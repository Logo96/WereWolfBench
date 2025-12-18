"""Game state models for Werewolf Benchmark"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class GamePhase(str, Enum):
    """Phases of the Werewolf game"""
    SETUP = "setup"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTING = "day_voting"
    NIGHT_WEREWOLF = "night_werewolf"
    NIGHT_WITCH = "night_witch"
    NIGHT_SEER = "night_seer"
    NIGHT_DOCTOR = "night_doctor"
    HUNTER_SHOOT = "hunter_shoot"
    GAME_OVER = "game_over"


class GameStatus(str, Enum):
    """Status of the game"""
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GameConfig(BaseModel):
    """Configuration for a Werewolf game"""
    num_werewolves: int = Field(2, ge=1, description="Number of werewolves")
    has_seer: bool = Field(True, description="Whether to include a seer")
    has_doctor: bool = Field(True, description="Whether to include a doctor")
    has_hunter: bool = Field(False, description="Whether to include a hunter")
    has_witch: bool = Field(False, description="Whether to include a witch")
    discussion_time_limit: int = Field(300, description="Time limit for discussion in seconds")
    voting_time_limit: int = Field(60, description="Time limit for voting in seconds")
    max_rounds: Optional[int] = Field(None, description="Maximum number of rounds before game ends (None = no limit)")


class RoundRecord(BaseModel):
    """Record of a single round in the game"""
    round_number: int
    phase: GamePhase
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    eliminated_agents: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class GameState(BaseModel):
    """Current state of the Werewolf game"""
    game_id: str = Field(..., description="Unique identifier for the game")
    status: GameStatus = Field(GameStatus.WAITING)
    phase: GamePhase = Field(GamePhase.SETUP)
    round_number: int = Field(0, ge=0)

    agent_ids: List[str] = Field(default_factory=list, description="All participating agent IDs")
    alive_agent_ids: List[str] = Field(default_factory=list, description="Currently alive agent IDs")
    eliminated_agent_ids: List[str] = Field(default_factory=list, description="Eliminated agent IDs")

    role_assignments: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of agent_id to role"
    )

    current_votes: Dict[str, str] = Field(
        default_factory=dict,
        description="Current voting state (voter_id -> target_id)"
    )

    # Witch state
    witch_heal_used: bool = Field(False, description="Whether witch has used heal potion")
    witch_poison_used: bool = Field(False, description="Whether witch has used poison potion")
    killed_this_night: Optional[str] = Field(None, description="Agent killed by werewolves this night")

    # Hunter state
    hunter_eliminated: Optional[str] = Field(None, description="Hunter who was eliminated and can shoot")

    # Seer investigation results
    seer_investigations: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Seer investigation results (agent_id -> {target_id: str, is_werewolf: bool, round: int})"
    )

    round_history: List[RoundRecord] = Field(default_factory=list)

    config: GameConfig = Field(default_factory=GameConfig)

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    winner: Optional[str] = Field(None, description="'villagers' or 'werewolves'")

    metadata: Dict[str, Any] = Field(default_factory=dict)


class GameSummary(BaseModel):
    """Summary of a completed game"""
    game_id: str
    winner: str
    total_rounds: int
    surviving_agents: List[str]
    eliminated_agents: List[str]
    duration_seconds: float
    created_at: datetime
    completed_at: datetime