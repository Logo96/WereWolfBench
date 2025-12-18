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
        "last_words": "last_words",
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
        # No truncation - preserve full reasoning for logging
        
        # Build the action payload
        # Get agent_id from game_state if available, otherwise empty (orchestrator will set it)
        agent_id = game_state.get("your_agent_id", "")
        action = {
            "agent_id": agent_id,
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
            parsed["reasoning"] = response if response else "No reasoning provided."
        
        # Extract discussion content if present
        content_match = re.search(r'CONTENT:\s*(.+?)(?=\n[A-Z]+:|$)', response, re.IGNORECASE | re.DOTALL)
        if content_match:
            parsed["discussion_content"] = content_match.group(1).strip()
        
        # Extract discussion type (backward compatibility)
        disc_type_match = re.search(r'DISCUSSION_TYPE:\s*(\w+)', response, re.IGNORECASE)
        if disc_type_match:
            parsed["discussion_type"] = disc_type_match.group(1).lower()
        
        # Extract multiple discussion subactions
        subactions_match = re.search(r'DISCUSSION_SUBACTIONS:\s*(\[.*?\])', response, re.IGNORECASE)
        if subactions_match:
            subactions_str = subactions_match.group(1)
            try:
                # Try to parse as JSON first (most reliable)
                import json
                parsed_subactions = json.loads(subactions_str)
                if isinstance(parsed_subactions, list):
                    # Remove duplicates and clean up
                    parsed["discussion_subactions"] = [
                        str(s).strip().lower().strip('"').strip("'") 
                        for s in parsed_subactions 
                        if s and str(s).strip()
                    ]
                    # Remove duplicates while preserving order
                    seen = set()
                    unique_subactions = []
                    for s in parsed["discussion_subactions"]:
                        if s not in seen:
                            seen.add(s)
                            unique_subactions.append(s)
                    parsed["discussion_subactions"] = unique_subactions
                else:
                    parsed["discussion_subactions"] = []
            except (json.JSONDecodeError, ValueError):
                # Fallback to regex parsing if JSON fails
                subactions_str = subactions_match.group(1).strip('[]')
                parsed["discussion_subactions"] = [
                    s.strip().lower().strip('"').strip("'") 
                    for s in subactions_str.split(',') 
                    if s.strip()
                ]
                # Remove duplicates
                seen = set()
                unique_subactions = []
                for s in parsed["discussion_subactions"]:
                    if s not in seen:
                        seen.add(s)
                        unique_subactions.append(s)
                parsed["discussion_subactions"] = unique_subactions
        
        # Extract multiple discussion targets (can be list of lists)
        # Use a more robust regex that handles nested brackets
        targets_match = re.search(r'DISCUSSION_TARGETS:\s*(\[.*?\])', response, re.IGNORECASE | re.DOTALL)
        if targets_match:
            targets_str = targets_match.group(1)
            try:
                # Try to parse as JSON first (most reliable)
                import json
                parsed_targets = json.loads(targets_str)
                if isinstance(parsed_targets, list):
                    # Ensure it's a list of lists
                    formatted_targets = []
                    for item in parsed_targets:
                        if isinstance(item, list):
                            # Filter out invalid values
                            formatted_targets.append([
                                str(t).strip() for t in item 
                                if t and str(t).strip().lower() not in ['none', 'n/a', '-', '']
                            ])
                        elif item and str(item).strip().lower() not in ['none', 'n/a', '-', '']:
                            # Single item - wrap in list
                            formatted_targets.append([str(item).strip()])
                        else:
                            formatted_targets.append([])
                    parsed["discussion_targets"] = formatted_targets
                else:
                    parsed["discussion_targets"] = []
            except (json.JSONDecodeError, ValueError):
                # Fallback to regex parsing if JSON fails
                # Try to match nested brackets more carefully
                nested_match = re.findall(r'\[([^\]]*)\]', targets_str)
                if nested_match:
                    # Found nested lists
                    formatted_targets = []
                    for group in nested_match:
                        # Clean up the group - remove quotes and whitespace
                        cleaned_group = group.strip().strip('"').strip("'")
                        if cleaned_group:
                            # Split by comma and clean each item
                            items = [t.strip().strip('"').strip("'") for t in cleaned_group.split(',') if t.strip()]
                            formatted_targets.append([
                                t for t in items 
                                if t.lower() not in ['none', 'n/a', '-', '']
                            ])
                        else:
                            formatted_targets.append([])
                    parsed["discussion_targets"] = formatted_targets
                else:
                    # Fallback: single list format
                    parsed["discussion_targets"] = [
                        [t.strip().strip('"').strip("'")] 
                        if t.strip() and t.strip().lower() not in ['none', 'n/a', '-', ''] 
                        else []
                        for t in targets_str.split(',')
                    ]
            
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
    def _extract_all_targets_from_text(text: str) -> List[str]:
        """Extract all target agents from free-form text."""
        targets = []
        # Find all agent_X patterns
        agent_matches = re.findall(r'agent[_\s]?(\d+)', text, re.IGNORECASE)
        for match in agent_matches:
            agent_id = f"agent_{match}"
            if agent_id not in targets:
                targets.append(agent_id)
        
        # Also look for "Player X" patterns
        player_matches = re.findall(r'player[_\s]?(\d+)', text, re.IGNORECASE)
        for match in player_matches:
            agent_id = f"agent_{match}"
            if agent_id not in targets:
                targets.append(agent_id)
        
        return targets
    
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
        """Format discussion-specific action fields, supporting multiple subactions."""
        fields = {}
        
        # Support multiple discussion subactions - STRICTLY REQUIRE STRUCTURED FORMAT
        discussion_subactions = parsed.get("discussion_subactions", [])
        discussion_targets = parsed.get("discussion_targets", [])

        # If no structured subactions provided, default to general_discussion
        # This prevents keyword gaming but allows natural responses
        if not discussion_subactions:
            discussion_subactions = ["general_discussion"]
            discussion_targets = [[]]
        
        # Only use keyword extraction if no structured subactions provided
        # This prevents gaming the keyword detection system
        if not discussion_subactions or (len(discussion_subactions) == 1 and discussion_subactions[0] == "general_discussion"):
            # Try to extract multiple subactions from reasoning/content as fallback
            content = parsed.get("discussion_content") or parsed.get("reasoning", "")
            extracted_subactions = ResponseFormatter._extract_multiple_subactions(content)
            if extracted_subactions and len(extracted_subactions) > 1:  # Only use if multiple actions detected
                discussion_subactions = extracted_subactions
                # Extract targets for each subaction (returns List[List[str]])
                discussion_targets = ResponseFormatter._extract_targets_for_subactions(content, discussion_subactions)
        
        # Convert to canonical types
        canonical_types = []
        for disc_type in discussion_subactions:
            canonical = ResponseFormatter.DISCUSSION_TYPES.get(disc_type.lower(), "general_discussion")
            canonical_types.append(canonical)
        
        # Ensure discussion_targets is a list of lists
        if not discussion_targets:
            discussion_targets = [[] for _ in canonical_types]
        else:
            # Convert to list of lists format
            formatted_targets = []
            for i, targets in enumerate(discussion_targets):
                if isinstance(targets, list):
                    # Already a list - filter out None/empty
                    formatted_targets.append([t for t in targets if t])
                elif isinstance(targets, str) and targets:
                    # Single string - wrap in list
                    formatted_targets.append([targets])
                else:
                    # None or empty - empty list
                    formatted_targets.append([])
            discussion_targets = formatted_targets
        
        # Ensure targets list matches subactions list length
        while len(discussion_targets) < len(canonical_types):
            discussion_targets.append([])
        discussion_targets = discussion_targets[:len(canonical_types)]
        
        # CRITICAL: general_discussion should NEVER have targets - remove any targets assigned to it
        for i, subaction_type in enumerate(canonical_types):
            if subaction_type == "general_discussion":
                discussion_targets[i] = []
        
        # Extract targets from content if missing and we have target-required actions
        # This is a fallback - the prompt should make it clear targets are required
        target_required_subactions = [
            "accuse", "defend", "reveal_investigation", 
            "reveal_protected", "reveal_werewolf"
        ]
        for i, subaction_type in enumerate(canonical_types):
            if subaction_type in target_required_subactions and not discussion_targets[i]:
                # Try to extract targets from content as fallback
                content = parsed.get("discussion_content") or parsed.get("reasoning", "")
                extracted = ResponseFormatter._extract_all_targets_from_text(content)
                if extracted:
                    discussion_targets[i] = extracted
                    logger.warning(f"Extracted targets {extracted} from content for {subaction_type} subaction - targets should be explicitly provided!")
                else:
                    logger.warning(f"WARNING: {subaction_type} subaction requires targets but none provided! Action may be invalid.")
        
        # Set fields - use new list-based format
        fields["discussion_subactions"] = canonical_types
        fields["discussion_targets"] = discussion_targets
        
        # Backward compatibility: also set single value
        fields["discussion_action_type"] = canonical_types[0] if canonical_types else "general_discussion"
        
        # Get discussion content
        content = parsed.get("discussion_content") or parsed.get("reasoning", "")
        fields["discussion_content"] = content  # No truncation - preserve full content for logging
        
        # Add claimed role if claiming
        if "claim_role" in canonical_types:
            fields["claimed_role"] = role  # Claim true role by default
            
        return fields
    
    @staticmethod
    def _extract_multiple_subactions(content: str) -> List[str]:
        """Extract multiple discussion subactions from text."""
        content_lower = content.lower()
        subactions = []
        
        # Check for multiple subaction keywords
        if "accuse" in content_lower or "accusing" in content_lower:
            subactions.append("accuse")
        if "defend" in content_lower or "defending" in content_lower:
            subactions.append("defend")
        if "reveal" in content_lower and "identity" in content_lower:
            subactions.append("reveal_identity")
        if "claim" in content_lower and "role" in content_lower:
            subactions.append("claim_role")
        if "last word" in content_lower or "last words" in content_lower:
            subactions.append("last_words")
        
        return subactions if subactions else ["general_discussion"]
    
    @staticmethod
    def _extract_targets_for_subactions(content: str, subactions: List[str]) -> List[List[str]]:
        """Extract targets for each subaction from content. Returns list of lists (multiple targets per subaction)."""
        targets = []
        
        # Extract all agent mentions
        all_agents = ResponseFormatter._extract_all_targets_from_text(content)
        
        for subaction in subactions:
            if subaction in ["accuse", "defend"]:
                # For accuse/defend, try to extract all mentioned agents
                # This allows multiple targets per subaction
                if all_agents:
                    targets.append(all_agents)
                else:
                    targets.append([])
            else:
                targets.append([])
        
        return targets
    
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

