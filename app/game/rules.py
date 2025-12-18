"""Rules validation for Werewolf game actions"""

from typing import List, Optional, Set
from app.types.agent import WerewolfAction, ActionType, AgentRole, DiscussionActionType
from app.types.game import GameState, GamePhase


class RulesValidator:
    """Validates that game actions follow Werewolf rules"""

    @staticmethod
    def is_action_valid(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """
        Check if an action is valid given the current game state.
        Returns (is_valid, error_message)
        """
        # Check if agent is alive
        if action.agent_id not in game_state.alive_agent_ids:
            return False, "Dead agents cannot take actions"

        # Check if target is valid (if applicable)
        if action.target_agent_id:
            if action.target_agent_id not in game_state.agent_ids:
                return False, "Target agent does not exist"

        # Validate action based on game phase
        phase_validators = {
            GamePhase.DAY_DISCUSSION: RulesValidator._validate_discussion,
            GamePhase.DAY_VOTING: RulesValidator._validate_voting,
            GamePhase.NIGHT_WEREWOLF: RulesValidator._validate_werewolf_night,
            GamePhase.NIGHT_WITCH: RulesValidator._validate_witch_night,
            GamePhase.NIGHT_SEER: RulesValidator._validate_seer_night,
            GamePhase.NIGHT_DOCTOR: RulesValidator._validate_doctor_night,
        }

        validator = phase_validators.get(game_state.phase)
        if not validator:
            return False, f"Invalid game phase: {game_state.phase}"

        return validator(action, game_state, agent_role)

    @staticmethod
    def _validate_discussion(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """Validate actions during day discussion phase"""
        if action.action_type not in [ActionType.DISCUSS, ActionType.PASS]:
            return False, "Only discussion or pass allowed during discussion phase"
        
        # If it's a discuss action, validate the discussion sub-action
        if action.action_type == ActionType.DISCUSS:
            return RulesValidator._validate_discussion_sub_action(action, game_state, agent_role)
        
        return True, None

    @staticmethod
    def _validate_discussion_sub_action(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """Validate discussion sub-actions based on role and content"""
        if not action.discussion_action_type:
            return True, None  # General discussion is always allowed
        
        sub_action = action.discussion_action_type
        
        # Everyone can do these actions
        if sub_action in [DiscussionActionType.GENERAL_DISCUSSION, DiscussionActionType.REVEAL_IDENTITY, 
                         DiscussionActionType.ACCUSE, DiscussionActionType.DEFEND, DiscussionActionType.CLAIM_ROLE]:
            return True, None
        
        # Role-specific actions
        if sub_action == DiscussionActionType.REVEAL_INVESTIGATION:
            if agent_role != AgentRole.SEER:
                return False, "Only seers can reveal investigation results"
            return True, None
            
        elif sub_action == DiscussionActionType.REVEAL_HEALED_KILLED:
            if agent_role != AgentRole.WITCH:
                return False, "Only witches can reveal healing/killing information"
            return True, None
            
        elif sub_action == DiscussionActionType.REVEAL_PROTECTED:
            if agent_role != AgentRole.DOCTOR:
                return False, "Only doctors can reveal protection information"
            return True, None
            
        elif sub_action == DiscussionActionType.REVEAL_WEREWOLF:
            if agent_role != AgentRole.WEREWOLF:
                return False, "Only werewolves can reveal other werewolves"
            # Validate that target is actually a werewolf
            if action.target_agent_id:
                target_role = game_state.role_assignments.get(action.target_agent_id)
                if target_role != AgentRole.WEREWOLF.value:
                    return False, "Can only reveal actual werewolves"
            return True, None
        
        return True, None

    @staticmethod
    def _validate_voting(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """Validate voting actions"""
        if action.action_type != ActionType.VOTE:
            return False, "Only voting allowed during voting phase"

        if not action.target_agent_id:
            return False, "Vote must specify a target"

        if action.target_agent_id not in game_state.alive_agent_ids:
            return False, "Can only vote for living agents"

        if action.target_agent_id == action.agent_id:
            return False, "Cannot vote for yourself"

        return True, None

    @staticmethod
    def _validate_werewolf_night(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """Validate werewolf night actions"""
        if agent_role != AgentRole.WEREWOLF:
            if action.action_type != ActionType.PASS:
                return False, "Non-werewolves must pass during werewolf phase"
            return True, None

        if action.action_type not in [ActionType.KILL, ActionType.PASS]:
            return False, "Werewolves can only kill or pass"

        if action.action_type == ActionType.KILL:
            if not action.target_agent_id:
                return False, "Kill action must specify a target"

            if action.target_agent_id not in game_state.alive_agent_ids:
                return False, "Can only target living agents"

            # Check if target is a werewolf
            target_role = game_state.role_assignments.get(action.target_agent_id)
            if target_role == AgentRole.WEREWOLF.value:
                return False, "Werewolves cannot kill other werewolves"

        return True, None

    @staticmethod
    def _validate_seer_night(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """Validate seer night actions"""
        if agent_role != AgentRole.SEER:
            if action.action_type != ActionType.PASS:
                return False, "Non-seers must pass during seer phase"
            return True, None

        if action.action_type not in [ActionType.INVESTIGATE, ActionType.PASS]:
            return False, "Seer can only investigate or pass"

        if action.action_type == ActionType.INVESTIGATE:
            if not action.target_agent_id:
                return False, "Investigation must specify a target"

            if action.target_agent_id not in game_state.alive_agent_ids:
                return False, "Can only investigate living agents"

            if action.target_agent_id == action.agent_id:
                return False, "Cannot investigate yourself"

        return True, None

    @staticmethod
    def _validate_doctor_night(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """Validate doctor night actions"""
        if agent_role != AgentRole.DOCTOR:
            if action.action_type != ActionType.PASS:
                return False, "Non-doctors must pass during doctor phase"
            return True, None

        if action.action_type not in [ActionType.PROTECT, ActionType.PASS]:
            return False, "Doctor can only protect or pass"

        if action.action_type == ActionType.PROTECT:
            if not action.target_agent_id:
                return False, "Protection must specify a target"

            if action.target_agent_id not in game_state.alive_agent_ids:
                return False, "Can only protect living agents"

        return True, None

    @staticmethod
    def _validate_witch_night(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """Validate witch night actions"""
        if agent_role != AgentRole.WITCH:
            if action.action_type != ActionType.PASS:
                return False, "Non-witches must pass during witch phase"
            return True, None

        if action.action_type not in [ActionType.HEAL, ActionType.POISON, ActionType.PASS]:
            return False, "Witch can only heal, poison, or pass"

        if action.action_type == ActionType.HEAL:
            if not action.target_agent_id:
                return False, "Heal action must specify a target"
            
            if game_state.witch_heal_used:
                return False, "Witch has already used heal potion"
                
            if action.target_agent_id != game_state.killed_this_night:
                return False, "Can only heal the agent killed this night"

        elif action.action_type == ActionType.POISON:
            if not action.target_agent_id:
                return False, "Poison action must specify a target"
                
            if game_state.witch_poison_used:
                return False, "Witch has already used poison potion"
                
            if action.target_agent_id not in game_state.alive_agent_ids:
                return False, "Can only poison living agents"

        return True, None

    @staticmethod
    def _validate_hunter_shoot(
        action: WerewolfAction,
        game_state: GameState,
        agent_role: AgentRole
    ) -> tuple[bool, Optional[str]]:
        """Validate hunter shoot action when eliminated"""
        if agent_role != AgentRole.HUNTER:
            return False, "Only hunters can shoot"
            
        if action.action_type != ActionType.SHOOT:
            return False, "Hunter can only shoot when eliminated"
            
        if not action.target_agent_id:
            return False, "Shoot action must specify a target"
            
        if action.target_agent_id not in game_state.alive_agent_ids:
            return False, "Can only shoot living agents"
            
        if action.agent_id != game_state.hunter_eliminated:
            return False, "Only the eliminated hunter can shoot"
            
        return True, None

    @staticmethod
    def check_game_end_condition(game_state: GameState) -> tuple[bool, Optional[str]]:
        """
        Check if the game has ended.
        Returns (game_ended, winner)
        """
        alive_agents = game_state.alive_agent_ids
        if not alive_agents:
            return True, "draw"

        werewolf_count = 0
        villager_count = 0

        for agent_id in alive_agents:
            role = game_state.role_assignments.get(agent_id)
            if role == AgentRole.WEREWOLF.value:
                werewolf_count += 1
            else:
                villager_count += 1

        # Werewolves win if they equal or outnumber villagers
        if werewolf_count >= villager_count:
            return True, "werewolves"

        # Villagers win if all werewolves are eliminated
        if werewolf_count == 0:
            return True, "villagers"

        # Check if max rounds reached - game ends but no winner declared (only if max_rounds is set)
        if game_state.config.max_rounds is not None and game_state.round_number >= game_state.config.max_rounds:
            return True, None  # No winner when max rounds reached

        return False, None