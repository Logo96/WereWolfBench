"""Data types for Werewolf Benchmark"""

from .agent import WerewolfAction, AgentProfile, AgentRole, ActionType, AgentResponse
from .game import GameState, GamePhase, GameConfig, GameStatus

__all__ = [
    # Agent types
    "WerewolfAction",
    "AgentProfile",
    "AgentRole",
    "ActionType",
    "AgentResponse",
    # Game types
    "GameState",
    "GamePhase",
    "GameConfig",
    "GameStatus",
]