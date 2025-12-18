"""
Error Handler for Werewolf Game.

This module provides comprehensive error handling for various failure scenarios
that can occur during gameplay, particularly with White Agent interactions.
"""

import logging
import random
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum

from app.types.agent import WerewolfAction, ActionType, AgentRole
from app.types.game import GameState, GamePhase

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """Types of errors that can occur during gameplay."""
    
    # Communication errors
    NETWORK_TIMEOUT = "network_timeout"
    CONNECTION_REFUSED = "connection_refused"
    INVALID_JSON = "invalid_json"
    
    # Response parsing errors
    MISSING_ACTION = "missing_action"
    INVALID_ACTION_TYPE = "invalid_action_type"
    MISSING_TARGET = "missing_target"
    MALFORMED_RESPONSE = "malformed_response"
    
    # Rule violations
    WRONG_PHASE_ACTION = "wrong_phase_action"
    INVALID_TARGET = "invalid_target"
    DEAD_AGENT_ACTION = "dead_agent_action"
    SELF_TARGET = "self_target"
    TEAMMATE_TARGET = "teammate_target"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    
    # System errors
    UNKNOWN_ERROR = "unknown_error"


class ErrorHandler:
    """Handles errors during Werewolf gameplay."""
    
    # Mapping of error types to recovery strategies
    RECOVERY_STRATEGIES = {
        ErrorType.NETWORK_TIMEOUT: "fallback_pass",
        ErrorType.CONNECTION_REFUSED: "fallback_pass",
        ErrorType.INVALID_JSON: "retry_once_then_fallback",
        ErrorType.MISSING_ACTION: "fallback_pass",
        ErrorType.INVALID_ACTION_TYPE: "correct_action_type",
        ErrorType.MISSING_TARGET: "random_valid_target",
        ErrorType.MALFORMED_RESPONSE: "fallback_pass",
        ErrorType.WRONG_PHASE_ACTION: "correct_action_type",
        ErrorType.INVALID_TARGET: "random_valid_target",
        ErrorType.DEAD_AGENT_ACTION: "skip_agent",
        ErrorType.SELF_TARGET: "random_valid_target",
        ErrorType.TEAMMATE_TARGET: "random_valid_target",
        ErrorType.RESOURCE_EXHAUSTED: "fallback_pass",
        ErrorType.UNKNOWN_ERROR: "fallback_pass",
    }
    
    @staticmethod
    def classify_error(error: Exception, context: Dict[str, Any] = None) -> ErrorType:
        """
        Classify an exception into an ErrorType.
        
        Args:
            error: The exception that occurred
            context: Additional context about the error
            
        Returns:
            Classified ErrorType
        """
        error_str = str(error).lower()
        
        # Network errors
        if "timeout" in error_str:
            return ErrorType.NETWORK_TIMEOUT
        if "connection" in error_str and "refused" in error_str:
            return ErrorType.CONNECTION_REFUSED
        
        # JSON errors
        if "json" in error_str or "decode" in error_str:
            return ErrorType.INVALID_JSON
        
        # Validation errors
        if "missing" in error_str:
            if "action" in error_str:
                return ErrorType.MISSING_ACTION
            if "target" in error_str:
                return ErrorType.MISSING_TARGET
        
        if "invalid" in error_str:
            if "action" in error_str or "type" in error_str:
                return ErrorType.INVALID_ACTION_TYPE
            if "target" in error_str:
                return ErrorType.INVALID_TARGET
        
        return ErrorType.UNKNOWN_ERROR
    
    @staticmethod
    def classify_validation_error(error_msg: str) -> ErrorType:
        """
        Classify a validation error message from the RulesValidator.
        
        Args:
            error_msg: Error message from validation
            
        Returns:
            Classified ErrorType
        """
        error_lower = error_msg.lower()
        
        if "dead" in error_lower:
            return ErrorType.DEAD_AGENT_ACTION
        if "yourself" in error_lower or "self" in error_lower:
            return ErrorType.SELF_TARGET
        if "werewolf" in error_lower and ("kill" in error_lower or "teammate" in error_lower):
            return ErrorType.TEAMMATE_TARGET
        if "only" in error_lower or "cannot" in error_lower or "not allowed" in error_lower:
            return ErrorType.WRONG_PHASE_ACTION
        if "target" in error_lower and ("not" in error_lower or "invalid" in error_lower):
            return ErrorType.INVALID_TARGET
        if "used" in error_lower or "exhausted" in error_lower:
            return ErrorType.RESOURCE_EXHAUSTED
        
        return ErrorType.UNKNOWN_ERROR
    
    @staticmethod
    def get_recovery_action(
        error_type: ErrorType,
        game_state: GameState,
        agent_id: str,
        original_action: Optional[WerewolfAction] = None
    ) -> Optional[WerewolfAction]:
        """
        Get a recovery action for an error.
        
        Args:
            error_type: Type of error that occurred
            game_state: Current game state
            agent_id: ID of the agent that had the error
            original_action: The original action that failed (if any)
            
        Returns:
            Recovery action, or None if no recovery possible
        """
        strategy = ErrorHandler.RECOVERY_STRATEGIES.get(error_type, "fallback_pass")
        
        if strategy == "skip_agent":
            # Dead agents don't take actions
            return None
        
        if strategy == "fallback_pass":
            return WerewolfAction(
                agent_id=agent_id,
                action_type=ActionType.PASS,
                reasoning=f"Fallback action due to error: {error_type.value}",
                confidence=0.0
            )
        
        if strategy == "correct_action_type":
            # Determine correct action type for phase
            correct_type = ErrorHandler._get_correct_action_type(game_state, agent_id)
            
            if correct_type == ActionType.PASS:
                return WerewolfAction(
                    agent_id=agent_id,
                    action_type=ActionType.PASS,
                    reasoning=f"Corrected action type due to error",
                    confidence=0.1
                )
            
            # Get a valid target
            target = ErrorHandler._get_random_valid_target(game_state, agent_id, correct_type)
            
            return WerewolfAction(
                agent_id=agent_id,
                action_type=correct_type,
                target_agent_id=target,
                reasoning=f"Corrected action due to {error_type.value}",
                confidence=0.1
            )
        
        if strategy == "random_valid_target":
            if original_action:
                action_type = original_action.action_type
            else:
                action_type = ErrorHandler._get_correct_action_type(game_state, agent_id)
            
            target = ErrorHandler._get_random_valid_target(game_state, agent_id, action_type)
            
            if target:
                return WerewolfAction(
                    agent_id=agent_id,
                    action_type=action_type,
                    target_agent_id=target,
                    reasoning=f"Random target selected due to {error_type.value}",
                    confidence=0.1
                )
            else:
                # No valid targets, pass instead
                return WerewolfAction(
                    agent_id=agent_id,
                    action_type=ActionType.PASS,
                    reasoning=f"No valid targets available",
                    confidence=0.0
                )
        
        # Default fallback
        return WerewolfAction(
            agent_id=agent_id,
            action_type=ActionType.PASS,
            reasoning=f"Default fallback for {error_type.value}",
            confidence=0.0
        )
    
    @staticmethod
    def _get_correct_action_type(game_state: GameState, agent_id: str) -> ActionType:
        """Get the correct action type for an agent in the current phase."""
        phase = game_state.phase
        role_str = game_state.role_assignments.get(agent_id)
        role = AgentRole(role_str) if role_str else AgentRole.VILLAGER
        
        if phase == GamePhase.DAY_DISCUSSION:
            return ActionType.DISCUSS
        elif phase == GamePhase.DAY_VOTING:
            return ActionType.VOTE
        elif phase == GamePhase.NIGHT_WEREWOLF:
            return ActionType.KILL if role == AgentRole.WEREWOLF else ActionType.PASS
        elif phase == GamePhase.NIGHT_SEER:
            return ActionType.INVESTIGATE if role == AgentRole.SEER else ActionType.PASS
        elif phase == GamePhase.NIGHT_DOCTOR:
            return ActionType.PROTECT if role == AgentRole.DOCTOR else ActionType.PASS
        elif phase == GamePhase.NIGHT_WITCH:
            return ActionType.PASS  # Witch chooses between heal/poison/pass
        
        return ActionType.PASS
    
    @staticmethod
    def _get_random_valid_target(
        game_state: GameState,
        agent_id: str,
        action_type: ActionType
    ) -> Optional[str]:
        """Get a random valid target for an action."""
        alive = game_state.alive_agent_ids
        role_str = game_state.role_assignments.get(agent_id)
        
        # Exclude self
        valid_targets = [aid for aid in alive if aid != agent_id]
        
        # Werewolves can't target teammates
        if action_type == ActionType.KILL and role_str == AgentRole.WEREWOLF.value:
            valid_targets = [
                aid for aid in valid_targets
                if game_state.role_assignments.get(aid) != AgentRole.WEREWOLF.value
            ]
        
        # Witch heal can only target killed player
        if action_type == ActionType.HEAL:
            killed = game_state.killed_this_night
            return killed if killed and killed in alive else None
        
        return random.choice(valid_targets) if valid_targets else None
    
    @staticmethod
    def format_error_log(
        error_type: ErrorType,
        agent_id: str,
        phase: str,
        round_number: int,
        details: str = None
    ) -> Dict[str, Any]:
        """
        Format an error for logging.
        
        Args:
            error_type: Type of error
            agent_id: Agent that had the error
            phase: Current game phase
            round_number: Current round number
            details: Additional error details
            
        Returns:
            Formatted error log dictionary
        """
        return {
            "error_type": error_type.value,
            "agent_id": agent_id,
            "phase": phase,
            "round_number": round_number,
            "details": details,
            "recovery_strategy": ErrorHandler.RECOVERY_STRATEGIES.get(error_type, "unknown"),
            "severity": ErrorHandler._get_severity(error_type),
        }
    
    @staticmethod
    def _get_severity(error_type: ErrorType) -> str:
        """Get severity level for an error type."""
        high_severity = {
            ErrorType.CONNECTION_REFUSED,
            ErrorType.DEAD_AGENT_ACTION,
        }
        
        medium_severity = {
            ErrorType.NETWORK_TIMEOUT,
            ErrorType.INVALID_JSON,
            ErrorType.MALFORMED_RESPONSE,
        }
        
        if error_type in high_severity:
            return "high"
        elif error_type in medium_severity:
            return "medium"
        else:
            return "low"

