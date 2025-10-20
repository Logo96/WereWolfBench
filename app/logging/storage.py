"""Storage system with both in-memory and file persistence for game data"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.types.game import GameState
from app.types.agent import WerewolfAction, AgentProfile

logger = logging.getLogger(__name__)


class GameLogger:
    """Handles game data storage with both in-memory cache and file persistence."""

    def __init__(self, log_dir: str = "game_logs"):
        """Initialize the game logger."""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        self.active_games: Dict[str, GameState] = {}
        self.game_agents: Dict[str, List[AgentProfile]] = {}
        self.game_actions: Dict[str, List[WerewolfAction]] = {}
        self.last_logged_states: Dict[str, Dict[str, Any]] = {}

    def save_game(self, game_state: GameState, force_log: bool = False) -> None:
        """Save or update game state."""
        self.active_games[game_state.game_id] = game_state

        # Check if state has changed or if forced to log
        if force_log or self._has_state_changed(game_state):
            self._write_game_event(game_state.game_id, {
                "event": "game_update",
                "timestamp": datetime.utcnow().isoformat(),
                "game_id": game_state.game_id,
                "status": game_state.status.value,
                "phase": game_state.phase.value,
                "round": game_state.round_number,
                "alive": game_state.alive_agent_ids,
                "eliminated": game_state.eliminated_agent_ids,
                "winner": game_state.winner
            })
            
            # Update the last logged state
            self.last_logged_states[game_state.game_id] = {
                "status": game_state.status.value,
                "phase": game_state.phase.value,
                "round": game_state.round_number,
                "alive": game_state.alive_agent_ids.copy(),
                "eliminated": game_state.eliminated_agent_ids.copy(),
                "winner": game_state.winner
            }

    def get_game(self, game_id: str) -> Optional[GameState]:
        """Get game state by ID from memory."""
        return self.active_games.get(game_id)

    def save_agents(self, game_id: str, agents: List[AgentProfile]) -> None:
        """Save agent profiles for a game."""
        self.game_agents[game_id] = agents

        self._write_game_event(game_id, {
            "event": "agents_assigned",
            "timestamp": datetime.utcnow().isoformat(),
            "game_id": game_id,
            "agents": [
                {
                    "id": agent.agent_id,
                    "name": agent.name,
                    "url": str(agent.agent_url),
                    "role": agent.role.value if agent.role else None
                }
                for agent in agents
            ]
        })

    def get_agents(self, game_id: str) -> List[AgentProfile]:
        """Get all agents in a game."""
        return self.game_agents.get(game_id, [])

    def save_action(self, game_id: str, action: WerewolfAction) -> None:
        """Save an action taken in a game."""
        if game_id not in self.game_actions:
            self.game_actions[game_id] = []
        self.game_actions[game_id].append(action)

        event_data = {
            "event": "action",
            "timestamp": action.timestamp.isoformat(),
            "game_id": game_id,
            "agent_id": action.agent_id,
            "action_type": action.action_type.value,
            "target": action.target_agent_id,
            "confidence": action.confidence,
            "reasoning": action.reasoning
        }
        
        # Add investigation result for seer actions
        if action.action_type.value == "investigate" and action.target_agent_id:
            # Get the game state to determine if target is werewolf
            game_state = self.get_game(game_id)
            if game_state:
                target_role = game_state.role_assignments.get(action.target_agent_id)
                is_werewolf = target_role == "werewolf"
                event_data["investigation_result"] = {
                    "target_id": action.target_agent_id,
                    "is_werewolf": is_werewolf
                }
        
        self._write_game_event(game_id, event_data)

    def get_game_actions(self, game_id: str) -> List[WerewolfAction]:
        """Get all actions in a game."""
        return self.game_actions.get(game_id, [])

    def get_agent_actions(self, game_id: str, agent_id: str) -> List[WerewolfAction]:
        """Get all actions by a specific agent in a game."""
        all_actions = self.get_game_actions(game_id)
        return [a for a in all_actions if a.agent_id == agent_id]

    def log_game_created(self, game_state: GameState, agent_urls: List[str]) -> None:
        """Log game creation event."""
        self.active_games[game_state.game_id] = game_state

        event = {
            "event": "game_created",
            "timestamp": datetime.utcnow().isoformat(),
            "game_id": game_state.game_id,
            "agent_urls": agent_urls,
            "config": game_state.config.model_dump(),
            "role_assignments": game_state.role_assignments
        }
        self._write_game_event(game_state.game_id, event)

    def log_game_started(self, game_id: str) -> None:
        """Log game start event."""
        self._write_game_event(game_id, {
            "event": "game_started",
            "timestamp": datetime.utcnow().isoformat(),
            "game_id": game_id
        })

    def log_game_ended(self, game_id: str, winner: str, rounds: int) -> None:
        """Log game end event."""
        self._write_game_event(game_id, {
            "event": "game_ended",
            "timestamp": datetime.utcnow().isoformat(),
            "game_id": game_id,
            "winner": winner,
            "total_rounds": rounds
        })

    def log_game_completed(self, game_state: GameState) -> None:
        """Log game completion with final state."""
        self._write_game_event(game_state.game_id, {
            "event": "game_completed",
            "timestamp": datetime.utcnow().isoformat(),
            "game_id": game_state.game_id,
            "status": game_state.status.value,
            "phase": game_state.phase.value,
            "round": game_state.round_number,
            "alive": game_state.alive_agent_ids,
            "eliminated": game_state.eliminated_agent_ids,
            "winner": game_state.winner,
            "total_rounds": game_state.round_number,
            "role_assignments": game_state.role_assignments
        })

    def list_games(self) -> List[str]:
        """List all game IDs."""
        return list(self.active_games.keys())

    def get_game_summary(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Get a summary of a game."""
        game_state = self.get_game(game_id)
        if not game_state:
            return None

        return {
            "game_id": game_id,
            "status": game_state.status.value,
            "phase": game_state.phase.value,
            "round_number": game_state.round_number,
            "winner": game_state.winner,
            "total_agents": len(game_state.agent_ids),
            "alive_agents": len(game_state.alive_agent_ids),
            "eliminated_agents": len(game_state.eliminated_agent_ids)
        }

    def _has_state_changed(self, game_state: GameState) -> bool:
        """Check if the game state has changed since last logged."""
        game_id = game_state.game_id
        last_state = self.last_logged_states.get(game_id)
        
        if not last_state:
            return True  # First time logging this game
        
        # Check if any key fields have changed
        current_state = {
            "status": game_state.status.value,
            "phase": game_state.phase.value,
            "round": game_state.round_number,
            "alive": game_state.alive_agent_ids,
            "eliminated": game_state.eliminated_agent_ids,
            "winner": game_state.winner
        }
        
        # Compare with last logged state
        for key, current_value in current_state.items():
            if last_state.get(key) != current_value:
                return True
                
        return False

    def _write_game_event(self, game_id: str, event: Dict[str, Any]) -> None:
        """Write an event to the game's log file."""
        log_file = self.log_dir / f"game_{game_id}.jsonl"

        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write event to log file: {e}")

    def load_game_from_log(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Load a game's history from its log file."""
        log_file = self.log_dir / f"game_{game_id}.jsonl"

        if not log_file.exists():
            return None

        events = []
        try:
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return None

        return {"game_id": game_id, "events": events}
