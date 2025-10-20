"""State management for Werewolf game"""

from typing import Dict, List, Optional, Set
from datetime import datetime
import random
from app.types.agent import AgentRole, WerewolfAction, ActionType
from app.types.game import GameState, GamePhase, GameStatus, RoundRecord


class StateManager:
    """Manages game state transitions and updates"""

    @staticmethod
    def assign_roles(agent_ids: List[str], config: Dict) -> Dict[str, str]:
        """Randomly assign roles to agents"""
        roles = []

        # Add werewolves
        for _ in range(config.get("num_werewolves", 2)):
            roles.append(AgentRole.WEREWOLF.value)

        # Add special roles
        if config.get("has_seer", True):
            roles.append(AgentRole.SEER.value)
        if config.get("has_doctor", True):
            roles.append(AgentRole.DOCTOR.value)
        if config.get("has_hunter", False):
            roles.append(AgentRole.HUNTER.value)
        if config.get("has_witch", False):
            roles.append(AgentRole.WITCH.value)

        # Fill remaining with villagers
        while len(roles) < len(agent_ids):
            roles.append(AgentRole.VILLAGER.value)

        # Shuffle and assign
        random.shuffle(roles)
        return {agent_id: role for agent_id, role in zip(agent_ids, roles)}

    @staticmethod
    def get_next_phase(current_phase: GamePhase, config: Dict) -> GamePhase:
        """Determine the next game phase"""
        phase_order = [
            GamePhase.NIGHT_WEREWOLF,
        ]

        if config.get("has_witch", False):
            phase_order.append(GamePhase.NIGHT_WITCH)
        if config.get("has_seer", True):
            phase_order.append(GamePhase.NIGHT_SEER)
        if config.get("has_doctor", True):
            phase_order.append(GamePhase.NIGHT_DOCTOR)
        
        # Day phases come after all night phases
        phase_order.extend([
            GamePhase.DAY_DISCUSSION,
            GamePhase.DAY_VOTING,
        ])

        if current_phase == GamePhase.SETUP:
            return GamePhase.NIGHT_WEREWOLF

        try:
            current_index = phase_order.index(current_phase)
            next_index = (current_index + 1) % len(phase_order)
            return phase_order[next_index]
        except ValueError:
            return GamePhase.DAY_DISCUSSION

    @staticmethod
    def process_voting_results(game_state: GameState) -> Optional[str]:
        """
        Process voting results and determine who gets eliminated.
        Returns the ID of the eliminated agent, or None if no elimination.
        """
        if not game_state.current_votes:
            return None

        # Count votes
        vote_counts: Dict[str, int] = {}
        for voter_id, target_id in game_state.current_votes.items():
            if target_id:
                vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

        if not vote_counts:
            return None

        # Find the agent(s) with the most votes
        max_votes = max(vote_counts.values())
        candidates = [agent_id for agent_id, count in vote_counts.items()
                     if count == max_votes]

        # If tied, randomly select one (or use other tie-breaking logic)
        if len(candidates) == 1:
            return candidates[0]
        else:
            return random.choice(candidates) if candidates else None

    @staticmethod
    def process_werewolf_kill(
        game_state: GameState,
        werewolf_actions: List[WerewolfAction]
    ) -> Optional[str]:
        """
        Process werewolf kill actions and determine the target.
        Returns the ID of the killed agent, or None if no consensus.
        """
        kill_targets: Dict[str, int] = {}

        for action in werewolf_actions:
            if action.action_type == ActionType.KILL and action.target_agent_id:
                kill_targets[action.target_agent_id] = (
                    kill_targets.get(action.target_agent_id, 0) + 1
                )

        if not kill_targets:
            return None

        # Werewolves must agree on target (majority vote)
        werewolf_count = sum(1 for role in game_state.role_assignments.values()
                           if role == AgentRole.WEREWOLF.value)
        required_votes = (werewolf_count // 2) + 1

        for target_id, vote_count in kill_targets.items():
            if vote_count >= required_votes:
                return target_id

        return None

    @staticmethod
    def eliminate_agent(game_state: GameState, agent_id: str) -> None:
        """Remove an agent from the game"""
        if agent_id in game_state.alive_agent_ids:
            game_state.alive_agent_ids.remove(agent_id)
            game_state.eliminated_agent_ids.append(agent_id)
            
            # Check if eliminated agent is a hunter
            if game_state.role_assignments.get(agent_id) == AgentRole.HUNTER.value:
                game_state.hunter_eliminated = agent_id

    @staticmethod
    def process_witch_actions(
        game_state: GameState,
        witch_actions: List[WerewolfAction]
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Process witch actions and return (healed_agent, poisoned_agent).
        Returns (None, None) if no valid actions.
        """
        healed_agent = None
        poisoned_agent = None
        
        for action in witch_actions:
            if action.action_type == ActionType.HEAL and not game_state.witch_heal_used:
                if action.target_agent_id == game_state.killed_this_night:
                    healed_agent = action.target_agent_id
                    game_state.witch_heal_used = True
            elif action.action_type == ActionType.POISON and not game_state.witch_poison_used:
                if action.target_agent_id in game_state.alive_agent_ids:
                    poisoned_agent = action.target_agent_id
                    game_state.witch_poison_used = True
                    
        return healed_agent, poisoned_agent

    @staticmethod
    def process_hunter_shoot(
        game_state: GameState,
        hunter_actions: List[WerewolfAction]
    ) -> Optional[str]:
        """
        Process hunter shoot action when eliminated.
        Returns the shot agent ID or None.
        """
        if not game_state.hunter_eliminated:
            return None
            
        for action in hunter_actions:
            if (action.agent_id == game_state.hunter_eliminated and 
                action.action_type == ActionType.SHOOT and
                action.target_agent_id in game_state.alive_agent_ids):
                return action.target_agent_id
                
        return None

    @staticmethod
    def process_seer_investigation(
        game_state: GameState,
        seer_actions: List[WerewolfAction]
    ) -> None:
        """
        Process seer investigation actions and store results.
        Updates game_state.seer_investigations with investigation results.
        """
        for action in seer_actions:
            if (action.action_type == ActionType.INVESTIGATE and 
                action.target_agent_id and
                action.target_agent_id in game_state.alive_agent_ids):
                
                # Determine if the target is a werewolf
                target_role = game_state.role_assignments.get(action.target_agent_id)
                is_werewolf = target_role == AgentRole.WEREWOLF.value
                
                # Store investigation result
                investigation_key = f"{action.agent_id}_{action.target_agent_id}_{game_state.round_number}"
                game_state.seer_investigations[investigation_key] = {
                    "seer_id": action.agent_id,
                    "target_id": action.target_agent_id,
                    "is_werewolf": is_werewolf,
                    "round": game_state.round_number,
                    "timestamp": action.timestamp
                }

    @staticmethod
    def advance_round(game_state: GameState) -> None:
        """Advance to the next round"""
        # Clear current votes
        game_state.current_votes.clear()

        # Move to next phase
        game_state.phase = StateManager.get_next_phase(
            game_state.phase,
            game_state.config.model_dump()
        )

        # Increment round number if returning to day
        if game_state.phase == GamePhase.DAY_DISCUSSION:
            game_state.round_number += 1
            # Clear night-specific state
            game_state.killed_this_night = None
            game_state.hunter_eliminated = None

    @staticmethod
    def create_round_record(
        game_state: GameState,
        actions: List[WerewolfAction],
        eliminated: List[str]
    ) -> RoundRecord:
        """Create a record of the current round"""
        return RoundRecord(
            round_number=game_state.round_number,
            phase=game_state.phase,
            actions=[action.model_dump() for action in actions],
            eliminated_agents=eliminated,
            timestamp=datetime.utcnow()
        )

    @staticmethod
    def get_visible_state(game_state: GameState, agent_id: str) -> Dict:
        """
        Get the game state visible to a specific agent.
        Hides information the agent shouldn't know.
        """
        visible_state = {
            "game_id": game_state.game_id,
            "phase": game_state.phase.value,
            "round_number": game_state.round_number,
            "alive_agents": game_state.alive_agent_ids,
            "eliminated_agents": game_state.eliminated_agent_ids,
            "your_role": game_state.role_assignments.get(agent_id),
        }

        # Add role-specific information
        agent_role = game_state.role_assignments.get(agent_id)

        if agent_role == AgentRole.WEREWOLF.value:
            # Werewolves know each other
            werewolf_ids = [
                aid for aid, role in game_state.role_assignments.items()
                if role == AgentRole.WEREWOLF.value
            ]
            visible_state["werewolf_teammates"] = werewolf_ids

        elif agent_role == AgentRole.WITCH.value:
            # Witch knows who was killed this night and potion status
            visible_state["killed_this_night"] = game_state.killed_this_night
            visible_state["heal_available"] = not game_state.witch_heal_used
            visible_state["poison_available"] = not game_state.witch_poison_used

        elif agent_role == AgentRole.SEER.value:
            # Seer knows their investigation results
            seer_investigations = []
            for investigation in game_state.seer_investigations.values():
                if investigation["seer_id"] == agent_id:
                    seer_investigations.append({
                        "target_id": investigation["target_id"],
                        "is_werewolf": investigation["is_werewolf"],
                        "round": investigation["round"]
                    })
            visible_state["investigation_results"] = seer_investigations

        # During voting, show current votes
        if game_state.phase == GamePhase.DAY_VOTING:
            visible_state["current_votes"] = game_state.current_votes

        return visible_state