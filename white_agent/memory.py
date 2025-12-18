"""
Agent Private Memory - Role-specific memory for White Agents.

This stores PRIVATE information that only the specific agent should know:
- Werewolf: Who their teammates are
- Seer: Investigation results
- Witch: Potion usage status
- Doctor: Who they've protected
- Hunter: Their shoot status

Design Decisions:
1. Memory is keyed by agent_id and game_id
2. Memory persists across turns within a game
3. Each role has specific private information to track
4. Memory can be serialized for persistence (optional)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class InvestigationResult:
    """Result of a seer investigation."""
    target_id: str
    is_werewolf: bool
    round_number: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


class AgentPrivateMemory:
    """
    Private memory storage for a single agent within a game.
    
    This stores role-specific information that only this agent should know:
    - Werewolves know their teammates
    - Seers know their investigation results
    - Witches know their potion status
    - Doctors know who they've protected
    """
    
    def __init__(self, agent_id: str, role: str, game_id: str = ""):
        self.agent_id = agent_id
        self.role = role
        self.game_id = game_id
        self.created_at = datetime.utcnow()
        self.last_updated = datetime.utcnow()
        
        # Werewolf-specific
        self._werewolf_teammates: List[str] = []
        
        # Seer-specific
        self._investigation_results: List[InvestigationResult] = []
        
        # Witch-specific
        self._heal_used: bool = False
        self._poison_used: bool = False
        self._healed_target: Optional[str] = None
        self._poisoned_target: Optional[str] = None
        
        # Doctor-specific
        self._protection_history: List[Dict[str, Any]] = []
        
        # Hunter-specific
        self._has_shot: bool = False
        self._shot_target: Optional[str] = None
        
        # General notes/strategy (optional, for agent use)
        self._notes: List[Dict[str, Any]] = []
        self._suspicions: Dict[str, float] = {}  # agent_id -> suspicion level
    
    # =========================================================================
    # Werewolf-specific methods
    # =========================================================================
    
    def set_werewolf_teammates(self, teammates: List[str]) -> None:
        """Set the list of werewolf teammates (for werewolves only)."""
        if self.role != "werewolf":
            return
        self._werewolf_teammates = [t for t in teammates if t != self.agent_id]
        self._update_timestamp()
    
    def get_werewolf_teammates(self) -> List[str]:
        """Get the list of werewolf teammates."""
        return self._werewolf_teammates.copy()
    
    def is_teammate(self, agent_id: str) -> bool:
        """Check if an agent is a werewolf teammate."""
        return agent_id in self._werewolf_teammates
    
    # =========================================================================
    # Seer-specific methods
    # =========================================================================
    
    def add_investigation_result(
        self,
        target_id: str,
        is_werewolf: bool,
        round_num: int
    ) -> None:
        """Add a new investigation result (for seer only)."""
        if self.role != "seer":
            return
        
        result = InvestigationResult(
            target_id=target_id,
            is_werewolf=is_werewolf,
            round_number=round_num
        )
        self._investigation_results.append(result)
        self._update_timestamp()
    
    def get_investigation_results(self) -> List[Dict[str, Any]]:
        """Get all investigation results."""
        return [
            {
                "target_id": r.target_id,
                "is_werewolf": r.is_werewolf,
                "round": r.round_number,
                "timestamp": r.timestamp.isoformat()
            }
            for r in self._investigation_results
        ]
    
    def get_known_werewolves(self) -> List[str]:
        """Get list of agents known to be werewolves from investigations."""
        return [r.target_id for r in self._investigation_results if r.is_werewolf]
    
    def get_confirmed_innocents(self) -> List[str]:
        """Get list of agents confirmed NOT to be werewolves."""
        return [r.target_id for r in self._investigation_results if not r.is_werewolf]
    
    def has_investigated(self, agent_id: str) -> bool:
        """Check if an agent has already been investigated."""
        return any(r.target_id == agent_id for r in self._investigation_results)
    
    # =========================================================================
    # Witch-specific methods
    # =========================================================================
    
    def update_potion_status(
        self,
        heal_used: Optional[bool] = None,
        poison_used: Optional[bool] = None,
        healed_target: Optional[str] = None,
        poisoned_target: Optional[str] = None
    ) -> None:
        """Update witch potion status (for witch only)."""
        if self.role != "witch":
            return
        
        if heal_used is not None:
            self._heal_used = heal_used
        if poison_used is not None:
            self._poison_used = poison_used
        if healed_target:
            self._healed_target = healed_target
        if poisoned_target:
            self._poisoned_target = poisoned_target
        
        self._update_timestamp()
    
    def get_potion_status(self) -> Dict[str, Any]:
        """Get current potion status."""
        return {
            "heal_used": self._heal_used,
            "poison_used": self._poison_used,
            "heal_available": not self._heal_used,
            "poison_available": not self._poison_used,
            "healed_target": self._healed_target,
            "poisoned_target": self._poisoned_target
        }
    
    def can_heal(self) -> bool:
        """Check if witch can still heal."""
        return self.role == "witch" and not self._heal_used
    
    def can_poison(self) -> bool:
        """Check if witch can still poison."""
        return self.role == "witch" and not self._poison_used
    
    # =========================================================================
    # Doctor-specific methods
    # =========================================================================
    
    def add_protection(self, target_id: str, round_num: int) -> None:
        """Record a protection action (for doctor only)."""
        if self.role != "doctor":
            return
        
        self._protection_history.append({
            "target_id": target_id,
            "round": round_num,
            "timestamp": datetime.utcnow().isoformat()
        })
        self._update_timestamp()
    
    def get_protection_history(self) -> List[Dict[str, Any]]:
        """Get history of all protection actions."""
        return self._protection_history.copy()
    
    def get_last_protected(self) -> Optional[str]:
        """Get the last protected target."""
        if self._protection_history:
            return self._protection_history[-1]["target_id"]
        return None
    
    # =========================================================================
    # Hunter-specific methods
    # =========================================================================
    
    def record_shot(self, target_id: str) -> None:
        """Record hunter's shot (for hunter only)."""
        if self.role != "hunter":
            return
        
        self._has_shot = True
        self._shot_target = target_id
        self._update_timestamp()
    
    def has_shot(self) -> bool:
        """Check if hunter has already shot."""
        return self._has_shot
    
    def get_shot_target(self) -> Optional[str]:
        """Get who the hunter shot."""
        return self._shot_target
    
    # =========================================================================
    # General methods (all roles)
    # =========================================================================
    
    def add_note(self, content: str, category: str = "general") -> None:
        """Add a strategic note."""
        self._notes.append({
            "content": content,
            "category": category,
            "timestamp": datetime.utcnow().isoformat()
        })
        self._update_timestamp()
    
    def get_notes(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all notes, optionally filtered by category."""
        if category:
            return [n for n in self._notes if n["category"] == category]
        return self._notes.copy()
    
    def update_suspicion(self, agent_id: str, level: float) -> None:
        """Update suspicion level for an agent (0.0 to 1.0)."""
        self._suspicions[agent_id] = max(0.0, min(1.0, level))
        self._update_timestamp()
    
    def get_suspicions(self) -> Dict[str, float]:
        """Get all suspicion levels."""
        return self._suspicions.copy()
    
    def get_most_suspicious(self, top_n: int = 3) -> List[tuple]:
        """Get the top N most suspicious agents."""
        sorted_suspicions = sorted(
            self._suspicions.items(),
            key=lambda x: -x[1]
        )
        return sorted_suspicions[:top_n]
    
    # =========================================================================
    # Summary for prompts
    # =========================================================================
    
    def get_private_summary(self) -> str:
        """Get a summary of private information for prompt inclusion."""
        lines = [f"═══ YOUR PRIVATE MEMORY ({self.role.upper()}) ═══"]
        
        if self.role == "werewolf":
            teammates = self._werewolf_teammates
            if teammates:
                lines.append(f"🐺 Your werewolf teammates: {', '.join(teammates)}")
            else:
                lines.append("🐺 You are the only werewolf")
        
        elif self.role == "seer":
            results = self._investigation_results
            if results:
                lines.append("🔮 Your investigation results:")
                for r in results:
                    result_str = "WEREWOLF ⚠️" if r.is_werewolf else "NOT a werewolf ✓"
                    lines.append(f"  Round {r.round_number}: {r.target_id} is {result_str}")
            else:
                lines.append("🔮 No investigations yet")
        
        elif self.role == "witch":
            lines.append("🧪 Potion status:")
            lines.append(f"  Heal potion: {'AVAILABLE' if not self._heal_used else 'USED'}")
            lines.append(f"  Poison potion: {'AVAILABLE' if not self._poison_used else 'USED'}")
            if self._healed_target:
                lines.append(f"  You healed: {self._healed_target}")
            if self._poisoned_target:
                lines.append(f"  You poisoned: {self._poisoned_target}")
        
        elif self.role == "doctor":
            history = self._protection_history
            if history:
                lines.append("💊 Your protection history:")
                for p in history[-5:]:  # Last 5
                    lines.append(f"  Round {p['round']}: Protected {p['target_id']}")
            else:
                lines.append("💊 No protections yet")
        
        elif self.role == "hunter":
            if self._has_shot:
                lines.append(f"🎯 You shot: {self._shot_target}")
            else:
                lines.append("🎯 You have not used your shot yet")
        
        lines.append("═══════════════════════════════════")
        return "\n".join(lines)
    
    # =========================================================================
    # Serialization
    # =========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize memory to dictionary."""
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "game_id": self.game_id,
            "werewolf_teammates": self._werewolf_teammates,
            "investigation_results": [
                {
                    "target_id": r.target_id,
                    "is_werewolf": r.is_werewolf,
                    "round_number": r.round_number,
                    "timestamp": r.timestamp.isoformat()
                }
                for r in self._investigation_results
            ],
            "heal_used": self._heal_used,
            "poison_used": self._poison_used,
            "healed_target": self._healed_target,
            "poisoned_target": self._poisoned_target,
            "protection_history": self._protection_history,
            "has_shot": self._has_shot,
            "shot_target": self._shot_target,
            "notes": self._notes,
            "suspicions": self._suspicions,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentPrivateMemory':
        """Deserialize memory from dictionary."""
        memory = cls(
            agent_id=data["agent_id"],
            role=data["role"],
            game_id=data.get("game_id", "")
        )
        
        memory._werewolf_teammates = data.get("werewolf_teammates", [])
        
        for r in data.get("investigation_results", []):
            memory._investigation_results.append(InvestigationResult(
                target_id=r["target_id"],
                is_werewolf=r["is_werewolf"],
                round_number=r["round_number"],
                timestamp=datetime.fromisoformat(r["timestamp"]) if "timestamp" in r else datetime.utcnow()
            ))
        
        memory._heal_used = data.get("heal_used", False)
        memory._poison_used = data.get("poison_used", False)
        memory._healed_target = data.get("healed_target")
        memory._poisoned_target = data.get("poisoned_target")
        memory._protection_history = data.get("protection_history", [])
        memory._has_shot = data.get("has_shot", False)
        memory._shot_target = data.get("shot_target")
        memory._notes = data.get("notes", [])
        memory._suspicions = data.get("suspicions", {})
        
        return memory
    
    def _update_timestamp(self) -> None:
        """Update the last modified timestamp."""
        self.last_updated = datetime.utcnow()


class PrivateMemoryManager:
    """
    Manager for all agent private memories in a game.
    
    This provides a centralized way to access and update private memories
    for all agents in a game.
    """
    
    def __init__(self, game_id: str):
        self.game_id = game_id
        self._memories: Dict[str, AgentPrivateMemory] = {}
    
    def get_or_create(self, agent_id: str, role: str) -> AgentPrivateMemory:
        """Get existing memory or create new one for an agent."""
        key = agent_id
        if key not in self._memories:
            self._memories[key] = AgentPrivateMemory(
                agent_id=agent_id,
                role=role,
                game_id=self.game_id
            )
        return self._memories[key]
    
    def get(self, agent_id: str) -> Optional[AgentPrivateMemory]:
        """Get memory for an agent if it exists."""
        return self._memories.get(agent_id)
    
    def initialize_werewolf_teams(self, role_assignments: Dict[str, str]) -> None:
        """Initialize werewolf teammate knowledge for all werewolves."""
        werewolves = [
            agent_id for agent_id, role in role_assignments.items()
            if role == "werewolf"
        ]
        
        for wolf_id in werewolves:
            memory = self.get_or_create(wolf_id, "werewolf")
            memory.set_werewolf_teammates(werewolves)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize all memories."""
        return {
            "game_id": self.game_id,
            "memories": {
                agent_id: memory.to_dict()
                for agent_id, memory in self._memories.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PrivateMemoryManager':
        """Deserialize all memories."""
        manager = cls(data["game_id"])
        for agent_id, memory_data in data.get("memories", {}).items():
            manager._memories[agent_id] = AgentPrivateMemory.from_dict(memory_data)
        return manager

