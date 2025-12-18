"""Prompt Parser for White Agent - parses incoming prompts from Green Agent."""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class PromptParser:
    """Parses and validates prompts received from the Green Agent."""
    
    @staticmethod
    def parse_task_data(task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and validate task data from Green Agent.
        
        Args:
            task_data: Raw task data dictionary
            
        Returns:
            Parsed and validated task data
        """
        parsed = {
            "game_id": task_data.get("game_id"),
            "phase": task_data.get("phase"),
            "round": task_data.get("round", 1),
            "your_role": task_data.get("your_role"),
            "alive_agents": task_data.get("alive_agents", []),
            "eliminated_agents": task_data.get("eliminated_agents", []),
            "prompt": task_data.get("prompt", ""),
            "game_state": task_data.get("game_state", {}),
            "valid_actions": task_data.get("valid_actions", []),
        }
        
        # Extract role-specific information from game_state
        game_state = parsed["game_state"]
        
        # For werewolves: teammates
        if "werewolf_teammates" in game_state:
            parsed["werewolf_teammates"] = game_state["werewolf_teammates"]
        
        # For witch: potion status and killed player
        if "killed_this_night" in game_state:
            parsed["killed_this_night"] = game_state["killed_this_night"]
        if "heal_available" in game_state:
            parsed["heal_available"] = game_state["heal_available"]
        if "poison_available" in game_state:
            parsed["poison_available"] = game_state["poison_available"]
            
        # For seer: investigation results
        if "investigation_results" in game_state:
            parsed["investigation_results"] = game_state["investigation_results"]
            
        # Public information
        if "discussion_history" in game_state:
            parsed["discussion_history"] = game_state["discussion_history"]
        if "voting_history" in game_state:
            parsed["voting_history"] = game_state["voting_history"]
            
        # Current round discussion (for sequential context)
        if "current_round_discussion" in task_data:
            parsed["current_round_discussion"] = task_data["current_round_discussion"]
            
        return parsed
    
    @staticmethod
    def extract_valid_targets(
        parsed_data: Dict[str, Any],
        exclude_self: bool = True
    ) -> List[str]:
        """
        Extract valid target agents based on phase and role.
        
        Args:
            parsed_data: Parsed task data
            exclude_self: Whether to exclude the agent's own ID
            
        Returns:
            List of valid target agent IDs
        """
        alive = parsed_data.get("alive_agents", [])
        phase = parsed_data.get("phase", "")
        role = parsed_data.get("your_role", "")
        
        # Get agent's own ID from game_state if available
        game_state = parsed_data.get("game_state", {})
        own_id = game_state.get("your_agent_id")
        
        valid_targets = alive.copy()
        
        # Exclude self for voting
        if exclude_self and own_id and own_id in valid_targets:
            valid_targets.remove(own_id)
            
        # Werewolves can't target other werewolves
        if role == "werewolf" and phase == "night_werewolf":
            teammates = parsed_data.get("werewolf_teammates", [])
            valid_targets = [t for t in valid_targets if t not in teammates]
            
        # Seer can't investigate self
        if role == "seer" and phase == "night_seer":
            if own_id and own_id in valid_targets:
                valid_targets.remove(own_id)
                
        return valid_targets
    
    @staticmethod
    def get_required_action_type(phase: str, role: str) -> Optional[str]:
        """
        Get the required action type for the current phase and role.
        
        Args:
            phase: Current game phase
            role: Agent's role
            
        Returns:
            Required action type string, or None if multiple options
        """
        phase_actions = {
            "day_discussion": "discuss",
            "day_voting": "vote",
            "night_werewolf": "kill" if role == "werewolf" else "pass",
            "night_seer": "investigate" if role == "seer" else "pass",
            "night_doctor": "protect" if role == "doctor" else "pass",
            "night_witch": None,  # Witch has multiple options
        }
        
        return phase_actions.get(phase, "pass")

