"""Agent models for Werewolf Benchmark"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime


class AgentRole(str, Enum):
    """Possible roles in Werewolf game"""
    VILLAGER = "villager"
    WEREWOLF = "werewolf"
    SEER = "seer"
    DOCTOR = "doctor"
    HUNTER = "hunter"
    WITCH = "witch"


class ActionType(str, Enum):
    """Types of actions agents can take"""
    VOTE = "vote"
    KILL = "kill"
    INVESTIGATE = "investigate"
    PROTECT = "protect"
    SHOOT = "shoot"
    HEAL = "heal"
    POISON = "poison"
    DISCUSS = "discuss"
    PASS = "pass"


class DiscussionActionType(str, Enum):
    """Sub-actions that can be taken during discussion phase"""
    GENERAL_DISCUSSION = "general_discussion"
    REVEAL_IDENTITY = "reveal_identity"  # Everyone can reveal their own role
    REVEAL_INVESTIGATION = "reveal_investigation"  # Seer only - reveal investigation results
    REVEAL_HEALED_KILLED = "reveal_healed_killed"  # Witch only - reveal who was healed/killed
    REVEAL_PROTECTED = "reveal_protected"  # Doctor only - reveal who they protected
    ACCUSE = "accuse"  # Everyone can accuse others
    DEFEND = "defend"  # Everyone can defend themselves or others
    CLAIM_ROLE = "claim_role"  # Everyone can claim to have a role (true or false)
    REVEAL_WEREWOLF = "reveal_werewolf"  # Werewolves can reveal other werewolves (rare)
    LAST_WORDS = "last_words"  # Last words after elimination at night


class WerewolfAction(BaseModel):
    """Action taken by an agent in the game"""
    agent_id: str = Field(..., description="ID of the agent taking the action")
    action_type: ActionType = Field(..., description="Type of action being taken")
    target_agent_id: Optional[str] = Field(None, description="ID of the target agent (if applicable)")
    reasoning: str = Field(..., description="Agent's reasoning for this action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Agent's confidence in this action")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional action metadata")
    
    # Discussion sub-actions - now supports multiple subactions per speech
    # For backward compatibility, single values are still supported
    discussion_action_type: Optional[DiscussionActionType] = Field(None, description="Sub-action type for discussion (deprecated: use discussion_subactions)")
    discussion_subactions: Optional[List[DiscussionActionType]] = Field(None, description="List of sub-action types for discussion (allows multiple per speech)")
    discussion_content: Optional[str] = Field(None, description="Content of the discussion message")
    # discussion_targets: List[List[str]] - each subaction can have multiple targets
    # Example: [accuse, defend] with [[agent1, agent2], [agent3]] means accuse both agent1 and agent2, defend agent3
    discussion_targets: Optional[List[List[str]]] = Field(None, description="List of target lists for each subaction (allows multiple targets per subaction)")
    revealed_information: Optional[Dict[str, Any]] = Field(None, description="Information revealed during discussion")
    claimed_role: Optional[str] = Field(None, description="Role claimed during discussion (for claim_role action)")
    
    def get_discussion_subactions(self) -> List[DiscussionActionType]:
        """Get list of discussion subactions, handling backward compatibility."""
        if self.discussion_subactions:
            return self.discussion_subactions
        elif self.discussion_action_type:
            return [self.discussion_action_type]
        return []
    
    def get_discussion_targets(self) -> List[List[str]]:
        """Get list of target lists for discussion subactions, handling backward compatibility."""
        if self.discussion_targets:
            # Handle both old format (List[Optional[str]]) and new format (List[List[str]])
            result = []
            for t in self.discussion_targets:
                if isinstance(t, list):
                    result.append([x for x in t if x])  # Filter out None values
                elif isinstance(t, str) and t:
                    result.append([t])
                else:
                    result.append([])
            return result
        elif self.target_agent_id:
            return [[self.target_agent_id]]
        return []


class AgentProfile(BaseModel):
    """Profile of a participating agent"""
    agent_id: str = Field(..., description="Unique identifier for the agent")
    agent_url: HttpUrl = Field(..., description="URL endpoint for the agent")
    name: str = Field(..., description="Display name of the agent")
    role: Optional[AgentRole] = Field(None, description="Assigned role in the game")
    is_alive: bool = Field(True, description="Whether the agent is still in the game")
    last_action: Optional[WerewolfAction] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model: Optional[str] = Field(None, description="LLM model used by this agent (if applicable)")


class AgentResponse(BaseModel):
    """Response from a white agent when queried for action"""
    action: WerewolfAction
    game_understanding: Dict[str, Any] = Field(
        default_factory=dict,
        description="Agent's current understanding of game state"
    )
    suspicions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Agent's suspicions about other players"
    )