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


class WerewolfAction(BaseModel):
    """Action taken by an agent in the game"""
    agent_id: str = Field(..., description="ID of the agent taking the action")
    action_type: ActionType = Field(..., description="Type of action being taken")
    target_agent_id: Optional[str] = Field(None, description="ID of the target agent (if applicable)")
    reasoning: str = Field(..., description="Agent's reasoning for this action")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Agent's confidence in this action")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional action metadata")


class AgentProfile(BaseModel):
    """Profile of a participating agent"""
    agent_id: str = Field(..., description="Unique identifier for the agent")
    agent_url: HttpUrl = Field(..., description="URL endpoint for the agent")
    name: str = Field(..., description="Display name of the agent")
    role: Optional[AgentRole] = Field(None, description="Assigned role in the game")
    is_alive: bool = Field(True, description="Whether the agent is still in the game")
    last_action: Optional[WerewolfAction] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


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