"""Response Formatter for White Agent - formats LLM output into valid actions."""

import logging
import re
import random
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Formats LLM responses into valid Werewolf action format."""
    
    # Action type mappings
    ACTION_TYPES = {
        "vote": "vote",
        "kill": "kill",
        "investigate": "investigate",
        "protect": "protect",
        "shoot": "shoot",
        "heal": "heal",
        "poison": "poison",
        "discuss": "discuss",
        "pass": "pass",
    }
    
    # Discussion sub-action types
    DISCUSSION_TYPES = {
        "general": "general_discussion",
        "general_discussion": "general_discussion",
        "reveal_identity": "reveal_identity",
        "reveal_investigation": "reveal_investigation",
        "reveal_healed_killed": "reveal_healed_killed",
        "reveal_protected": "reveal_protected",
        "accuse": "accuse",
        "defend": "defend",
        "claim_role": "claim_role",
        "reveal_werewolf": "reveal_werewolf",
    }
    
    @staticmethod
    def format_action_response(
        llm_response: str,
        phase: str,
        your_role: str,
        alive_agents: List[str],
        game_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Format LLM response into valid AgentResponse format.
        
        Args:
            llm_response: Raw LLM response text (may contain [FALLBACK] prefix)
            phase: Current game phase
            your_role: Agent's assigned role
            alive_agents: List of alive agent IDs
            game_state: Current game state
            
        Returns:
            Formatted AgentResponse dictionary
        """
        # Check if this is a fallback response
        is_fallback = llm_response.startswith("[FALLBACK]")
        if is_fallback:
            llm_response = llm_response[11:]  # Remove "[FALLBACK]" prefix
            logger.warning("Processing fallback response (LLM unavailable)")
        
        # Parse the LLM response
        parsed = ResponseFormatter._parse_llm_response(llm_response)
        
        # Get action type (with validation)
        action_type = ResponseFormatter._get_valid_action_type(
            parsed.get("action", ""),
            phase,
            your_role
        )
        
        # Get target (with validation)
        target = ResponseFormatter._get_valid_target(
            parsed.get("target"),
            action_type,
            phase,
            your_role,
            alive_agents,
            game_state
        )
        
        # Get reasoning
        reasoning = parsed.get("reasoning", "Strategic decision based on game state.")
        if len(reasoning) > 200:
            reasoning = reasoning[:197] + "..."
        
        # Build the action payload
        action = {
            "agent_id": game_state.get("your_agent_id", ""),  # Will be set by orchestrator
            "action_type": action_type,
            "target_agent_id": target,
            "reasoning": reasoning,
            "confidence": ResponseFormatter._calculate_confidence(parsed),
            "metadata": {"source": "fallback" if is_fallback else "llm"},
        }
        
        # Add discussion-specific fields if applicable
        if action_type == "discuss":
            discussion_fields = ResponseFormatter._format_discussion_action(
                parsed,
                your_role,
                game_state
            )
            action.update(discussion_fields)
        
        # Build full response
        return {
            "action": action,
            "game_understanding": {
                "phase": phase,
                "alive_agents": alive_agents,
                "role_awareness": your_role,
            },
            "suspicions": ResponseFormatter._extract_suspicions(parsed, alive_agents),
        }
    
    @staticmethod
    def _parse_llm_response(response: str) -> Dict[str, Any]:
        """
        Parse structured LLM response into components.
        
        Expected format:
        ACTION: [action_type]
        TARGET: [target or none]
        REASONING: [explanation]
        
        Also handles free-form responses.
        """
        parsed = {}
        
        # Try structured format first
        action_match = re.search(r'ACTION:\s*(\w+)', response, re.IGNORECASE)
        target_match = re.search(r'TARGET:\s*(\S+)', response, re.IGNORECASE)
        reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z]+:|$)', response, re.IGNORECASE | re.DOTALL)
        
        if action_match:
            parsed["action"] = action_match.group(1).lower()
        
        if target_match:
            target = target_match.group(1).lower()
            if target not in ["none", "n/a", "-", ""]:
                parsed["target"] = target_match.group(1)
        
        if reasoning_match:
            parsed["reasoning"] = reasoning_match.group(1).strip()
        
        # If no structured format, try to extract from free-form
        if "action" not in parsed:
            parsed["action"] = ResponseFormatter._extract_action_from_text(response)
        
        if "target" not in parsed:
            parsed["target"] = ResponseFormatter._extract_target_from_text(response)
            
        if "reasoning" not in parsed:
            parsed["reasoning"] = response[:200] if response else "No reasoning provided."
        
        # Extract discussion content if present
        content_match = re.search(r'CONTENT:\s*(.+?)(?=\n[A-Z]+:|$)', response, re.IGNORECASE | re.DOTALL)
        if content_match:
            parsed["discussion_content"] = content_match.group(1).strip()
        
        # Extract discussion type
        disc_type_match = re.search(r'DISCUSSION_TYPE:\s*(\w+)', response, re.IGNORECASE)
        if disc_type_match:
            parsed["discussion_type"] = disc_type_match.group(1).lower()
            
        return parsed
    
    @staticmethod
    def _extract_action_from_text(text: str) -> str:
        """Extract action type from free-form text."""
        text_lower = text.lower()
        
        # Check for action keywords
        if any(word in text_lower for word in ["vote for", "voting for", "i vote"]):
            return "vote"
        if any(word in text_lower for word in ["kill", "attack", "eliminate tonight"]):
            return "kill"
        if any(word in text_lower for word in ["investigate", "check", "look at"]):
            return "investigate"
        if any(word in text_lower for word in ["protect", "save", "guard"]):
            return "protect"
        if any(word in text_lower for word in ["heal", "use heal"]):
            return "heal"
        if any(word in text_lower for word in ["poison", "use poison"]):
            return "poison"
        if any(word in text_lower for word in ["discuss", "think", "believe", "suspect"]):
            return "discuss"
        if any(word in text_lower for word in ["pass", "skip", "do nothing"]):
            return "pass"
            
        return "pass"  # Default
    
    @staticmethod
    def _extract_target_from_text(text: str) -> Optional[str]:
        """Extract target agent from free-form text."""
        # Look for agent_X pattern
        agent_match = re.search(r'agent[_\s]?(\d+)', text, re.IGNORECASE)
        if agent_match:
            return f"agent_{agent_match.group(1)}"
        
        # Look for "Player X" pattern
        player_match = re.search(r'player[_\s]?(\d+)', text, re.IGNORECASE)
        if player_match:
            return f"agent_{player_match.group(1)}"
            
        return None
    
    @staticmethod
    def _get_valid_action_type(
        parsed_action: str,
        phase: str,
        role: str
    ) -> str:
        """
        Validate and correct action type based on phase and role.
        """
        # Map to canonical action type
        action = ResponseFormatter.ACTION_TYPES.get(parsed_action.lower(), "pass")
        
        # Phase-specific validation
        valid_actions = {
            "day_discussion": ["discuss", "pass"],
            "day_voting": ["vote"],
            "night_werewolf": ["kill", "pass"] if role == "werewolf" else ["pass"],
            "night_seer": ["investigate", "pass"] if role == "seer" else ["pass"],
            "night_doctor": ["protect", "pass"] if role == "doctor" else ["pass"],
            "night_witch": ["heal", "poison", "pass"] if role == "witch" else ["pass"],
        }
        
        allowed = valid_actions.get(phase, ["pass"])
        
        if action not in allowed:
            logger.warning(f"Invalid action '{action}' for phase '{phase}', role '{role}'. Using default.")
            return allowed[0] if allowed else "pass"
            
        return action
    
    @staticmethod
    def _get_valid_target(
        parsed_target: Optional[str],
        action_type: str,
        phase: str,
        role: str,
        alive_agents: List[str],
        game_state: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate and correct target based on action and game state.
        """
        # Actions that don't need targets
        if action_type in ["pass", "discuss"]:
            return None
            
        # If no target parsed but one is needed, select randomly
        if not parsed_target:
            valid_targets = ResponseFormatter._get_valid_targets(
                action_type, role, alive_agents, game_state
            )
            if valid_targets:
                return random.choice(valid_targets)
            return None
        
        # Normalize target format
        target = parsed_target
        if not target.startswith("agent_"):
            # Try to extract agent number
            match = re.search(r'\d+', target)
            if match:
                target = f"agent_{match.group()}"
        
        # Validate target is alive and valid
        valid_targets = ResponseFormatter._get_valid_targets(
            action_type, role, alive_agents, game_state
        )
        
        if target in valid_targets:
            return target
        elif valid_targets:
            logger.warning(f"Target '{target}' invalid, selecting random valid target.")
            return random.choice(valid_targets)
        
        return None
    
    @staticmethod
    def _get_valid_targets(
        action_type: str,
        role: str,
        alive_agents: List[str],
        game_state: Dict[str, Any]
    ) -> List[str]:
        """Get list of valid targets for an action."""
        own_id = game_state.get("your_agent_id")
        targets = [a for a in alive_agents if a != own_id]
        
        # Werewolves can't kill teammates
        if action_type == "kill" and role == "werewolf":
            teammates = game_state.get("werewolf_teammates", [])
            targets = [t for t in targets if t not in teammates]
        
        # Witch heal can only target killed player
        if action_type == "heal":
            killed = game_state.get("killed_this_night")
            if killed:
                return [killed]
            return []
            
        return targets
    
    @staticmethod
    def _calculate_confidence(parsed: Dict[str, Any]) -> float:
        """Calculate confidence score based on parsed response quality."""
        confidence = 0.5
        
        # Increase if we got clear action
        if parsed.get("action"):
            confidence += 0.2
            
        # Increase if we got clear reasoning
        if parsed.get("reasoning") and len(parsed["reasoning"]) > 20:
            confidence += 0.2
            
        # Increase if we got clear target (when needed)
        if parsed.get("target"):
            confidence += 0.1
            
        return min(confidence, 1.0)
    
    @staticmethod
    def _format_discussion_action(
        parsed: Dict[str, Any],
        role: str,
        game_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Format discussion-specific action fields."""
        fields = {}
        
        # Get discussion type
        disc_type = parsed.get("discussion_type", "general_discussion")
        canonical_type = ResponseFormatter.DISCUSSION_TYPES.get(disc_type, "general_discussion")
        fields["discussion_action_type"] = canonical_type
        
        # Get discussion content
        content = parsed.get("discussion_content") or parsed.get("reasoning", "")
        fields["discussion_content"] = content[:300]  # Limit for cost savings
        
        # Add claimed role if claiming
        if canonical_type == "claim_role":
            fields["claimed_role"] = role  # Claim true role by default
            
        return fields
    
    @staticmethod
    def _extract_suspicions(
        parsed: Dict[str, Any],
        alive_agents: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract suspicion information from parsed response."""
        suspicions = []
        
        reasoning = parsed.get("reasoning", "")
        target = parsed.get("target")
        
        if target and target in alive_agents:
            suspicions.append({
                "agent_id": target,
                "suspicion_level": 0.6,
                "reason": "Mentioned in reasoning",
            })
            
        return suspicions

