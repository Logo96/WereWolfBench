"""
Public Game Memory - Shared memory accessible to all agents.

This stores all PUBLIC information that any player in a Werewolf game would know:
- Discussions (what people said)
- Votes (who voted for whom)
- Eliminations (who was eliminated and when)
- Phase transitions and round progression

Information is stored chronologically by phase for easy reconstruction of game history.

Design Decisions:
1. Organized chronologically (by phase/round) rather than by action type, 
   because players experience the game in sequence
2. Compact summaries for prompts to reduce token usage
3. Memory ID for versioning (can track what information agent has seen)
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class PhaseEvent:
    """A single event within a phase."""
    event_type: str  # "discussion", "vote", "elimination", "phase_start", "phase_end"
    agent_id: Optional[str] = None
    target_id: Optional[str] = None
    content: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseRecord:
    """Record of all events in a single phase."""
    round_number: int
    phase: str
    events: List[PhaseEvent] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None


class PublicGameMemory:
    """
    Shared memory for public game information.
    
    This class stores ALL public information from the game, organized chronologically.
    It's designed to be:
    1. Complete - stores full game history (not just last N events)
    2. Efficient - provides compact summaries for prompts
    3. Consistent - all agents see the same public information
    """
    
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.memory_id = str(uuid.uuid4())[:8]  # Short ID for reference
        
        # Chronological storage: List of PhaseRecords
        self.phase_history: List[PhaseRecord] = []
        self._current_phase: Optional[PhaseRecord] = None
        
        # Quick-access indices (for efficient lookups)
        self._discussions_by_round: Dict[int, List[PhaseEvent]] = {}
        self._votes_by_round: Dict[int, Dict[str, str]] = {}  # round -> {voter: target}
        self._eliminations: List[Dict[str, Any]] = []  # chronological list
        self._alive_by_round: Dict[int, List[str]] = {}  # round -> alive_agents
        
        # Tracking
        self.created_at = datetime.utcnow()
        self.last_updated = datetime.utcnow()
    
    # =========================================================================
    # Phase Management
    # =========================================================================
    
    def start_phase(self, round_number: int, phase: str, alive_agents: List[str]) -> None:
        """Start a new phase, closing any previous phase."""
        # Close previous phase
        if self._current_phase:
            self._current_phase.ended_at = datetime.utcnow()
            self.phase_history.append(self._current_phase)
        
        # Create new phase record
        self._current_phase = PhaseRecord(
            round_number=round_number,
            phase=phase
        )
        
        # Track alive agents at start of this round
        if round_number not in self._alive_by_round:
            self._alive_by_round[round_number] = alive_agents.copy()
        
        self._update_timestamp()
    
    def end_phase(self) -> None:
        """End the current phase."""
        if self._current_phase:
            self._current_phase.ended_at = datetime.utcnow()
            self.phase_history.append(self._current_phase)
            self._current_phase = None
        self._update_timestamp()
    
    # =========================================================================
    # Event Recording
    # =========================================================================
    
    def add_discussion(
        self,
        agent_id: str,
        content: str,
        round_number: int,
        discussion_type: str = "general",
        targets: Optional[List[str]] = None,
        subactions: Optional[List[str]] = None
    ) -> None:
        """
        Record a discussion action.
        
        Args:
            agent_id: Who spoke
            content: What they said
            round_number: Current round
            discussion_type: Type of discussion (e.g., "accuse", "defend", "claim_role")
            targets: Who the discussion targets (for accuse/defend)
            subactions: List of discussion subactions used
        """
        event = PhaseEvent(
            event_type="discussion",
            agent_id=agent_id,
            content=content,
            target_id=targets[0] if targets and len(targets) == 1 else None,
            metadata={
                "discussion_type": discussion_type,
                "targets": targets or [],
                "subactions": subactions or []
            }
        )
        
        # Add to current phase
        if self._current_phase:
            self._current_phase.events.append(event)
        
        # Add to quick-access index
        if round_number not in self._discussions_by_round:
            self._discussions_by_round[round_number] = []
        self._discussions_by_round[round_number].append(event)
        
        self._update_timestamp()
    
    def add_vote(self, voter_id: str, target_id: str, round_number: int) -> None:
        """Record a vote."""
        event = PhaseEvent(
            event_type="vote",
            agent_id=voter_id,
            target_id=target_id
        )
        
        # Add to current phase
        if self._current_phase:
            self._current_phase.events.append(event)
        
        # Add to quick-access index
        if round_number not in self._votes_by_round:
            self._votes_by_round[round_number] = {}
        self._votes_by_round[round_number][voter_id] = target_id
        
        self._update_timestamp()
    
    def add_elimination(
        self,
        agent_id: str,
        round_number: int,
        method: str,
        phase: str
    ) -> None:
        """
        Record an elimination.
        
        Args:
            agent_id: Who was eliminated
            round_number: Which round
            method: How they were eliminated ("vote", "werewolf_kill", "witch_poison", "hunter_shot")
            phase: Which phase the elimination occurred in
        """
        elimination = {
            "agent_id": agent_id,
            "round": round_number,
            "method": method,
            "phase": phase,
            "timestamp": datetime.utcnow()
        }
        self._eliminations.append(elimination)
        
        event = PhaseEvent(
            event_type="elimination",
            agent_id=agent_id,
            metadata={"method": method, "round": round_number}
        )
        
        if self._current_phase:
            self._current_phase.events.append(event)
        
        self._update_timestamp()
    
    def update_alive_agents(self, round_number: int, alive_agents: List[str]) -> None:
        """Update the list of alive agents for a round."""
        self._alive_by_round[round_number] = alive_agents.copy()
        self._update_timestamp()
    
    # =========================================================================
    # Memory Retrieval - Full History
    # =========================================================================
    
    def get_all_discussions(self) -> List[Dict[str, Any]]:
        """Get all discussions from all rounds."""
        discussions = []
        for round_num in sorted(self._discussions_by_round.keys()):
            for event in self._discussions_by_round[round_num]:
                discussions.append({
                    "round": round_num,
                    "agent_id": event.agent_id,
                    "content": event.content,
                    "discussion_type": event.metadata.get("discussion_type", "general"),
                    "targets": event.metadata.get("targets", []),
                    "timestamp": event.timestamp.isoformat()
                })
        return discussions
    
    def get_all_votes(self) -> List[Dict[str, Any]]:
        """Get all votes from all rounds."""
        votes = []
        for round_num in sorted(self._votes_by_round.keys()):
            round_votes = self._votes_by_round[round_num]
            for voter, target in round_votes.items():
                votes.append({
                    "round": round_num,
                    "voter_id": voter,
                    "target_id": target
                })
        return votes
    
    def get_all_eliminations(self) -> List[Dict[str, Any]]:
        """Get all eliminations in chronological order."""
        return self._eliminations.copy()
    
    def get_round_discussions(self, round_number: int) -> List[Dict[str, Any]]:
        """Get discussions from a specific round."""
        events = self._discussions_by_round.get(round_number, [])
        return [
            {
                "agent_id": e.agent_id,
                "content": e.content,
                "discussion_type": e.metadata.get("discussion_type", "general"),
                "targets": e.metadata.get("targets", [])
            }
            for e in events
        ]
    
    def get_round_votes(self, round_number: int) -> Dict[str, str]:
        """Get votes from a specific round."""
        return self._votes_by_round.get(round_number, {}).copy()
    
    # =========================================================================
    # Compact Summaries (for prompts)
    # =========================================================================
    
    def get_compact_summary(self, max_rounds: Optional[int] = None) -> str:
        """
        Get a compact summary of the game history for prompt inclusion.
        
        This is designed to be token-efficient while preserving key information.
        
        Args:
            max_rounds: Limit to last N rounds (None = all rounds)
        """
        lines = []
        
        # Get rounds to include
        all_rounds = sorted(set(
            list(self._discussions_by_round.keys()) + 
            list(self._votes_by_round.keys())
        ))
        
        if max_rounds and len(all_rounds) > max_rounds:
            rounds = all_rounds[-max_rounds:]
            lines.append(f"[Showing last {max_rounds} rounds of {len(all_rounds)}]")
        else:
            rounds = all_rounds
        
        for round_num in rounds:
            round_lines = [f"\n📍 ROUND {round_num}:"]
            
            # Discussions
            discussions = self._discussions_by_round.get(round_num, [])
            if discussions:
                round_lines.append("  💬 Discussions:")
                for d in discussions:
                    targets = d.metadata.get("targets", [])
                    target_str = f" (→{','.join(targets)})" if targets else ""
                    # Truncate long discussions
                    content = d.content or ""
                    if len(content) > 150:
                        content = content[:147] + "..."
                    round_lines.append(f"    • {d.agent_id}{target_str}: \"{content}\"")
            
            # Votes
            votes = self._votes_by_round.get(round_num, {})
            if votes:
                round_lines.append("  🗳️ Votes:")
                vote_counts = {}
                for voter, target in votes.items():
                    vote_counts[target] = vote_counts.get(target, 0) + 1
                    round_lines.append(f"    • {voter} → {target}")
                # Add vote summary
                vote_summary = ", ".join([f"{t}:{c}" for t, c in sorted(vote_counts.items(), key=lambda x: -x[1])])
                round_lines.append(f"    Summary: {vote_summary}")
            
            # Eliminations in this round
            round_elims = [e for e in self._eliminations if e["round"] == round_num]
            if round_elims:
                round_lines.append("  ❌ Eliminated:")
                for e in round_elims:
                    round_lines.append(f"    • {e['agent_id']} ({e['method']})")
            
            lines.extend(round_lines)
        
        # Current status
        if self._alive_by_round:
            latest_round = max(self._alive_by_round.keys())
            alive = self._alive_by_round[latest_round]
            lines.append(f"\n📊 Current: {len(alive)} alive, {len(self._eliminations)} eliminated")
        
        return "\n".join(lines) if lines else "No game history yet."
    
    def get_memory_summary(self) -> str:
        """
        Get a structured memory summary for inclusion in prompts.
        
        Returns formatted string with memory ID for reference.
        """
        summary = self.get_compact_summary()
        return f"═══ GAME MEMORY (ID: {self.memory_id}) ═══\n{summary}\n═══════════════════════════════"
    
    def get_round_summary(self, round_number: int) -> str:
        """Get summary for a specific round."""
        lines = [f"Round {round_number} Summary:"]
        
        # Discussions
        discussions = self._discussions_by_round.get(round_number, [])
        if discussions:
            lines.append("  Discussions:")
            for d in discussions:
                content = (d.content or "")[:100]
                lines.append(f"    - {d.agent_id}: {content}")
        
        # Votes
        votes = self._votes_by_round.get(round_number, {})
        if votes:
            lines.append("  Votes:")
            for voter, target in votes.items():
                lines.append(f"    - {voter} → {target}")
        
        # Eliminations
        elims = [e for e in self._eliminations if e["round"] == round_number]
        if elims:
            lines.append("  Eliminated:")
            for e in elims:
                lines.append(f"    - {e['agent_id']} ({e['method']})")
        
        return "\n".join(lines)
    
    # =========================================================================
    # Serialization
    # =========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize memory to dictionary for storage."""
        return {
            "game_id": self.game_id,
            "memory_id": self.memory_id,
            "discussions": self.get_all_discussions(),
            "votes": self.get_all_votes(),
            "eliminations": self._eliminations,
            "alive_by_round": {str(k): v for k, v in self._alive_by_round.items()},
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PublicGameMemory':
        """Deserialize memory from dictionary."""
        memory = cls(data["game_id"])
        memory.memory_id = data.get("memory_id", memory.memory_id)
        
        # Restore discussions
        for d in data.get("discussions", []):
            round_num = d["round"]
            if round_num not in memory._discussions_by_round:
                memory._discussions_by_round[round_num] = []
            memory._discussions_by_round[round_num].append(PhaseEvent(
                event_type="discussion",
                agent_id=d["agent_id"],
                content=d["content"],
                metadata={
                    "discussion_type": d.get("discussion_type", "general"),
                    "targets": d.get("targets", [])
                }
            ))
        
        # Restore votes
        for v in data.get("votes", []):
            round_num = v["round"]
            if round_num not in memory._votes_by_round:
                memory._votes_by_round[round_num] = {}
            memory._votes_by_round[round_num][v["voter_id"]] = v["target_id"]
        
        # Restore eliminations
        memory._eliminations = data.get("eliminations", [])
        
        # Restore alive status
        memory._alive_by_round = {
            int(k): v for k, v in data.get("alive_by_round", {}).items()
        }
        
        return memory
    
    # =========================================================================
    # Internal
    # =========================================================================
    
    def _update_timestamp(self) -> None:
        """Update the last modified timestamp."""
        self.last_updated = datetime.utcnow()

