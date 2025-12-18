"""Game orchestration via A2A SDK with enhanced prompt building and information hiding."""

import asyncio
import logging
import time
import random
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
    AgentRole, ActionType, DiscussionActionType
)
from app.types.game import GameState, GamePhase, GameConfig, GameStatus
from app.game.engine import GameEngine
from app.logging.storage import GameLogger
from app.prompts.builder import PromptBuilder
from app.memory.public_memory import PublicGameMemory

logger = logging.getLogger(__name__)


# Cost-saving limits
# MAX_GAME_ROUNDS removed - games can now run to completion without round limits
MAX_DISCUSSION_TURNS = 1  # Each agent speaks once per discussion round


class GameOrchestrator:
    """Orchestrates Werewolf games between white agents via A2A with enhanced prompt building."""

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
        # Set high timeout for LLM calls (5 minutes) - LLM responses can take time
        # Connect timeout: 60 seconds (for slow network connections)
        # Total timeout: 300 seconds (5 minutes for full LLM response)
        timeout = httpx.Timeout(300.0, connect=60.0)
        self.httpx_client = httpx_client or httpx.AsyncClient(timeout=timeout)
        self._owns_httpx_client = httpx_client is None
        
        # Track discussion context for sequential discussion
        self.discussion_context: Dict[str, List[Dict[str, Any]]] = {}
        
        # Track which agent is werewolf decision maker per game
        self.werewolf_decision_makers: Dict[str, str] = {}
        
        # Public memory for each game (shared across all agents)
        self.public_memories: Dict[str, PublicGameMemory] = {}

    async def start_game(
        self,
        agent_urls: List[str],
        config: Optional[GameConfig] = None,
        agent_models: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Start a new Werewolf game with the specified agents.

        Args:
            agent_urls: List of A2A-compliant agent URLs
            config: Optional game configuration
            agent_models: Optional mapping of agent_url -> model_name for tracking LLM models

        Returns:
            Game ID of the created game
        """
        # Initialize config if needed
        if config is None:
            config = GameConfig()
        # max_rounds is now optional (None = no limit)
        
        game_state = self.engine.create_game(agent_urls, config)

        agents = []
        for i, url in enumerate(agent_urls):
            agent_id = game_state.agent_ids[i]
            role = AgentRole(game_state.role_assignments[agent_id])
            
            # Get model information if provided
            model = None
            if agent_models:
                model = agent_models.get(url)

            agent = AgentProfile(
                agent_id=agent_id,
                agent_url=url,
                name=f"Agent {i+1}",
                role=role,
                model=model
            )
            agents.append(agent)
            self.agent_clients[agent_id] = A2AClient(
                httpx_client=self.httpx_client,
                url=url
            )

        # Select werewolf decision maker (random werewolf)
        werewolves = [
            aid for aid, role in game_state.role_assignments.items()
            if role == AgentRole.WEREWOLF.value
        ]
        if werewolves:
            self.werewolf_decision_makers[game_state.game_id] = random.choice(werewolves)
            logger.info(f"Werewolf decision maker: {self.werewolf_decision_makers[game_state.game_id]}")
        
        # Initialize public memory for this game
        self.public_memories[game_state.game_id] = PublicGameMemory(game_state.game_id)
        self.public_memories[game_state.game_id].update_alive_agents(
            game_state.round_number, game_state.alive_agent_ids
        )
        logger.info(f"Initialized public memory for game {game_state.game_id}")

        self.storage.log_game_created(game_state, agent_urls)
        self.storage.save_agents(game_state.game_id, agents)

        game_state = self.engine.start_game(game_state)
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
                
                # Check max rounds limit (if configured)
                if game_state.config.max_rounds is not None and game_state.round_number > game_state.config.max_rounds:
                    logger.info(f"Game {game_id} reached max rounds limit ({game_state.config.max_rounds})")
                    game_state = self._force_game_end(game_state)
                    self.storage.save_game(game_state, force_log=True)
                    await self._finalize_game(game_id)
                    break

                await self._run_phase(game_id)

                game_state = self.storage.get_game(game_id)
                phase_actions = self._get_phase_actions(game_id)

                if self.engine.should_advance_phase(game_state, phase_actions):
                    old_phase = game_state.phase
                    
                    # Update public memory before phase change
                    public_memory = self.public_memories.get(game_id)
                    if public_memory:
                        public_memory.end_phase()
                    
                    game_state, eliminated = self.engine.advance_phase(game_state, phase_actions)
                    
                    # Update public memory after phase change
                    if public_memory:
                        # Start new phase
                        public_memory.start_phase(
                            game_state.round_number,
                            game_state.phase.value,
                            game_state.alive_agent_ids
                        )
                        
                        # Record eliminations in public memory
                        for agent_id in eliminated:
                            method = self._determine_elimination_method(old_phase, game_state, agent_id)
                            public_memory.add_elimination(
                                agent_id=agent_id,
                                round_number=game_state.round_number,
                                method=method,
                                phase=old_phase.value
                            )
                        
                        # Update alive agents
                        public_memory.update_alive_agents(
                            game_state.round_number,
                            game_state.alive_agent_ids
                        )

                    logger.info(
                        f"Game {game_id}: {old_phase.value} -> {game_state.phase.value}"
                    )

                    # Handle last words for agents eliminated at night
                    night_eliminated = []
                    if old_phase in [GamePhase.NIGHT_WEREWOLF, GamePhase.NIGHT_WITCH, GamePhase.NIGHT_DOCTOR]:
                        night_eliminated = eliminated.copy()
                    
                    if night_eliminated:
                        logger.info(f"Game {game_id}: {len(night_eliminated)} agents eliminated at night - requesting last words")
                        # Re-fetch agents to get latest status after eliminations
                        agents = self.storage.get_agents(game_id)
                        await self._handle_last_words(game_id, game_state, night_eliminated, agents)
                        
                        # Handle hunter shooting for hunters eliminated at night
                        for agent_id in night_eliminated:
                            if game_state.role_assignments.get(agent_id) == AgentRole.HUNTER.value:
                                logger.info(f"Game {game_id}: Hunter {agent_id} was eliminated at night - requesting shoot action")
                                hunter_agent = next((a for a in agents if a.agent_id == agent_id), None)
                                if hunter_agent:
                                    await self._handle_hunter_shoot(game_id, game_state, hunter_agent, is_night=True)
                                    # Re-fetch game state after hunter shoot (may have eliminated another agent)
                                    game_state = self.storage.get_game(game_id)

                    # Handle hunter shooting for hunters eliminated by vote during the day
                    if old_phase == GamePhase.DAY_VOTING:
                        day_eliminated = eliminated.copy()
                        for agent_id in day_eliminated:
                            if game_state.role_assignments.get(agent_id) == AgentRole.HUNTER.value:
                                logger.info(f"Game {game_id}: Hunter {agent_id} was eliminated by vote - requesting shoot action")
                                agents = self.storage.get_agents(game_id)
                                hunter_agent = next((a for a in agents if a.agent_id == agent_id), None)
                                if hunter_agent:
                                    await self._handle_hunter_shoot(game_id, game_state, hunter_agent, is_night=False)
                                    # Re-fetch game state after hunter shoot (may have eliminated another agent)
                                    game_state = self.storage.get_game(game_id)

                    # Log all eliminations
                    for agent_id in eliminated:
                        logger.info(f"Game {game_id}: Agent {agent_id} eliminated")

                    self.storage.save_game(game_state)

                    if game_state.status == GameStatus.COMPLETED:
                        self.storage.save_game(game_state, force_log=True)
                        await self._finalize_game(game_id)
                        break

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            # Normal cancellation (e.g., Ctrl+C) - don't mark game as cancelled
            logger.info(f"Game loop for {game_id} was cancelled (normal interruption)")
            raise  # Re-raise to allow proper cleanup
        except Exception as e:
            logger.error(f"Error in game loop for {game_id}: {e}")
            import traceback
            traceback.print_exc()
            game_state = self.storage.get_game(game_id)
            if game_state:
                game_state.status = GameStatus.CANCELLED
                self.storage.save_game(game_state)

    def _force_game_end(self, game_state: GameState) -> GameState:
        """Force game to end when max rounds reached."""
        # No winner declared when max rounds reached - game didn't naturally conclude
        game_state.winner = None
        
        game_state.status = GameStatus.COMPLETED
        game_state.phase = GamePhase.GAME_OVER
        game_state.completed_at = datetime.utcnow()
        
        logger.info(f"Game {game_state.game_id} force-ended at round {game_state.round_number}. No winner (max rounds reached).")
        return game_state

    async def _run_phase(self, game_id: str):
        """Execute the current game phase by requesting actions from agents."""
        game_state = self.storage.get_game(game_id)
        if not game_state:
            return

        agents = self.storage.get_agents(game_id)
        if not agents:
            return

        active_agents = self._get_active_agents(game_state, agents)
        
        # Handle sequential discussion
        if game_state.phase == GamePhase.DAY_DISCUSSION:
            await self._run_sequential_discussion(game_id, game_state, active_agents)
            return
        
        # Handle werewolf decision maker logic
        if game_state.phase == GamePhase.NIGHT_WEREWOLF:
            await self._run_werewolf_phase(game_id, game_state, active_agents)
            return

        # Standard parallel processing for other phases
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
                self._handle_agent_error(game_id, agent_id, str(e))

    async def _run_sequential_discussion(
        self,
        game_id: str,
        game_state: GameState,
        agents: List[AgentProfile]
    ):
        """
        Run sequential discussion where each agent sees previous speakers' messages.
        
        Cost saving: Each agent speaks only once per discussion round.
        """
        # Initialize discussion context for this round
        if game_id not in self.discussion_context:
            self.discussion_context[game_id] = []
        
        # Clear context for new discussion round
        self.discussion_context[game_id] = []
        
        # Use fixed order (sorted by agent_id) for consistency
        # This ensures agents always speak in the same order each round
        speaking_order = sorted(agents, key=lambda a: a.agent_id)
        
        logger.info(f"Discussion order (fixed): {[a.agent_id for a in speaking_order]}")
        
        # Track which agents have already spoken to enforce one chance per agent
        agents_spoken = set()
        
        for agent in speaking_order:
            # Enforce one chance to speak per agent per discussion round
            if agent.agent_id in agents_spoken:
                logger.warning(f"Agent {agent.agent_id} attempted to speak multiple times - skipping")
                continue
            
            agents_spoken.add(agent.agent_id)
            try:
                # Get current discussion context (what previous agents said)
                current_context = self.discussion_context[game_id].copy()
                
                # Request action with sequential context
                action = await self._request_agent_action(
                    game_id, agent, game_state,
                    discussion_context=current_context
                )
                
                # Add this agent's discussion to context for next speakers
                if action and action.action_type == ActionType.DISCUSS:
                    self.discussion_context[game_id].append({
                        "agent_id": agent.agent_id,
                        "content": action.discussion_content or action.reasoning,
                        "discussion_type": action.discussion_action_type.value if action.discussion_action_type else "general",
                        "target": action.target_agent_id,
                    })
                    
            except Exception as e:
                logger.error(f"Error in sequential discussion from {agent.agent_id}: {e}")
                self._handle_agent_error(game_id, agent.agent_id, str(e))

    async def _handle_hunter_shoot(
        self,
        game_id: str,
        game_state: GameState,
        hunter_agent: AgentProfile,
        is_night: bool = False
    ):
        """Handle hunter shooting when eliminated.
        
        Args:
            game_id: Game ID
            game_state: Current game state
            hunter_agent: The eliminated hunter agent
            is_night: True if eliminated at night, False if eliminated by vote during day
        """
        # Temporarily set phase to HUNTER_SHOOT for prompt building
        original_phase = game_state.phase
        game_state.phase = GamePhase.HUNTER_SHOOT
        
        # Store context for prompt building
        game_state.metadata = game_state.metadata or {}
        game_state.metadata["hunter_shoot_is_night"] = is_night
        
        try:
            # Request shoot action from hunter
            shoot_action = await self._request_agent_action(
                game_id, hunter_agent, game_state
            )
            
            if shoot_action and shoot_action.action_type == ActionType.SHOOT:
                target = shoot_action.target_agent_id
                if target and target in game_state.alive_agent_ids:
                    # Process the shoot action
                    self._process_action(game_id, shoot_action)
                    
                    # Eliminate the shot target
                    self.engine.state_manager.eliminate_agent(game_state, target)
                    context = "at night" if is_night else "publicly during the day"
                    logger.info(f"Game {game_id}: Hunter {hunter_agent.agent_id} shot and eliminated {target} {context}")
                    
                    # Save game state
                    self.storage.save_game(game_state)
                else:
                    logger.warning(f"Game {game_id}: Hunter {hunter_agent.agent_id} attempted invalid shoot target: {target}")
            else:
                logger.warning(f"Game {game_id}: Hunter {hunter_agent.agent_id} did not provide valid shoot action")
        finally:
            # Restore original phase and clean up metadata
            game_state.phase = original_phase
            if game_state.metadata:
                game_state.metadata.pop("hunter_shoot_is_night", None)

    async def _handle_last_words(
        self,
        game_id: str,
        game_state: GameState,
        eliminated_agents: List[str],
        all_agents: List[AgentProfile]
    ):
        """
        Handle last words for agents eliminated at night.
        They speak first, before day discussion, and can only speak once.
        They can use multiple discussion subactions in their last words.
        """
        if not eliminated_agents:
            return
        
        # Get agent profiles for eliminated agents
        eliminated_profiles = [
            agent for agent in all_agents
            if agent.agent_id in eliminated_agents
        ]
        
        if not eliminated_profiles:
            return
        
        logger.info(f"Requesting last words from {len(eliminated_profiles)} eliminated agents")
        
        # Track who has given last words to ensure they only speak once
        agents_given_last_words = set()
        
        # Process last words sequentially (they speak first, before day discussion)
        for agent in eliminated_profiles:
            if agent.agent_id in agents_given_last_words:
                logger.warning(f"Agent {agent.agent_id} attempted to give last words multiple times - skipping")
                continue
            
            try:
                # Request last words action
                action = await self._request_agent_action(
                    game_id, agent, game_state,
                    is_last_words=True  # Signal that this is last words
                )
                
                if action and action.action_type == ActionType.DISCUSS:
                    # Ensure last_words subaction is included
                    subactions = action.get_discussion_subactions()
                    if DiscussionActionType.LAST_WORDS not in subactions:
                        # Add last_words as the first subaction if not present
                        if action.discussion_subactions is None:
                            action.discussion_subactions = []
                        action.discussion_subactions.insert(0, DiscussionActionType.LAST_WORDS)
                    
                    # Log the last words
                    self.storage.log_action(game_id, action)
                    agents_given_last_words.add(agent.agent_id)
                    
                    logger.info(f"Agent {agent.agent_id} gave last words with {len(action.get_discussion_subactions())} subactions")
                else:
                    logger.warning(f"Agent {agent.agent_id} did not provide valid last words discussion action")
                    
            except Exception as e:
                logger.error(f"Error getting last words from {agent.agent_id}: {e}")
                self._handle_agent_error(game_id, agent.agent_id, str(e))

    async def _run_werewolf_phase(
        self,
        game_id: str,
        game_state: GameState,
        werewolves: List[AgentProfile]
    ):
        """
        Run werewolf night phase with decision maker logic.
        
        One werewolf is randomly selected as decision maker. Others automatically agree.
        This simplifies the consensus mechanism.
        """
        decision_maker_id = self.werewolf_decision_makers.get(game_id)
        
        # If decision maker is dead, select new one from alive werewolves
        alive_werewolves = [w for w in werewolves if w.agent_id in game_state.alive_agent_ids]
        
        if not alive_werewolves:
            logger.warning(f"No alive werewolves in game {game_id}")
            return
        
        if not decision_maker_id or decision_maker_id not in [w.agent_id for w in alive_werewolves]:
            decision_maker_id = random.choice([w.agent_id for w in alive_werewolves])
            self.werewolf_decision_makers[game_id] = decision_maker_id
            logger.info(f"New werewolf decision maker: {decision_maker_id}")
        
        # Get decision from decision maker
        decision_maker = next((w for w in alive_werewolves if w.agent_id == decision_maker_id), None)
        
        if decision_maker:
            decision_action = await self._request_agent_action(
                game_id, decision_maker, game_state,
                is_decision_maker=True
            )
            
            if decision_action and decision_action.target_agent_id:
                target = decision_action.target_agent_id
                
                # Other werewolves automatically agree
                for werewolf in alive_werewolves:
                    if werewolf.agent_id != decision_maker_id:
                        # Create agreeing action
                        agree_action = WerewolfAction(
                            agent_id=werewolf.agent_id,
                            action_type=ActionType.KILL,
                            target_agent_id=target,
                            reasoning=f"Agreeing with {decision_maker_id}'s decision",
                            confidence=0.8
                        )
                        self._process_action(game_id, agree_action)
                        
                        # Log the automatic agreement
                        self.storage.log_agent_action_detail(
                            game_id=game_id,
                            agent_id=werewolf.agent_id,
                            prompt="[AUTOMATIC AGREEMENT - Not prompted]",
                            raw_response=f"Auto-agreeing with decision maker {decision_maker_id}",
                            parsed_action=agree_action.model_dump()
                        )

    async def _request_agent_action(
        self,
        game_id: str,
        agent: AgentProfile,
        game_state: GameState,
        discussion_context: List[Dict[str, Any]] = None,
        is_decision_maker: bool = False,
        is_last_words: bool = False
    ) -> Optional[WerewolfAction]:
        """Request an action from a white agent via A2A SDK with enhanced prompt."""
        
        # Build the prompt using PromptBuilder
        public_memory = self.public_memories.get(game_id)
        prompt = PromptBuilder.build_prompt(
            game_state=game_state,
            agent=agent,
            discussion_context=discussion_context,
            storage=self.storage,
            is_last_words=is_last_words,
            public_memory=public_memory
        )
        
        # Add decision maker context for werewolves
        if is_decision_maker and game_state.phase == GamePhase.NIGHT_WEREWOLF:
            prompt += "\n\nYou are the DECISION MAKER for the werewolves tonight. Your choice will be final."
        
        # Add last words context
        if is_last_words:
            prompt += "\n\n⚠️ IMPORTANT: You have been ELIMINATED at night. This is your LAST WORDS - you can only speak once. "
            prompt += "You may use multiple discussion subactions (e.g., defend someone AND accuse someone else). "
            prompt += "After this, you will never speak again.\n\n"
            prompt += "⚠️ CRITICAL: If you accuse or defend anyone, you MUST include their exact agent_id in DISCUSSION_TARGETS. "
            prompt += "If you mention someone in your message but don't include them in DISCUSSION_TARGETS, your action will be invalid."
        
        # Get visible state (for backwards compatibility)
        visible_state = self.engine.get_agent_view(game_state, agent.agent_id, self.storage)

        client = self.agent_clients.get(agent.agent_id)
        if not client:
            logger.error(f"No A2A client found for agent {agent.agent_id}")
            return None

        # Build task data with prompt
        task_data = {
            "task": "werewolf_action",
            "game_id": game_id,
            "prompt": prompt,  # Full constructed prompt
            "game_state": visible_state,
            "your_role": agent.role.value,
            "your_agent_id": agent.agent_id,  # Pass agent_id so White Agent can include it in response
            "phase": game_state.phase.value,
            "round": game_state.round_number,
            "alive_agents": game_state.alive_agent_ids,
            "eliminated_agents": game_state.eliminated_agent_ids,
            "valid_actions": self._get_valid_actions_for_phase(game_state.phase, agent.role),
        }

        if discussion_context:
            task_data["current_round_discussion"] = discussion_context

        if game_state.phase == GamePhase.DAY_VOTING:
            task_data["current_votes"] = game_state.current_votes

        start_time = time.time()

        # Log the prompt being sent (Deep Debug)
        self.storage.log_agent_prompt(
            game_id=game_id,
            agent_id=agent.agent_id,
            phase=game_state.phase.value,
            round_number=game_state.round_number,
            prompt=prompt
        )

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

            # Check if response itself is an error response
            if hasattr(response, 'root'):
                # Check for JSON-RPC errors first (error responses have 'error' attribute, not 'result')
                if hasattr(response.root, 'error') and response.root.error:
                    error_info = response.root.error
                    error_msg = f"JSON-RPC error from agent: {error_info}"
                    logger.error(f"Agent {agent.agent_id} returned error: {error_msg}")
                    self._handle_agent_error(game_id, agent.agent_id, error_msg)
                    return None
                
                # Check if response.root is an error response type (no 'result' attribute)
                if not hasattr(response.root, 'result'):
                    error_msg = f"Agent {agent.agent_id} returned error response (no result attribute)"
                    logger.error(error_msg)
                    # Try to extract error info if available
                    if hasattr(response.root, 'error'):
                        error_msg += f": {response.root.error}"
                    self._handle_agent_error(game_id, agent.agent_id, error_msg)
                    return None

                # Check for result
                if response.root.result:
                    result = response.root.result
                    for part_text in self._iter_response_text_parts(result):
                        # Extract raw LLM text from metadata if available
                        try:
                            response_data = json.loads(part_text)
                            raw_llm_text = None
                            if isinstance(response_data, dict):
                                action_meta = response_data.get("action", {}).get("metadata", {})
                                raw_llm_text = action_meta.get("raw_llm_text")
                        except:
                            raw_llm_text = None
                        
                        # Log raw response (Deep Debug)
                        # part_text is the JSON response from White Agent
                        # If raw_llm_text is available, log it separately
                        self.storage.log_agent_response(
                            game_id=game_id,
                            agent_id=agent.agent_id,
                            phase=game_state.phase.value,
                            round_number=game_state.round_number,
                            raw_response=part_text,  # JSON response from White Agent
                            response_time_ms=response_time
                        )
                        
                        # Also log raw LLM text if available (before JSON formatting)
                        if raw_llm_text:
                            self.storage._write_game_event(game_id, {
                                "event": "DEBUG_raw_llm_text",
                                "timestamp": datetime.utcnow().isoformat(),
                                "game_id": game_id,
                                "agent_id": agent.agent_id,
                                "phase": game_state.phase.value,
                                "round_number": game_state.round_number,
                                "raw_llm_text": raw_llm_text,
                                "response_time_ms": response_time
                            })
                        
                        try:
                            response_data = json.loads(part_text)
                        except json.JSONDecodeError as decode_error:
                            logger.error(
                                f"Failed to decode agent response JSON: {decode_error}"
                            )
                            self._handle_invalid_response(game_id, agent.agent_id, part_text, "JSON decode error")
                            continue

                        try:
                            agent_response = AgentResponse(**response_data)
                        except Exception as parse_error:
                            logger.error(f"Failed to parse agent response: {parse_error}")
                            self._handle_invalid_response(game_id, agent.agent_id, part_text, str(parse_error))
                            continue

                        action = agent_response.action
                        action.agent_id = agent.agent_id
                        
                        # Log the parsed action (Deep Debug)
                        self.storage.log_agent_action_detail(
                            game_id=game_id,
                            agent_id=agent.agent_id,
                            prompt=prompt,
                            raw_response=part_text,
                            parsed_action=action.model_dump()
                        )
                        
                        self._process_action(game_id, action)
                        return action

                    logger.error(
                        f"Agent {agent.agent_id} returned unexpected response format: {result}"
                    )
                    return None
                else:
                    # No result attribute - might be an error response
                    error_msg = f"Agent {agent.agent_id} returned response without result"
                    logger.error(error_msg)
                    self._handle_agent_error(game_id, agent.agent_id, error_msg)
                    return None
            else:
                # Response doesn't have root attribute - might be error response object
                error_msg = f"Agent {agent.agent_id} returned unexpected response type: {type(response)}"
                logger.error(error_msg)
                self._handle_agent_error(game_id, agent.agent_id, error_msg)
                return None

        except Exception as e:
            logger.error(f"Failed to get action from {agent.agent_id}: {e}")
            self._handle_agent_error(game_id, agent.agent_id, str(e))
            return None

    def _get_valid_actions_for_phase(self, phase: GamePhase, role: AgentRole) -> List[str]:
        """Get list of valid actions for the current phase and role."""
        if phase == GamePhase.DAY_DISCUSSION:
            return ["discuss", "pass"]
        elif phase == GamePhase.DAY_VOTING:
            return ["vote"]
        elif phase == GamePhase.NIGHT_WEREWOLF:
            return ["kill", "pass"] if role == AgentRole.WEREWOLF else ["pass"]
        elif phase == GamePhase.NIGHT_SEER:
            return ["investigate", "pass"] if role == AgentRole.SEER else ["pass"]
        elif phase == GamePhase.NIGHT_DOCTOR:
            return ["protect", "pass"] if role == AgentRole.DOCTOR else ["pass"]
        elif phase == GamePhase.NIGHT_WITCH:
            return ["heal", "poison", "pass"] if role == AgentRole.WITCH else ["pass"]
        return ["pass"]

    def _handle_agent_error(self, game_id: str, agent_id: str, error: str):
        """Handle agent errors by logging and creating a pass action."""
        logger.warning(f"Agent {agent_id} error: {error}")
        
        # Log the error
        self.storage.log_agent_error(
            game_id=game_id,
            agent_id=agent_id,
            error_type="agent_communication_error",
            error_message=error
        )
        
        # Create a pass action as fallback
        pass_action = WerewolfAction(
            agent_id=agent_id,
            action_type=ActionType.PASS,
            reasoning=f"Error occurred: {error}",
            confidence=0.0
        )
        self._process_action(game_id, pass_action)

    def _handle_invalid_response(self, game_id: str, agent_id: str, response: str, error: str):
        """Handle invalid responses from agents."""
        logger.warning(f"Invalid response from {agent_id}: {error}")
        
        # Log the invalid response
        self.storage.log_agent_error(
            game_id=game_id,
            agent_id=agent_id,
            error_type="invalid_response",
            error_message=error,
            raw_response=response
        )

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
            
            # Update public memory with public actions
            self._update_public_memory_with_action(game_id, action, game_state)
        else:
            logger.warning(f"Invalid action from {action.agent_id}: {error_msg}")
            # Log invalid actions to the game log for analysis
            self.storage.log_invalid_action(game_id, action, error_msg, game_state.round_number)
            
            # Create fallback action
            self._create_fallback_action(game_id, action.agent_id, game_state, error_msg)

    def _create_fallback_action(
        self,
        game_id: str,
        agent_id: str,
        game_state: GameState,
        error_msg: str
    ):
        """Create a valid fallback action when an invalid action is submitted."""
        phase = game_state.phase
        role_str = game_state.role_assignments.get(agent_id)
        role = AgentRole(role_str) if role_str else AgentRole.VILLAGER
        
        # Determine appropriate fallback
        if phase == GamePhase.DAY_VOTING:
            # Vote for a random valid target
            valid_targets = [
                aid for aid in game_state.alive_agent_ids
                if aid != agent_id
            ]
            if valid_targets:
                fallback = WerewolfAction(
                    agent_id=agent_id,
                    action_type=ActionType.VOTE,
                    target_agent_id=random.choice(valid_targets),
                    reasoning=f"Fallback vote due to invalid action: {error_msg}",
                    confidence=0.1
                )
            else:
                return  # No valid targets
        else:
            # Default to pass
            fallback = WerewolfAction(
                agent_id=agent_id,
                action_type=ActionType.PASS,
                reasoning=f"Fallback pass due to invalid action: {error_msg}",
                confidence=0.0
            )
        
        # Process the fallback action
        success, _ = self.engine.process_action(game_state, fallback)
        if success:
            self.storage.save_action(game_id, fallback, game_state.round_number)
            self.storage.save_game(game_state)
            logger.info(f"Applied fallback action for {agent_id}: {fallback.action_type}")

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
    
    def _determine_elimination_method(
        self,
        phase: GamePhase,
        game_state: GameState,
        agent_id: str
    ) -> str:
        """Determine how an agent was eliminated based on the phase."""
        if phase == GamePhase.DAY_VOTING:
            return "vote"
        elif phase == GamePhase.NIGHT_WEREWOLF:
            return "werewolf_kill"
        elif phase == GamePhase.NIGHT_WITCH:
            return "witch_poison"
        elif phase == GamePhase.HUNTER_SHOOT:
            return "hunter_shot"
        elif phase in [GamePhase.NIGHT_DOCTOR, GamePhase.NIGHT_SEER]:
            # These phases don't directly cause eliminations, but the night kill
            # is finalized when transitioning to day
            return "werewolf_kill"
        else:
            return "unknown"
    
    def _update_public_memory_with_action(
        self,
        game_id: str,
        action: WerewolfAction,
        game_state: GameState
    ) -> None:
        """Update public memory with a successfully processed action."""
        public_memory = self.public_memories.get(game_id)
        if not public_memory:
            return
        
        # Only public actions should be recorded in public memory
        if action.action_type == ActionType.DISCUSS:
            # Get subactions and targets
            subactions = action.get_discussion_subactions()
            targets = action.get_discussion_targets()
            
            # Flatten targets for simple storage
            all_targets = []
            for target_list in targets:
                all_targets.extend(target_list)
            
            public_memory.add_discussion(
                agent_id=action.agent_id,
                content=action.discussion_content or action.reasoning,
                round_number=game_state.round_number,
                discussion_type=subactions[0].value if subactions else "general",
                targets=all_targets,
                subactions=[s.value for s in subactions] if subactions else None
            )
        
        elif action.action_type == ActionType.VOTE:
            if action.target_agent_id:
                public_memory.add_vote(
                    voter_id=action.agent_id,
                    target_id=action.target_agent_id,
                    round_number=game_state.round_number
                )
        
        # Note: Night actions (KILL, INVESTIGATE, PROTECT, HEAL, POISON) are NOT recorded
        # in public memory as they are private information

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

        # Calculate and store evaluation scores
        # Note: Most metrics don't require a winner - they're based on actions, discussions, etc.
        # Only the 'winner' field itself will be None for games that hit max rounds
        try:
            from extract_game_metrics import extract_game_metrics
            import os
            
            # Use custom name if available from storage, otherwise use game_id
            file_name = self.storage.game_name if hasattr(self.storage, 'game_name') and self.storage.game_name else game_id
            game_log_path = f"game_logs/baseline/game_{file_name}.jsonl"
            if os.path.exists(game_log_path):
                logger.info(f"Calculating metrics for game {game_id}")
                metrics = extract_game_metrics(game_log_path)
                
                # Ensure winner field matches game state (will be None for max-round games)
                metrics["winner"] = game_state.winner
                
                self.storage._write_game_event(game_id, {
                    "event": "evaluation_metrics",
                    "timestamp": datetime.utcnow().isoformat(),
                    "game_id": game_id,
                    "metrics": metrics
                })
                
                if game_state.winner is None:
                    logger.info(f"Game {game_id} metrics calculated (no winner - max rounds reached)")
                else:
                    logger.info(f"Game {game_id} evaluation completed with {len(metrics)} metrics")
            else:
                logger.warning(f"Game log not found for metrics calculation: {game_log_path}")
        except Exception as e:
            logger.error(f"Failed to calculate metrics for game {game_id}: {e}")
            import traceback
            traceback.print_exc()

        # Clean up discussion context
        if game_id in self.discussion_context:
            del self.discussion_context[game_id]
        
        # Clean up werewolf decision maker
        if game_id in self.werewolf_decision_makers:
            del self.werewolf_decision_makers[game_id]
        
        # Clean up public memory
        if game_id in self.public_memories:
            del self.public_memories[game_id]

        # Clean up agent clients
        for agent_id in list(self.agent_clients.keys()):
            if agent_id in game_state.agent_ids:
                self.agent_clients.pop(agent_id, None)

        logger.info(f"Game {game_id} finalized and cleaned up")

    async def close(self):
        """Clean up resources."""
        if self._owns_httpx_client:
            await self.httpx_client.aclose()
        self.agent_clients.clear()
