"""
Prompt Builder for Green Agent.

This module constructs role-appropriate prompts for White Agents based on:
- Current game phase
- Agent's assigned role
- Public vs private information (information hiding)
- Sequential discussion context
"""

import logging
from typing import Dict, Any, List, Optional
from app.types.agent import AgentRole, AgentProfile
from app.types.game import GameState, GamePhase

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds context-aware prompts for White Agents."""
    
    # Base templates for different phases
    PHASE_TEMPLATES = {
        GamePhase.DAY_DISCUSSION: """=== WEREWOLF GAME - DAY DISCUSSION (Round {round}) ===

You are {agent_id}, a {role} in this game of Werewolf.
{role_instruction}

GAME STATE:
- Round: {round}
- Phase: Day Discussion (everyone speaks once, then votes)
- Alive Players: {alive_agents}
- Eliminated Players: {eliminated_agents}

{public_info}

{private_info}

{discussion_context}

YOUR TASK:
Share your thoughts with the village. Be strategic based on your role.
- If you're a villager/seer/doctor: Help identify werewolves
- If you're a werewolf: Blend in, deflect suspicion

Respond CONCISELY (under 100 words) with:
ACTION: discuss
DISCUSSION_TYPE: [general_discussion|accuse|defend|claim_role|reveal_identity]
TARGET: [agent_id if accusing/defending, otherwise none]
CONTENT: [your message to the village]
REASONING: [brief 1-sentence explanation]""",

        GamePhase.DAY_VOTING: """=== WEREWOLF GAME - DAY VOTING (Round {round}) ===

You are {agent_id}, a {role}.
{role_instruction}

GAME STATE:
- Round: {round}
- Phase: Day Voting (vote to eliminate one player)
- Alive Players: {alive_agents}
- Eliminated Players: {eliminated_agents}

{public_info}

{current_votes}

YOUR TASK:
Vote for a player to eliminate. You cannot vote for yourself.
Valid targets: {valid_targets}

Respond CONCISELY with:
ACTION: vote
TARGET: [agent_id to eliminate]
REASONING: [brief 1-sentence explanation]""",

        GamePhase.NIGHT_WEREWOLF: """=== WEREWOLF GAME - NIGHT PHASE (Round {round}) ===

You are {agent_id}, a WEREWOLF.

WEREWOLF KNOWLEDGE:
- Your fellow werewolves: {werewolf_teammates}
- You must work together to eliminate villagers

GAME STATE:
- Round: {round}
- Phase: Night (Werewolf Turn)
- Alive Players: {alive_agents}
- Eliminated Players: {eliminated_agents}

{public_info}

YOUR TASK:
Choose a villager to kill tonight. You cannot target fellow werewolves.
Valid targets: {valid_targets}

Respond CONCISELY with:
ACTION: kill
TARGET: [agent_id to kill]
REASONING: [brief 1-sentence explanation]""",

        GamePhase.NIGHT_SEER: """=== WEREWOLF GAME - NIGHT PHASE (Round {round}) ===

You are {agent_id}, the SEER.

SEER POWER:
Each night, you can investigate one player to learn if they are a werewolf.

PREVIOUS INVESTIGATIONS:
{investigation_results}

GAME STATE:
- Round: {round}
- Phase: Night (Seer Turn)
- Alive Players: {alive_agents}
- Eliminated Players: {eliminated_agents}

{public_info}

YOUR TASK:
Choose a player to investigate. You cannot investigate yourself.
Valid targets: {valid_targets}

Respond CONCISELY with:
ACTION: investigate
TARGET: [agent_id to investigate]
REASONING: [brief 1-sentence explanation]""",

        GamePhase.NIGHT_DOCTOR: """=== WEREWOLF GAME - NIGHT PHASE (Round {round}) ===

You are {agent_id}, the DOCTOR.

DOCTOR POWER:
Each night, you can protect one player from being killed by werewolves.

GAME STATE:
- Round: {round}
- Phase: Night (Doctor Turn)
- Alive Players: {alive_agents}
- Eliminated Players: {eliminated_agents}

{public_info}

YOUR TASK:
Choose a player to protect tonight.
Valid targets: {valid_targets}

Respond CONCISELY with:
ACTION: protect
TARGET: [agent_id to protect]
REASONING: [brief 1-sentence explanation]""",

        GamePhase.NIGHT_WITCH: """=== WEREWOLF GAME - NIGHT PHASE (Round {round}) ===

You are {agent_id}, the WITCH.

WITCH POWERS:
- Heal Potion: {heal_status} (can save the werewolf victim)
- Poison Potion: {poison_status} (can kill any player)

{killed_info}

GAME STATE:
- Round: {round}
- Phase: Night (Witch Turn)
- Alive Players: {alive_agents}
- Eliminated Players: {eliminated_agents}

{public_info}

YOUR TASK:
Decide whether to use a potion. Options:
- heal [killed_player] (if someone was killed and you have heal potion)
- poison [agent_id] (if you have poison potion)
- pass (use no potion)

Respond CONCISELY with:
ACTION: [heal|poison|pass]
TARGET: [agent_id or none]
REASONING: [brief 1-sentence explanation]""",
    }
    
    # Role-specific instructions
    ROLE_INSTRUCTIONS = {
        AgentRole.VILLAGER: "As a VILLAGER, your goal is to identify and eliminate all werewolves through discussion and voting.",
        AgentRole.WEREWOLF: "As a WEREWOLF, your goal is to eliminate villagers without being discovered. Blend in during discussions.",
        AgentRole.SEER: "As the SEER, your goal is to use your investigation power wisely and help the village identify werewolves.",
        AgentRole.DOCTOR: "As the DOCTOR, your goal is to protect key players from werewolf attacks.",
        AgentRole.WITCH: "As the WITCH, your goal is to use your potions strategically to help the village.",
        AgentRole.HUNTER: "As the HUNTER, your goal is to help identify werewolves. If eliminated, you can take one player with you.",
    }

    @staticmethod
    def build_prompt(
        game_state: GameState,
        agent: AgentProfile,
        discussion_context: List[Dict[str, Any]] = None,
        storage=None
    ) -> str:
        """
        Build a complete prompt for an agent based on game state and role.
        
        Args:
            game_state: Current game state
            agent: Agent profile to build prompt for
            discussion_context: Previous discussion messages in current round
            storage: GameLogger for accessing action history
            
        Returns:
            Complete formatted prompt string
        """
        phase = game_state.phase
        role = agent.role
        
        # Get the appropriate template
        template = PromptBuilder.PHASE_TEMPLATES.get(phase)
        if not template:
            logger.warning(f"No template for phase {phase}, using fallback")
            return PromptBuilder._build_fallback_prompt(game_state, agent)
        
        # Build template variables
        variables = PromptBuilder._build_template_variables(
            game_state, agent, discussion_context, storage
        )
        
        # Format the template
        try:
            prompt = template.format(**variables)
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            prompt = PromptBuilder._build_fallback_prompt(game_state, agent)
            
        return prompt
    
    @staticmethod
    def _build_template_variables(
        game_state: GameState,
        agent: AgentProfile,
        discussion_context: List[Dict[str, Any]] = None,
        storage=None
    ) -> Dict[str, Any]:
        """Build all template variables for prompt formatting."""
        role = agent.role
        agent_id = agent.agent_id
        
        # Basic variables
        variables = {
            "agent_id": agent_id,
            "role": role.value if role else "unknown",
            "round": game_state.round_number,
            "alive_agents": ", ".join(game_state.alive_agent_ids),
            "eliminated_agents": ", ".join(game_state.eliminated_agent_ids) or "none",
            "role_instruction": PromptBuilder.ROLE_INSTRUCTIONS.get(role, "Play strategically."),
        }
        
        # Valid targets (exclude self and role-specific exclusions)
        valid_targets = PromptBuilder._get_valid_targets(game_state, agent)
        variables["valid_targets"] = ", ".join(valid_targets) or "none"
        
        # Public information (visible to all players)
        variables["public_info"] = PromptBuilder._build_public_info(game_state, agent_id, storage)
        
        # Private information (role-specific)
        variables["private_info"] = PromptBuilder._build_private_info(game_state, agent)
        
        # Discussion context for sequential discussion
        variables["discussion_context"] = PromptBuilder._format_discussion_context(discussion_context)
        
        # Current votes (for voting phase)
        variables["current_votes"] = PromptBuilder._format_current_votes(game_state)
        
        # Role-specific variables
        if role == AgentRole.WEREWOLF:
            teammates = [
                aid for aid, r in game_state.role_assignments.items()
                if r == AgentRole.WEREWOLF.value and aid != agent_id
            ]
            variables["werewolf_teammates"] = ", ".join(teammates) or "none (you're alone)"
        
        if role == AgentRole.SEER:
            variables["investigation_results"] = PromptBuilder._format_investigation_results(
                game_state, agent_id
            )
        
        if role == AgentRole.WITCH:
            variables["heal_status"] = "AVAILABLE" if not game_state.witch_heal_used else "USED"
            variables["poison_status"] = "AVAILABLE" if not game_state.witch_poison_used else "USED"
            if game_state.killed_this_night:
                variables["killed_info"] = f"WEREWOLF VICTIM: {game_state.killed_this_night} was targeted by werewolves tonight."
            else:
                variables["killed_info"] = "No one was targeted by werewolves tonight."
        
        return variables
    
    @staticmethod
    def _get_valid_targets(game_state: GameState, agent: AgentProfile) -> List[str]:
        """Get valid targets for the current phase and role."""
        valid = [aid for aid in game_state.alive_agent_ids if aid != agent.agent_id]
        
        # Werewolves can't target each other
        if agent.role == AgentRole.WEREWOLF and game_state.phase == GamePhase.NIGHT_WEREWOLF:
            valid = [
                aid for aid in valid
                if game_state.role_assignments.get(aid) != AgentRole.WEREWOLF.value
            ]
        
        # Witch heal can only target killed player
        if agent.role == AgentRole.WITCH and game_state.phase == GamePhase.NIGHT_WITCH:
            if game_state.killed_this_night:
                valid = [game_state.killed_this_night]
                
        return valid
    
    @staticmethod
    def _build_public_info(game_state: GameState, agent_id: str, storage=None) -> str:
        """Build public information section visible to all players."""
        lines = ["PUBLIC INFORMATION:"]
        
        # Previous round summaries
        if game_state.round_number > 1:
            lines.append(f"- This is round {game_state.round_number}")
            lines.append(f"- {len(game_state.eliminated_agent_ids)} players have been eliminated")
        
        # Discussion history from storage (public actions only)
        if storage:
            all_actions = storage.get_game_actions(game_state.game_id)
            
            # Get discussion actions
            discussions = [
                a for a in all_actions
                if a.action_type.value == "discuss"
            ]
            if discussions:
                lines.append("\nRECENT DISCUSSION:")
                for action in discussions[-5:]:  # Last 5 discussions
                    content = action.discussion_content or action.reasoning
                    if len(content) > 100:
                        content = content[:97] + "..."
                    lines.append(f"  {action.agent_id}: \"{content}\"")
            
            # Get voting results from previous rounds
            votes = [
                a for a in all_actions
                if a.action_type.value == "vote"
            ]
            if votes:
                lines.append("\nPREVIOUS VOTES:")
                vote_summary = {}
                for action in votes[-10:]:
                    voter = action.agent_id
                    target = action.target_agent_id
                    vote_summary[voter] = target
                for voter, target in vote_summary.items():
                    lines.append(f"  {voter} voted for {target}")
        
        return "\n".join(lines) if len(lines) > 1 else ""
    
    @staticmethod
    def _build_private_info(game_state: GameState, agent: AgentProfile) -> str:
        """Build private information section (role-specific secrets)."""
        role = agent.role
        agent_id = agent.agent_id
        
        # Most roles don't have additional private info beyond what's in the template
        if role == AgentRole.VILLAGER:
            return ""
        
        if role == AgentRole.HUNTER:
            return "HUNTER ABILITY: If you are eliminated, you will get to shoot one player."
        
        return ""
    
    @staticmethod
    def _format_discussion_context(discussion_context: List[Dict[str, Any]] = None) -> str:
        """Format previous discussion messages in current round for sequential context."""
        if not discussion_context:
            return "CURRENT ROUND DISCUSSION:\nYou are the first to speak this round."
        
        lines = ["CURRENT ROUND DISCUSSION (what others have said):"]
        for msg in discussion_context:
            speaker = msg.get("agent_id", "unknown")
            content = msg.get("content", msg.get("discussion_content", ""))
            if len(content) > 150:
                content = content[:147] + "..."
            lines.append(f"  {speaker}: \"{content}\"")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_current_votes(game_state: GameState) -> str:
        """Format current voting status."""
        if not game_state.current_votes:
            return "CURRENT VOTES: No votes cast yet."
        
        lines = ["CURRENT VOTES:"]
        for voter, target in game_state.current_votes.items():
            lines.append(f"  {voter} -> {target}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_investigation_results(game_state: GameState, seer_id: str) -> str:
        """Format seer's investigation results."""
        results = []
        for key, investigation in game_state.seer_investigations.items():
            if investigation.get("seer_id") == seer_id:
                target = investigation.get("target_id")
                is_wolf = investigation.get("is_werewolf")
                round_num = investigation.get("round")
                result = "WEREWOLF" if is_wolf else "NOT a werewolf"
                results.append(f"  Round {round_num}: {target} is {result}")
        
        if not results:
            return "No investigations yet."
        
        return "\n".join(results)
    
    @staticmethod
    def _build_fallback_prompt(game_state: GameState, agent: AgentProfile) -> str:
        """Build a simple fallback prompt when templates fail."""
        return f"""You are {agent.agent_id}, a {agent.role.value if agent.role else 'player'} in Werewolf.
Phase: {game_state.phase.value}
Round: {game_state.round_number}
Alive: {', '.join(game_state.alive_agent_ids)}

What is your action? Respond briefly."""

