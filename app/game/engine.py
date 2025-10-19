"""Main game engine for Werewolf Benchmark"""

import uuid
from typing import List, Dict, Optional
from datetime import datetime
import logging

from app.types.agent import WerewolfAction, AgentRole, ActionType
from app.types.game import GameState, GamePhase, GameStatus, GameConfig
from app.game.rules import RulesValidator
from app.game.state import StateManager

logger = logging.getLogger(__name__)


class GameEngine:
    """Core game engine that manages game lifecycle and processes actions."""

    def __init__(self):
        self.rules_validator = RulesValidator()
        self.state_manager = StateManager()

    def create_game(
        self,
        agent_urls: List[str],
        config: Optional[GameConfig] = None
    ) -> GameState:
        """Create a new game with the specified agents."""
        if len(agent_urls) < 4:
            raise ValueError("Minimum 4 agents required to play Werewolf")

        game_id = str(uuid.uuid4())
        agent_ids = [f"agent_{i}" for i in range(len(agent_urls))]

        game_state = GameState(
            game_id=game_id,
            status=GameStatus.WAITING,
            phase=GamePhase.SETUP,
            agent_ids=agent_ids,
            alive_agent_ids=agent_ids.copy(),
            config=config or GameConfig()
        )

        game_state.role_assignments = self.state_manager.assign_roles(
            agent_ids,
            game_state.config.model_dump()
        )

        logger.info(f"Created game {game_id} with {len(agent_urls)} agents")
        return game_state

    def start_game(self, game_state: GameState) -> GameState:
        """Start the game and move to first phase."""
        if game_state.status != GameStatus.WAITING:
            raise ValueError(f"Cannot start game in status {game_state.status}")

        game_state.status = GameStatus.IN_PROGRESS
        game_state.phase = GamePhase.DAY_DISCUSSION
        game_state.round_number = 1
        game_state.started_at = datetime.utcnow()

        logger.info(f"Started game {game_state.game_id}")
        return game_state

    def process_action(
        self,
        game_state: GameState,
        action: WerewolfAction
    ) -> tuple[bool, Optional[str]]:
        """Process an agent's action in the game."""
        agent_role = AgentRole(game_state.role_assignments.get(action.agent_id))

        is_valid, error_msg = self.rules_validator.is_action_valid(
            action, game_state, agent_role
        )

        if not is_valid:
            logger.warning(f"Invalid action from {action.agent_id}: {error_msg}")
            return False, error_msg

        if action.action_type == ActionType.VOTE:
            game_state.current_votes[action.agent_id] = action.target_agent_id

        logger.info(
            f"Processed {action.action_type} from {action.agent_id} "
            f"targeting {action.target_agent_id}"
        )

        return True, None

    def should_advance_phase(
        self,
        game_state: GameState,
        received_actions: List[WerewolfAction]
    ) -> bool:
        """Determine if the game should advance to the next phase."""
        expected_agents = self._get_expected_agents_for_phase(game_state)
        acted_agents = {action.agent_id for action in received_actions}
        return expected_agents.issubset(acted_agents)

    def advance_phase(
        self,
        game_state: GameState,
        phase_actions: List[WerewolfAction]
    ) -> tuple[GameState, List[str]]:
        """
        Advance game to the next phase and process phase results.

        Args:
            game_state: Current game state
            phase_actions: All actions from the current phase

        Returns:
            Tuple of (updated game state, list of eliminated agent IDs)
        """
        eliminated = []

        # Process phase-specific outcomes
        if game_state.phase == GamePhase.DAY_VOTING:
            eliminated_id = self.state_manager.process_voting_results(game_state)
            if eliminated_id:
                self.state_manager.eliminate_agent(game_state, eliminated_id)
                eliminated.append(eliminated_id)
                logger.info(f"Agent {eliminated_id} eliminated by vote")

        elif game_state.phase == GamePhase.NIGHT_WEREWOLF:
            werewolf_actions = [
                a for a in phase_actions
                if a.action_type == ActionType.KILL
            ]
            target_id = self.state_manager.process_werewolf_kill(
                game_state, werewolf_actions
            )

            # Check if target was protected
            doctor_protection = self._get_doctor_protection(phase_actions)
            if target_id and target_id != doctor_protection:
                self.state_manager.eliminate_agent(game_state, target_id)
                eliminated.append(target_id)
                logger.info(f"Agent {target_id} killed by werewolves")

        # Record round history
        round_record = self.state_manager.create_round_record(
            game_state, phase_actions, eliminated
        )
        game_state.round_history.append(round_record)

        # Advance to next phase
        self.state_manager.advance_round(game_state)

        # Check for game end
        game_ended, winner = self.rules_validator.check_game_end_condition(game_state)
        if game_ended:
            game_state.status = GameStatus.COMPLETED
            game_state.phase = GamePhase.GAME_OVER
            game_state.winner = winner
            game_state.completed_at = datetime.utcnow()
            logger.info(f"Game {game_state.game_id} ended. Winner: {winner}")

        return game_state, eliminated

    def get_agent_view(self, game_state: GameState, agent_id: str) -> Dict:
        """
        Get the game state from an agent's perspective.

        Args:
            game_state: Current game state
            agent_id: ID of the agent

        Returns:
            Filtered game state visible to the agent
        """
        return self.state_manager.get_visible_state(game_state, agent_id)

    def _get_expected_agents_for_phase(self, game_state: GameState) -> set:
        """Get set of agents expected to act in current phase"""
        if game_state.phase in [GamePhase.DAY_DISCUSSION, GamePhase.DAY_VOTING]:
            # All alive agents participate
            return set(game_state.alive_agent_ids)

        elif game_state.phase == GamePhase.NIGHT_WEREWOLF:
            # Only werewolves act
            return {
                agent_id for agent_id in game_state.alive_agent_ids
                if game_state.role_assignments.get(agent_id) == AgentRole.WEREWOLF.value
            }

        elif game_state.phase == GamePhase.NIGHT_SEER:
            # Only seer acts (if alive)
            return {
                agent_id for agent_id in game_state.alive_agent_ids
                if game_state.role_assignments.get(agent_id) == AgentRole.SEER.value
            }

        elif game_state.phase == GamePhase.NIGHT_DOCTOR:
            # Only doctor acts (if alive)
            return {
                agent_id for agent_id in game_state.alive_agent_ids
                if game_state.role_assignments.get(agent_id) == AgentRole.DOCTOR.value
            }

        return set()

    def _get_doctor_protection(self, phase_actions: List[WerewolfAction]) -> Optional[str]:
        """Get the agent protected by doctor this round"""
        for action in phase_actions:
            if action.action_type == ActionType.PROTECT:
                return action.target_agent_id
        return None