"""Game orchestration via A2A SDK"""

import asyncio
import logging
import time
from typing import List, Dict, Optional, Any, Iterator
from datetime import datetime
import json

import httpx
from a2a.client import A2AClient
from a2a.types import (
    SendMessageRequest, MessageSendParams, Message,
    Part, TextPart, Role
)

from fastapi.encoders import jsonable_encoder

from app.types.agent import (
    WerewolfAction, AgentProfile, AgentResponse,
    AgentRole, ActionType
)
from app.types.game import GameState, GamePhase, GameConfig, GameStatus
from app.game.engine import GameEngine
from app.logging.storage import GameLogger

logger = logging.getLogger(__name__)


class GameOrchestrator:
    """Orchestrates Werewolf games between white agents via A2A"""

    def __init__(
        self,
        storage: GameLogger,
        httpx_client: Optional[httpx.AsyncClient] = None
    ):
        """
        Initialize the orchestrator.

        Args:
            storage: Game logger for data persistence
        """
        self.storage = storage
        self.engine = GameEngine()
        self.agent_clients: Dict[str, A2AClient] = {}
        self.httpx_client = httpx_client or httpx.AsyncClient()
        self._owns_httpx_client = httpx_client is None

    async def start_game(
        self,
        agent_urls: List[str],
        config: Optional[GameConfig] = None
    ) -> str:
        """
        Start a new Werewolf game with the specified agents.

        Args:
            agent_urls: List of A2A-compliant agent URLs
            config: Optional game configuration

        Returns:
            Game ID of the created game
        """
        game_state = self.engine.create_game(agent_urls, config)

        agents = []
        for i, url in enumerate(agent_urls):
            agent_id = game_state.agent_ids[i]
            role = AgentRole(game_state.role_assignments[agent_id])

            agent = AgentProfile(
                agent_id=agent_id,
                agent_url=url,
                name=f"Agent {i+1}",
                role=role
            )
            agents.append(agent)
            self.agent_clients[agent_id] = A2AClient(
                httpx_client=self.httpx_client,
                url=url
            )

        self.storage.log_game_created(game_state, agent_urls)
        self.storage.save_agents(game_state.game_id, agents)

        game_state = self.engine.start_game(game_state)
        # Log game started BEFORE first game update
        self.storage.log_game_started(game_state.game_id)
        self.storage.save_game(game_state, force_log=True)

        asyncio.create_task(self._run_game_loop(game_state.game_id))

        logger.info(f"Started game {game_state.game_id} with {len(agents)} agents")
        return game_state.game_id

    async def _run_game_loop(self, game_id: str):
        """Main game loop that manages phases and agent interactions."""
        try:
            while True:
                game_state = self.storage.get_game(game_id)
                if not game_state or game_state.status == GameStatus.COMPLETED:
                    break

                await self._run_phase(game_id)

                game_state = self.storage.get_game(game_id)
                phase_actions = self._get_phase_actions(game_id)

                if self.engine.should_advance_phase(game_state, phase_actions):
                    old_phase = game_state.phase
                    game_state, eliminated = self.engine.advance_phase(game_state, phase_actions)

                    logger.info(
                        f"Game {game_id}: {old_phase.value} -> {game_state.phase.value}"
                    )

                    for agent_id in eliminated:
                        logger.info(f"Game {game_id}: Agent {agent_id} eliminated")

                    self.storage.save_game(game_state)

                    if game_state.status == GameStatus.COMPLETED:
                        # Log final game state with winner
                        self.storage.save_game(game_state, force_log=True)
                        await self._finalize_game(game_id)
                        break

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in game loop for {game_id}: {e}")
            game_state = self.storage.get_game(game_id)
            if game_state:
                game_state.status = GameStatus.CANCELLED
                self.storage.save_game(game_state)

    async def _run_phase(self, game_id: str):
        """Execute the current game phase by requesting actions from agents."""
        game_state = self.storage.get_game(game_id)
        if not game_state:
            return

        agents = self.storage.get_agents(game_id)
        if not agents:
            return

        active_agents = self._get_active_agents(game_state, agents)

        tasks = []
        for agent in active_agents:
            task = asyncio.create_task(
                self._request_agent_action(game_id, agent, game_state)
            )
            tasks.append((agent.agent_id, task))

        for agent_id, task in tasks:
            try:
                await task
            except Exception as e:
                logger.error(f"Error getting action from {agent_id}: {e}")
                pass_action = WerewolfAction(
                    agent_id=agent_id,
                    action_type=ActionType.PASS,
                    reasoning="Failed to respond in time",
                    confidence=0.0
                )
                self._process_action(game_id, pass_action)

    async def _request_agent_action(
        self,
        game_id: str,
        agent: AgentProfile,
        game_state: GameState
    ) -> Optional[WerewolfAction]:
        """Request an action from a white agent via A2A SDK."""
        visible_state = self.engine.get_agent_view(game_state, agent.agent_id, self.storage)

        client = self.agent_clients.get(agent.agent_id)
        if not client:
            logger.error(f"No A2A client found for agent {agent.agent_id}")
            return None

        task_data = {
            "task": "werewolf_action",
            "game_id": game_id,
            "game_state": visible_state,
            "your_role": agent.role.value,
            "phase": game_state.phase.value,
            "round": game_state.round_number,
            "alive_agents": game_state.alive_agent_ids,
            "eliminated_agents": game_state.eliminated_agent_ids,
            "previous_actions": [
                a.model_dump() for a in self.storage.get_agent_actions(game_id, agent.agent_id)
            ][-5:]
        }

        if game_state.phase == GamePhase.DAY_VOTING:
            task_data["current_votes"] = game_state.current_votes

        start_time = time.time()

        try:
            message = Message(
                message_id=str(time.time()),
                role=Role.user,
                parts=[
                    TextPart(
                        kind="text",
                        text=json.dumps(jsonable_encoder(task_data)),
                    )
                ]
            )

            request = SendMessageRequest(
                id=str(time.time()),
                jsonrpc="2.0",
                method="message/send",
                params=MessageSendParams(message=message)
            )

            response = await client.send_message(request)
            response_time = (time.time() - start_time) * 1000

            logger.debug(
                f"Agent {agent.agent_id} responded in {response_time:.2f}ms"
            )

            if response.root.result:
                result = response.root.result
                for part_text in self._iter_response_text_parts(result):
                    try:
                        response_data = json.loads(part_text)
                    except json.JSONDecodeError as decode_error:
                        logger.error(
                            f"Failed to decode agent response JSON: {decode_error}"
                        )
                        continue

                    try:
                        agent_response = AgentResponse(**response_data)
                    except Exception as parse_error:
                        logger.error(f"Failed to parse agent response: {parse_error}")
                        continue

                    action = agent_response.action
                    action.agent_id = agent.agent_id
                    self._process_action(game_id, action)
                    return action

                logger.error(
                    f"Agent {agent.agent_id} returned unexpected response format: {result}"
                )
                return None
            else:
                logger.error(f"Agent {agent.agent_id} returned error")
                return None

        except Exception as e:
            logger.error(f"Failed to get action from {agent.agent_id}: {e}")
            return None

    def _iter_response_text_parts(self, result: Any) -> Iterator[str]:
        """Yield text content from response parts regardless of structure."""
        parts = getattr(result, "parts", None)
        if parts is None and isinstance(result, dict):
            parts = result.get("parts", [])
        if not parts:
            return iter(())

        def _generator():
            for part in parts:
                text = None
                if hasattr(part, "text"):
                    text = part.text
                elif hasattr(part, "root"):
                    root = getattr(part, "root")
                    if hasattr(root, "text"):
                        text = root.text
                elif isinstance(part, dict):
                    text = part.get("text")
                if text:
                    yield text

        return _generator()

    def _process_action(self, game_id: str, action: WerewolfAction):
        """Process and validate an agent's action."""
        game_state = self.storage.get_game(game_id)
        if not game_state:
            return

        success, error_msg = self.engine.process_action(game_state, action)

        if success:
            self.storage.save_action(game_id, action, game_state.round_number)
            self.storage.save_game(game_state)
            logger.debug(f"Processed action from {action.agent_id}: {action.action_type}")
        else:
            logger.warning(f"Invalid action from {action.agent_id}: {error_msg}")

    def _get_active_agents(
        self,
        game_state: GameState,
        agents: List[AgentProfile]
    ) -> List[AgentProfile]:
        """Get list of agents that should act in the current phase."""
        active = []

        for agent in agents:
            if agent.agent_id not in game_state.alive_agent_ids:
                continue

            role = game_state.role_assignments.get(agent.agent_id)

            if game_state.phase in [GamePhase.DAY_DISCUSSION, GamePhase.DAY_VOTING]:
                active.append(agent)
            elif game_state.phase == GamePhase.NIGHT_WEREWOLF:
                if role == AgentRole.WEREWOLF.value:
                    active.append(agent)
            elif game_state.phase == GamePhase.NIGHT_WITCH:
                if role == AgentRole.WITCH.value:
                    active.append(agent)
            elif game_state.phase == GamePhase.NIGHT_SEER:
                if role == AgentRole.SEER.value:
                    active.append(agent)
            elif game_state.phase == GamePhase.NIGHT_DOCTOR:
                if role == AgentRole.DOCTOR.value:
                    active.append(agent)

        return active

    def _get_phase_actions(self, game_id: str) -> List[WerewolfAction]:
        """Get all actions from the current phase."""
        all_actions = self.storage.get_game_actions(game_id)
        recent_actions = [
            a for a in all_actions
            if (datetime.utcnow() - a.timestamp).total_seconds() < 300
        ]
        return recent_actions

    async def _finalize_game(self, game_id: str):
        """Finalize game and clean up resources."""
        game_state = self.storage.get_game(game_id)
        if not game_state:
            return

        logger.info(
            f"Game {game_id} completed. Winner: {game_state.winner}, "
            f"Rounds: {game_state.round_number}"
        )

        # Log comprehensive game completion
        self.storage.log_game_completed(game_state)
        self.storage.log_game_ended(game_id, game_state.winner, game_state.round_number)

        # TODO: Calculate and store evaluation scores

        for agent_id in list(self.agent_clients.keys()):
            if agent_id in game_state.agent_ids:
                self.agent_clients.pop(agent_id, None)

        logger.info(f"Game {game_id} finalized and cleaned up")

    async def close(self):
        """Clean up resources."""
        if self._owns_httpx_client:
            await self.httpx_client.aclose()
        self.agent_clients.clear()
