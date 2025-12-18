"""
Prompt Builder for Green Agent.

This module constructs role-appropriate prompts for White Agents based on:
- Current game phase
- Agent's assigned role
- Public vs private information (information hiding)
- Sequential discussion context
- Full game history from PublicGameMemory
"""

import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from app.types.agent import AgentRole, AgentProfile
from app.types.game import GameState, GamePhase

if TYPE_CHECKING:
    from app.memory.public_memory import PublicGameMemory

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds context-aware prompts for White Agents."""
    
    # Base templates for different phases
    PHASE_TEMPLATES = {
        GamePhase.DAY_DISCUSSION: """ROUND {round} - DAY DISCUSSION PHASE

IDENTITY: {agent_id} ({role})

{role_instruction}

CURRENT STATE:
Round: {round}
Alive ({alive_count}): {alive_agents}
Eliminated: {eliminated_agents}

{public_info}

{private_info}

CURRENT ROUND DISCUSSION:
{discussion_context}

STRATEGY GUIDELINES:
- Analyze voting patterns and discussion history to identify suspicious behavior
- Look for contradictions in claims and voting records
- Consider who benefits from each elimination
- Build alliances but verify claims independently
- Use accusations strategically - false accusations can backfire
- Lying is an option when it benefits you (e.g., claim_role can be false)
- Reveal information carefully - timing and targets matter
- Use multiple subactions in one speech to be more effective

AVAILABLE ACTIONS:
You can use multiple discussion subactions in one response.

Universal subactions:
- general_discussion: General discussion, sharing opinions, or strategizing (no target)
- accuse: Accuse agent of being werewolf (REQUIRES TARGET: agent_id)
- defend: Defend yourself or another agent against accusations (REQUIRES TARGET: agent_id)
- reveal_identity: Reveal your TRUE role publicly (no target) - CANNOT LIE
- claim_role: Claim to have ANY role (can be true OR FALSE) (no target) - YOU CAN LIE

Role-specific subactions:
{role_specific_subactions}

TARGET REQUIREMENTS:
Subactions requiring targets (MUST include agent_id in DISCUSSION_TARGETS):
- accuse, defend, reveal_investigation, reveal_protected, reveal_healed_killed, reveal_werewolf

Subactions without targets:
- general_discussion, reveal_identity, claim_role, last_words

CRITICAL SUBACTION REQUIREMENT:
You MUST choose the appropriate subaction(s) for what you want to do. Do NOT use "general_discussion" when you want to:
- Accuse someone → Use "accuse" subaction
- Defend someone → Use "defend" subaction
- Claim a role → Use "claim_role" subaction
- Reveal your role → Use "reveal_identity" subaction

"general_discussion" is ONLY for pure discussion without specific actions. If you want to take any specific action, you MUST specify it in DISCUSSION_SUBACTIONS.

RESPONSE FORMAT:
ACTION: discuss
DISCUSSION_SUBACTIONS: [list of subactions]
DISCUSSION_TARGETS: [list of target lists, e.g., [[agent_1], [agent_2]] for accuse agent_1, defend agent_2]
CONTENT: [your message]
REASONING: [strategic reasoning]

CRITICAL: If you mention an agent in CONTENT for a target-required subaction, you MUST include their agent_id in DISCUSSION_TARGETS or the action will be invalid.

IMPORTANT: claim_role vs reveal_identity
- claim_role: You can claim ANY role (seer, doctor, werewolf, etc.) even if it's FALSE - use this to deceive
- reveal_identity: You can ONLY reveal your ACTUAL role - this is always TRUE information
- Example: If you're a villager, you could use claim_role to pretend you're the seer, but you cannot use reveal_identity unless you're actually the seer""",
        GamePhase.DAY_VOTING: """ROUND {round} - VOTING PHASE

IDENTITY: {agent_id} ({role})

{role_instruction}

CURRENT STATE:
Round: {round}
Alive ({alive_count}): {alive_agents}
Eliminated: {eliminated_agents}

{public_info}

CURRENT VOTES:
{current_votes}

STRATEGY GUIDELINES:
- Vote based on discussion analysis and voting patterns
- Consider who other players are voting for - bandwagon votes may indicate werewolf coordination
- Avoid random votes - use game history to inform decisions
- If you have information (seer results, etc.), consider when to reveal vs when to vote silently

VALID TARGETS: {valid_targets}
Cannot vote for yourself.

RESPONSE FORMAT:
ACTION: vote
TARGET: [agent_id]
REASONING: [why you're voting for this player]""",

        GamePhase.NIGHT_WEREWOLF: """ROUND {round} - NIGHT PHASE: WEREWOLF HUNT

IDENTITY: {agent_id} - WEREWOLF

{role_instruction}

WEREWOLF TEAMMATES: {werewolf_teammates}
You know each other's identities and must coordinate to eliminate villagers.

CURRENT STATE:
Round: {round}
Alive ({alive_count}): {alive_agents}
Eliminated: {eliminated_agents}

{public_info}

STRATEGY GUIDELINES:
- Target high-value roles (seer, doctor) to reduce village information
- Avoid killing teammates
- Consider who the village suspects - killing them may confirm suspicions
- Balance between eliminating threats and maintaining cover

VALID TARGETS: {valid_targets}
Cannot target fellow werewolves.

RESPONSE FORMAT:
ACTION: kill
TARGET: [agent_id]
REASONING: [why you're targeting this player]""",

        GamePhase.NIGHT_SEER: """ROUND {round} - NIGHT PHASE: SEER INVESTIGATION

IDENTITY: {agent_id} - SEER

{role_instruction}

INVESTIGATION POWER:
Each night, investigate one player to learn if they are WEREWOLF or NOT a werewolf.

PREVIOUS INVESTIGATIONS:
{investigation_results}

CURRENT STATE:
Round: {round}
Alive ({alive_count}): {alive_agents}
Eliminated: {eliminated_agents}

{public_info}

STRATEGY GUIDELINES:
- Investigate suspicious players or those with unclear voting patterns
- Prioritize players who haven't been investigated yet
- Consider investigating players who are being defended - may indicate werewolf protection
- Balance between confirming suspicions and gathering new information

VALID TARGETS: {valid_targets}
Cannot investigate yourself.

RESPONSE FORMAT:
ACTION: investigate
TARGET: [agent_id]
REASONING: [why you're investigating this player]""",

        GamePhase.NIGHT_DOCTOR: """ROUND {round} - NIGHT PHASE: DOCTOR PROTECTION

IDENTITY: {agent_id} - DOCTOR

{role_instruction}

PROTECTION POWER:
Protect one player from werewolf attacks each night. If werewolves target your protected player, they survive.
You can protect yourself.

CURRENT STATE:
Round: {round}
Alive ({alive_count}): {alive_agents}
Eliminated: {eliminated_agents}

{public_info}

STRATEGY GUIDELINES:
- Protect high-value roles (seer, confirmed villagers) or yourself
- Consider protecting players who revealed information - they may be werewolf targets
- Avoid predictable protection patterns
- Early game: protect yourself or random player. Late game: protect confirmed villagers.

VALID TARGETS: {valid_targets}

RESPONSE FORMAT:
ACTION: protect
TARGET: [agent_id]
REASONING: [why you're protecting this player]""",

        GamePhase.HUNTER_SHOOT: """ROUND {round} - HUNTER SHOOT (ELIMINATED)

IDENTITY: {agent_id} - HUNTER

{role_instruction}

You have been eliminated. As a hunter, you must shoot one player.

{hunter_shoot_context}

CURRENT STATE:
Round: {round}
Alive ({alive_count}): {alive_agents}
Eliminated: {eliminated_agents}

{public_info}

STRATEGY GUIDELINES:
- Shoot confirmed werewolves or highly suspicious players
- Consider who voted for you - may indicate werewolf coordination
- Avoid shooting confirmed villagers or yourself
- If uncertain, target players with suspicious voting patterns

ALIVE PLAYERS: {alive_agents}

RESPONSE FORMAT:
ACTION: shoot
TARGET: [agent_id]
REASONING: [why you're shooting this player]""",

        GamePhase.NIGHT_WITCH: """ROUND {round} - NIGHT PHASE: WITCH DECISION

IDENTITY: {agent_id} - WITCH

{role_instruction}

POTIONS (each usable once):
1. HEAL POTION: {heal_status}
   - Save the player killed by werewolves tonight
   - Must be used immediately after learning who was killed

2. POISON POTION: {poison_status}
   - Eliminate any player (alive or dead)
   - Use to eliminate confirmed werewolves or threats

{killed_info}

CURRENT STATE:
Round: {round}
Alive ({alive_count}): {alive_agents}
Eliminated: {eliminated_agents}

{public_info}

STRATEGY GUIDELINES:
- Heal: Save high-value roles (seer, doctor) or yourself. Early game: consider saving random player to gather info.
- Poison: Use on confirmed werewolves or highly suspicious players. Avoid poisoning without strong evidence.
- Timing: Don't waste potions early. Save for critical moments or confirmed threats.
- Information: Consider who was killed - may reveal werewolf targeting patterns.

OPTIONS:
{options_list}

RESPONSE FORMAT:
ACTION: [heal|poison|pass]
TARGET: [agent_id or none]
REASONING: [why you're making this decision]""",
    }

    # Role-specific instructions with win conditions and rules
    ROLE_INSTRUCTIONS = {
        AgentRole.VILLAGER: """ROLE: VILLAGER
GOAL: Eliminate all werewolves before werewolves equal or outnumber villagers.

STRATEGY:
- Analyze voting patterns and discussion history for inconsistencies
- Look for players who defend each other suspiciously
- Identify players who avoid voting or vote randomly
- Build trust with confirmed villagers through consistent voting
- Be cautious of role claims - verify through actions, not words
- Use discussion subactions to take specific actions:
  - Use "accuse" subaction to point out suspicious players
  - Use "defend" subaction to protect allies or yourself
  - Use "claim_role" subaction to pose as eliminated roles and gather information
- Create fake alliances to expose werewolves
  - Spread misinformation to confuse the werewolf team""",

        AgentRole.WEREWOLF: """ROLE: WEREWOLF
GOAL: Eliminate villagers until werewolves equal or outnumber them.

TEAMMATES: {werewolf_teammates}

STRATEGY:
- Coordinate kills with teammates (you know each other's identities)
- Blend in with villagers - vote with majority when safe
- Target high-value roles (seer, doctor) at night
- Avoid drawing attention - don't defend teammates too obviously
- Create confusion by voting against teammates occasionally to appear independent
- Use discussion subactions strategically:
  - Use "accuse" subaction to eliminate real threats or create false suspicions
  - Use "defend" subaction to protect teammates while appearing helpful
  - Use "claim_role" subaction to pretend to be villager roles (doctor, seer, witch)
- Spread misinformation about other players
- Create fake alliances and betray them during voting
- Your survival depends on convincing villagers you're innocent""",

        AgentRole.SEER: """ROLE: SEER
GOAL: Identify werewolves through investigation and help village eliminate them.

STRATEGY:
- Investigate suspicious players or those with unclear voting patterns
- Consider revealing investigation results strategically - timing matters
- Early game: investigate quietly. Late game: reveal confirmed werewolves
- Be cautious about revealing your role - werewolves will target you
- Cross-reference investigation results with voting patterns
- Use discussion subactions strategically:
  - Use "reveal_investigation" subaction to share investigation results
  - Use "accuse" subaction to point out confirmed werewolves
  - Use "claim_role" subaction to pretend to be other roles if your cover is blown""",

        AgentRole.DOCTOR: """ROLE: DOCTOR
GOAL: Protect key players from werewolf attacks and help identify threats.

STRATEGY:
- Protect high-value roles (seer, confirmed villagers) or yourself
- Early game: protect yourself or random player. Late game: protect confirmed villagers
- Consider protecting players who revealed information - they may be targets
- Avoid predictable protection patterns
- Reveal protection information strategically to help village identify werewolves
- **DECEPTION**: Lie to protect your identity
  - Use claim_role to pretend to be other roles
  - Use false accusations to deflect suspicion
  - Consider pretending to be the seer if the real seer is dead""",

        AgentRole.WITCH: """ROLE: WITCH
GOAL: Use potions strategically to help village eliminate werewolves.

STRATEGY:
- Heal: Save high-value roles or yourself. Early game: consider saving random player for info.
- Poison: Use on confirmed werewolves or highly suspicious players
- Don't waste potions early - save for critical moments
- Consider who was killed - reveals werewolf targeting patterns
- Reveal potion use strategically - can confirm werewolf kills or create confusion
- **DECEPTION**: Master of manipulation
  - Use claim_role to pretend to be any role (seer, doctor, etc.)
  - Use poison secretly - let villagers think it was werewolves
  - Reveal potion use selectively to create doubt and confusion
  - Lie about your potion status to manipulate voting""",

        AgentRole.HUNTER: """ROLE: HUNTER
GOAL: Help identify werewolves. If eliminated, shoot one player.

STRATEGY:
- If eliminated: shoot confirmed werewolves or highly suspicious players
- Consider who voted for you - may indicate werewolf coordination
- Avoid shooting confirmed villagers or yourself
- Use your threat strategically - players may avoid voting for you
- If uncertain, target players with suspicious voting patterns
- **DECEPTION**: Use your final shot as a weapon
  - Use claim_role to pretend to be other roles
  - Use accusations to manipulate pre-voting
  - Your final shot can be used to take a key player with you""",
    }

    @staticmethod
    def build_prompt(
        game_state: GameState,
        agent: AgentProfile,
        discussion_context: List[Dict[str, Any]] = None,
        storage=None,
        is_last_words: bool = False,
        public_memory: Optional['PublicGameMemory'] = None
    ) -> str:
        """
        Build a complete prompt for an agent based on game state and role.
        
        Args:
            game_state: Current game state
            agent: Agent profile to build prompt for
            discussion_context: Previous discussion messages in current round
            storage: GameLogger for accessing action history
            is_last_words: Whether this is a last words prompt
            public_memory: PublicGameMemory instance for full game history
            
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
            game_state, agent, discussion_context, storage, public_memory
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
        storage=None,
        public_memory: Optional['PublicGameMemory'] = None
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
            "alive_count": len(game_state.alive_agent_ids),
            "eliminated_agents": ", ".join(game_state.eliminated_agent_ids) or "none",
        }
        
        # Role-specific variables (needed before building role_instruction)
        if role == AgentRole.WEREWOLF:
            teammates = [
                aid for aid, r in game_state.role_assignments.items()
                if r == AgentRole.WEREWOLF.value and aid != agent_id
            ]
            variables["werewolf_teammates"] = ", ".join(teammates) if teammates else "none (you're alone)"
        else:
            variables["werewolf_teammates"] = "N/A"
        
        if role == AgentRole.WITCH:
            variables["heal_status"] = "AVAILABLE" if not game_state.witch_heal_used else "UNAVAILABLE (already used)"
            variables["poison_status"] = "AVAILABLE" if not game_state.witch_poison_used else "UNAVAILABLE (already used)"
            variables["heal_available"] = not game_state.witch_heal_used
            variables["poison_available"] = not game_state.witch_poison_used
        else:
            variables["heal_status"] = "N/A"
            variables["poison_status"] = "N/A"
            variables["heal_available"] = False
            variables["poison_available"] = False
        
        # Build role instruction (with dynamic formatting for werewolf)
        role_instruction_template = PromptBuilder.ROLE_INSTRUCTIONS.get(role, "Follow the rules of the game.")
        try:
            variables["role_instruction"] = role_instruction_template.format(**variables)
        except KeyError:
            # If formatting fails, use template as-is
            variables["role_instruction"] = role_instruction_template
        
        # Valid targets (exclude self and role-specific exclusions)
        valid_targets = PromptBuilder._get_valid_targets(game_state, agent)
        variables["valid_targets"] = ", ".join(valid_targets) or "none"
        
        # Public information (visible to all players)
        # Use memory system if available, otherwise fall back to storage-based history
        variables["public_info"] = PromptBuilder._build_public_info(
            game_state, agent_id, storage, public_memory
        )
        
        # Private information (role-specific)
        variables["private_info"] = PromptBuilder._build_private_info(game_state, agent)
        
        # Discussion context for sequential discussion
        variables["discussion_context"] = PromptBuilder._format_discussion_context(discussion_context)
        
        # Role-specific subactions for discussion phase
        variables["role_specific_subactions"] = PromptBuilder._get_role_specific_subactions(role)
        
        # Current votes (for voting phase)
        variables["current_votes"] = PromptBuilder._format_current_votes(game_state)
        
        # Role-specific investigation results
        if role == AgentRole.SEER:
            variables["investigation_results"] = PromptBuilder._format_investigation_results(
                game_state, agent_id
            )
        else:
            variables["investigation_results"] = "N/A"
        
        # Witch-specific killed info and options
        if role == AgentRole.WITCH:
            if game_state.killed_this_night:
                variables["killed_info"] = f"Werewolf victim: {game_state.killed_this_night} was targeted tonight."
            else:
                variables["killed_info"] = "No one was targeted by werewolves tonight."
            
            # Build options list based on availability
            options = []
            if variables["heal_available"] and game_state.killed_this_night:
                options.append(f"- heal [{game_state.killed_this_night}]: Save {game_state.killed_this_night}")
            elif variables["heal_available"]:
                options.append("- heal [killed_player]: Save killed player (no one killed tonight)")
            else:
                options.append("- heal: UNAVAILABLE (already used)")
            
            if variables["poison_available"]:
                options.append("- poison [agent_id]: Eliminate any player")
            else:
                options.append("- poison: UNAVAILABLE (already used)")
            
            options.append("- pass: Use no potion")
            variables["options_list"] = "\n".join(options)
        else:
            variables["killed_info"] = ""
            variables["options_list"] = "- pass: Use no potion this night"
        
        # Hunter shoot context (for HUNTER_SHOOT phase)
        if game_state.phase == GamePhase.HUNTER_SHOOT:
            is_night = game_state.metadata.get("hunter_shoot_is_night", False) if game_state.metadata else False
            if is_night:
                variables["hunter_shoot_context"] = (
                    "You were eliminated at night. Your shot will be revealed in the morning "
                    "together with other night deaths."
                )
            else:
                variables["hunter_shoot_context"] = (
                    "You were eliminated by vote during the day. You must shoot publicly, "
                    "right now, and everyone will see who you shoot."
                )
        else:
            variables["hunter_shoot_context"] = ""
        
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
    def _build_public_info(
        game_state: GameState,
        agent_id: str,
        storage=None,
        public_memory: Optional['PublicGameMemory'] = None
    ) -> str:
        """
        Build public information section visible to all players.
        
        Uses PublicGameMemory if available for full game history,
        otherwise falls back to storage-based limited history.
        """
        # Use memory system if available (provides full history)
        if public_memory:
            return PromptBuilder._build_public_info_from_memory(game_state, public_memory)
        
        # Fallback to storage-based limited history
        return PromptBuilder._build_public_info_from_storage(game_state, agent_id, storage)
    
    @staticmethod
    def _build_public_info_from_memory(
        game_state: GameState,
        public_memory: 'PublicGameMemory'
    ) -> str:
        """Build public info from PublicGameMemory (full game history)."""
        lines = ["GAME HISTORY"]
        
        # Basic game info
        lines.append(f"Round {game_state.round_number} | Phase: {game_state.phase.value}")
        lines.append(f"Alive: {len(game_state.alive_agent_ids)} | Eliminated: {len(game_state.eliminated_agent_ids)}")
        
        # Get memory summary (includes all discussions, votes, eliminations)
        memory_summary = public_memory.get_compact_summary()
        if memory_summary and memory_summary != "No game history yet.":
            lines.append(memory_summary)
        else:
            lines.append("(No previous game events recorded)")
        
        return "\n".join(lines)
    
    @staticmethod
    def _build_public_info_from_storage(
        game_state: GameState,
        agent_id: str,
        storage=None
    ) -> str:
        """Build public info from storage (limited history - fallback)."""
        lines = ["GAME HISTORY (LIMITED):"]
        
        # Previous round summaries
        if game_state.round_number > 1:
            lines.append(f"Round {game_state.round_number}")
            lines.append(f"Eliminated: {len(game_state.eliminated_agent_ids)} players")
        
        # Discussion history from storage (public actions only)
        if storage:
            all_actions = storage.get_game_actions(game_state.game_id)
            
            # Get discussion actions
            discussions = [
                a for a in all_actions
                if a.action_type.value == "discuss"
            ]
            if discussions:
                lines.append("\nRecent discussions:")
                for action in discussions[-5:]:  # Last 5 discussions
                    content = action.discussion_content or action.reasoning
                    lines.append(f"  {action.agent_id}: \"{content}\"")
            
            # Get voting results from previous rounds
            votes = [
                a for a in all_actions
                if a.action_type.value == "vote"
            ]
            if votes:
                lines.append("\nPrevious votes:")
                vote_summary = {}
                for action in votes[-10:]:
                    voter = action.agent_id
                    target = action.target_agent_id
                    vote_summary[voter] = target
                for voter, target in vote_summary.items():
                    lines.append(f"  {voter} -> {target}")
        
        return "\n".join(lines) if len(lines) > 1 else ""
    
    @staticmethod
    def _get_role_specific_subactions(role: AgentRole) -> str:
        """Get role-specific discussion subactions available to this agent."""
        subactions = []
        
        if role == AgentRole.SEER:
            subactions.append('- reveal_investigation: Reveal your investigation results about an agent (REQUIRES TARGET: agent_id)')

        if role == AgentRole.DOCTOR:
            subactions.append('- reveal_protected: Reveal which agent you protected last night (REQUIRES TARGET: agent_id)')

        if role == AgentRole.WITCH:
            subactions.append('- reveal_healed_killed: Reveal which agent you healed or poisoned (REQUIRES TARGET: agent_id)')

        if role == AgentRole.WEREWOLF:
            subactions.append('- reveal_werewolf: Reveal another werewolf teammate (REQUIRES TARGET: agent_id) [rare, usually not recommended]')
        
        if not subactions:
            return "(No role-specific subactions available)"
        
        return "\n".join(subactions)
    
    @staticmethod
    def _build_private_info(game_state: GameState, agent: AgentProfile) -> str:
        """Build private information section (role-specific secrets)."""
        role = agent.role
        
        # Most roles don't have additional private info beyond what's in the template
        if role == AgentRole.VILLAGER:
            return ""
        
        if role == AgentRole.HUNTER:
            return "HUNTER ABILITY: If eliminated, you can shoot one player."
        
        return ""
    
    @staticmethod
    def _format_discussion_context(discussion_context: List[Dict[str, Any]] = None) -> str:
        """Format previous discussion messages in current round for sequential context."""
        if not discussion_context:
            return "You are the first to speak this round."
        
        lines = []
        for msg in discussion_context:
            speaker = msg.get("agent_id", "unknown")
            content = msg.get("content", msg.get("discussion_content", ""))
            lines.append(f"{speaker}: \"{content}\"")
        
        return "\n".join(lines) if lines else "You are the first to speak this round."
    
    @staticmethod
    def _format_current_votes(game_state: GameState) -> str:
        """Format current voting status."""
        if not game_state.current_votes:
            return "No votes cast yet."
        
        lines = []
        for voter, target in game_state.current_votes.items():
            lines.append(f"{voter} -> {target}")
        
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
                results.append(f"Round {round_num}: {target} is {result}")
        
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

