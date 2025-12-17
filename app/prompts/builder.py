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
        GamePhase.DAY_DISCUSSION: """🌅 DAY BREAKS - ROUND {round} DISCUSSION PHASE 🌅

The sun rises over the village. Last night was quiet... or was it? It's time to discuss what happened and decide who to eliminate.

═══════════════════════════════════════════════════════════
YOUR IDENTITY: {agent_id} ({role})
═══════════════════════════════════════════════════════════

{role_instruction}

═══════════════════════════════════════════════════════════
CURRENT SITUATION
═══════════════════════════════════════════════════════════
Round: {round}
Alive Players ({alive_count}): {alive_agents}
Eliminated Players: {eliminated_agents}

{public_info}

{private_info}

═══════════════════════════════════════════════════════════
WHAT OTHERS HAVE SAID THIS ROUND
═══════════════════════════════════════════════════════════
{discussion_context}

═══════════════════════════════════════════════════════════
YOUR TURN TO SPEAK
═══════════════════════════════════════════════════════════
This is your chance to speak to the village. What will you say?

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC OPTIONS:
# - Share observations about suspicious behavior
# - Accuse someone you believe is a werewolf
# - Defend yourself or someone else from accusations
# - Claim a role (if you're Seer/Doctor/etc. and want to reveal)
# - Reveal investigation results (if you're the Seer)
# - Ask questions to gather information
# - Create alliances or build trust
#
# Remember: Werewolves are listening. Choose your words carefully.

Respond with your message to the village (keep it under 100 words):
ACTION: discuss
DISCUSSION_SUBACTIONS: [list of subactions, e.g., accuse, defend, general_discussion]
DISCUSSION_TARGETS: [list of target lists, e.g., [[agent_1, agent_2], [agent_3]] means accuse both agent_1 and agent_2, defend agent_3]
CONTENT: [your message]
REASONING: [why you're saying this]

⚠️ CRITICAL REQUIREMENT - TARGETS ARE MANDATORY FOR CERTAIN SUBACTIONS:

SUBACTIONS THAT REQUIRE TARGETS (you MUST include agent_id):
- "accuse" → MUST include at least one target (the agent you're accusing)
- "defend" → MUST include at least one target (the agent you're defending)
- "reveal_investigation" → MUST include target (the agent whose investigation you're revealing)
- "reveal_protected" → MUST include target (the agent you protected)
- "reveal_werewolf" → MUST include target (the werewolf you're revealing)

SUBACTIONS THAT DON'T REQUIRE TARGETS:
- "general_discussion" → no target needed
- "reveal_identity" → no target needed (you're revealing yourself)
- "claim_role" → no target needed (you're claiming your own role)
- "last_words" → no target needed

TARGET FORMAT REQUIREMENTS:
- You MUST use the exact format: agent_X (e.g., agent_0, agent_1, agent_2, etc.)
- The DISCUSSION_TARGETS list must match DISCUSSION_SUBACTIONS in length
- Each subaction can have multiple targets: [[agent_1, agent_2], [agent_3]] means accuse both agent_1 AND agent_2, defend agent_3
- If you mention someone in your CONTENT but don't include them in DISCUSSION_TARGETS for a target-required subaction, your action will be INVALID
- Example: If you say "I think agent_1 is suspicious" but use "accuse" without including agent_1 in DISCUSSION_TARGETS, your accusation will be IGNORED

VALIDATION: Your response will be rejected if you use a target-required subaction without providing the corresponding target(s).""",

        GamePhase.DAY_VOTING: """🗳️ VOTING TIME - ROUND {round} 🗳️

Discussion is over. The village must now vote to eliminate someone.

═══════════════════════════════════════════════════════════
YOUR IDENTITY: {agent_id} ({role})
═══════════════════════════════════════════════════════════

{role_instruction}

═══════════════════════════════════════════════════════════
CURRENT SITUATION
═══════════════════════════════════════════════════════════
Round: {round}
Alive Players ({alive_count}): {alive_agents}
Eliminated Players: {eliminated_agents}

{public_info}

═══════════════════════════════════════════════════════════
CURRENT VOTES
═══════════════════════════════════════════════════════════
{current_votes}

═══════════════════════════════════════════════════════════
YOUR VOTE
═══════════════════════════════════════════════════════════
You must vote to eliminate one player.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC CONSIDERATIONS:
# - Vote for the player you believe is most likely a werewolf
# - Consider voting patterns - are others coordinating?
# - Think about who would benefit from eliminating each player
# - Remember: Werewolves will vote together to eliminate villagers
# - If you're a werewolf, vote strategically to eliminate threats or create misdirection

Valid targets: {valid_targets}
(You cannot vote for yourself)

Respond with your vote:
ACTION: vote
TARGET: [agent_id to eliminate]
REASONING: [why you're voting for this player]""",

        GamePhase.NIGHT_WEREWOLF: """🌙 NIGHT FALLS - WEREWOLF HUNT (Round {round}) 🌙

The sun sets and darkness envelops the village. The werewolves awaken...

═══════════════════════════════════════════════════════════
YOUR IDENTITY: {agent_id} - WEREWOLF
═══════════════════════════════════════════════════════════

{role_instruction}

═══════════════════════════════════════════════════════════
YOUR PACK
═══════════════════════════════════════════════════════════
Your fellow werewolves: {werewolf_teammates}
Work together to eliminate the villagers. You know each other's identities.

═══════════════════════════════════════════════════════════
CURRENT SITUATION
═══════════════════════════════════════════════════════════
Round: {round}
Alive Players ({alive_count}): {alive_agents}
Eliminated Players: {eliminated_agents}

{public_info}

═══════════════════════════════════════════════════════════
YOUR HUNT
═══════════════════════════════════════════════════════════
Choose your target for tonight.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC TARGETS TO CONSIDER:
# - The Seer (if you've identified them) - eliminate them before they reveal findings
# - The Doctor (if you've identified them) - they can protect others
# - Strong villagers who are organizing the village
# - Players who seem suspicious of you or your teammates
# - Create misdirection by targeting unexpected players

Valid targets: {valid_targets}
(You cannot target fellow werewolves)

Respond with your kill target:
ACTION: kill
TARGET: [agent_id to kill]
REASONING: [why you're targeting this player]""",

        GamePhase.NIGHT_SEER: """🔮 NIGHT PHASE - SEER INVESTIGATION (Round {round}) 🔮

While the village sleeps, your mystical powers awaken. You can see through deception...

═══════════════════════════════════════════════════════════
YOUR IDENTITY: {agent_id} - THE SEER
═══════════════════════════════════════════════════════════

{role_instruction}

═══════════════════════════════════════════════════════════
YOUR INVESTIGATION POWER
═══════════════════════════════════════════════════════════
Each night, you can investigate one player to learn their true nature:
- You will learn if they are a WEREWOLF or NOT a werewolf

PREVIOUS INVESTIGATIONS:
{investigation_results}

═══════════════════════════════════════════════════════════
CURRENT SITUATION
═══════════════════════════════════════════════════════════
Round: {round}
Alive Players ({alive_count}): {alive_agents}
Eliminated Players: {eliminated_agents}

{public_info}

═══════════════════════════════════════════════════════════
YOUR INVESTIGATION
═══════════════════════════════════════════════════════════
Choose who to investigate tonight.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC CONSIDERATIONS:
# - Investigate players who seem suspicious or are acting strangely
# - Investigate players who are making strong accusations (could be werewolves deflecting)
# - Investigate players who are being quiet or avoiding discussion
# - Consider investigating players who others trust (verify their innocence)
# - Don't waste investigations on players you're already confident about

Valid targets: {valid_targets}
(You cannot investigate yourself)

Respond with your investigation target:
ACTION: investigate
TARGET: [agent_id to investigate]
REASONING: [why you're investigating this player]""",

        GamePhase.NIGHT_DOCTOR: """💊 NIGHT PHASE - DOCTOR PROTECTION (Round {round}) 💊

While darkness falls, you prepare your healing arts. You can save one person tonight...

═══════════════════════════════════════════════════════════
YOUR IDENTITY: {agent_id} - THE DOCTOR
═══════════════════════════════════════════════════════════

{role_instruction}

═══════════════════════════════════════════════════════════
YOUR PROTECTION POWER
═══════════════════════════════════════════════════════════
Each night, you can protect one player from werewolf attacks.
- If werewolves target the player you protect, they will survive
- You can protect yourself
- You can only protect one person per night

═══════════════════════════════════════════════════════════
CURRENT SITUATION
═══════════════════════════════════════════════════════════
Round: {round}
Alive Players ({alive_count}): {alive_agents}
Eliminated Players: {eliminated_agents}

{public_info}

═══════════════════════════════════════════════════════════
YOUR PROTECTION
═══════════════════════════════════════════════════════════
Choose who to protect tonight.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC CONSIDERATIONS:
# - Protect yourself if you're suspicious or revealed
# - Protect the Seer if they've revealed themselves
# - Protect players who are organizing the village
# - Protect players who seem like likely werewolf targets
# - Consider protecting suspicious players (they might be werewolves, but better safe than sorry)
# - Don't waste protection on players unlikely to be targeted

Valid targets: {valid_targets}

Respond with your protection target:
ACTION: protect
TARGET: [agent_id to protect]
REASONING: [why you're protecting this player]""",

        GamePhase.NIGHT_WITCH: """🧪 NIGHT PHASE - WITCH DECISION (Round {round}) 🧪

The night deepens. Your potions await your command. Will you use them?

═══════════════════════════════════════════════════════════
YOUR IDENTITY: {agent_id} - THE WITCH
═══════════════════════════════════════════════════════════

{role_instruction}

═══════════════════════════════════════════════════════════
YOUR POTIONS
═══════════════════════════════════════════════════════════
You have TWO potions, each usable only ONCE:

1. HEAL POTION: {heal_status}
   - Can save the player killed by werewolves tonight
   - Use it immediately after learning who was killed
   - Once used, it's gone forever

2. POISON POTION: {poison_status}
   - Can eliminate ANY player (alive or dead)
   - Use it to eliminate confirmed werewolves or threats
   - Once used, it's gone forever

{killed_info}

═══════════════════════════════════════════════════════════
CURRENT SITUATION
═══════════════════════════════════════════════════════════
Round: {round}
Alive Players ({alive_count}): {alive_agents}
Eliminated Players: {eliminated_agents}

{public_info}

═══════════════════════════════════════════════════════════
YOUR DECISION
═══════════════════════════════════════════════════════════
Decide whether to use a potion tonight. Each potion can only be used once.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC CONSIDERATIONS:
# - Use HEAL to save the Seer, Doctor, or other key players
# - Use POISON to eliminate confirmed werewolves or major threats
# - Save potions for critical moments - you only get one of each
# - Don't waste potions on uncertain situations
# - Consider: Is this the right time to act, or should you wait?

Your options:
- heal [killed_player] - Save someone killed by werewolves (if heal available)
- poison [agent_id] - Eliminate any player (if poison available)
- pass - Use no potion this night

Respond with your decision:
ACTION: [heal|poison|pass]
TARGET: [agent_id or none]
REASONING: [why you're making this decision]""",
    }
    
    # Role-specific instructions with win conditions and strategic guidance
    ROLE_INSTRUCTIONS = {
        AgentRole.VILLAGER: """YOUR ROLE: VILLAGER
YOUR GOAL: Eliminate all werewolves before they eliminate the villagers.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC GUIDANCE:
# - Pay close attention to everyone's behavior and statements
# - Look for inconsistencies, suspicious voting patterns, or unusual accusations
# - Trust the Seer if they reveal their identity and findings
# - Be cautious of false accusations - werewolves will try to frame innocent players
# - Build alliances with other villagers, but verify claims carefully
# - If you're eliminated, the village loses a valuable voice

WHAT YOU KNOW:
- You are innocent and want to protect the village
- Werewolves are among the players, but you don't know who they are
- You must work with other villagers to identify threats through discussion and voting""",

        AgentRole.WEREWOLF: """YOUR ROLE: WEREWOLF
YOUR GOAL: Eliminate enough villagers so that werewolves equal or outnumber them.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC GUIDANCE:
# - You know your fellow werewolves: {werewolf_teammates}
# - Work together strategically, but NEVER reveal your teammates publicly
# - Blend in during discussions - act like a concerned villager
# - Deflect suspicion away from yourself and your teammates
# - Consider framing innocent players to create confusion
# - Vote strategically to eliminate threats (Seer, Doctor) or create misdirection
# - If villagers identify you, try to create doubt or shift blame

WHAT YOU KNOW:
- Your werewolf teammates: {werewolf_teammates} (work together but secretly)
- Who the villagers are (your targets)
- You must eliminate villagers without being discovered
- If you're caught, you're eliminated and your team loses a member""",

        AgentRole.SEER: """YOUR ROLE: SEER
YOUR GOAL: Use your investigation power to identify werewolves and help the village eliminate them.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC GUIDANCE:
# - Each night you can investigate one player to learn if they're a werewolf
# - Use your investigations wisely - you're a prime target for werewolves
# - Consider revealing your identity strategically, but beware of counter-claims
# - Share your findings carefully - werewolves may try to discredit you
# - Protect yourself - if werewolves know you're the Seer, they'll target you
# - Build trust with confirmed villagers through your investigations

WHAT YOU KNOW:
- Each night you can investigate one player to learn if they're a werewolf
- Your investigation results (see below)
- Werewolves will try to eliminate you if they discover your role""",

        AgentRole.DOCTOR: """YOUR ROLE: DOCTOR
YOUR GOAL: Protect key players from werewolf attacks and help the village identify threats.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC GUIDANCE:
# - Each night you can protect one player from being killed
# - Protect yourself early if you're suspicious, or protect likely targets (Seer, other key roles)
# - Don't reveal your role unless necessary - werewolves will target you
# - Consider protecting players who seem suspicious - they might be werewolves trying to frame others
# - Your protection is powerful but limited - use it strategically
# - Work with the Seer if they reveal themselves - protect them!

WHAT YOU KNOW:
- Each night you can protect one player from werewolf attacks
- If werewolves target the player you protect, they will survive
- You can protect yourself
- Werewolves will target you if they discover your role""",

        AgentRole.WITCH: """YOUR ROLE: WITCH
YOUR GOAL: Use your potions to help the village eliminate werewolves.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC GUIDANCE:
# - You have TWO potions: one heal (save a killed player) and one poison (kill any player)
# - Use your heal potion wisely - you can only use it once
# - Use your poison potion to eliminate confirmed werewolves or suspicious players
# - Don't reveal your role unless necessary - werewolves will target you
# - Consider saving the Seer or Doctor if they're killed
# - Your potions are powerful but limited - use them strategically

WHAT YOU KNOW:
- You have TWO potions, each usable only ONCE:
  1. HEAL POTION: {heal_status} (can save the player killed by werewolves tonight)
  2. POISON POTION: {poison_status} (can eliminate any player)
- Werewolves will target you if they discover your role""",

        AgentRole.HUNTER: """YOUR ROLE: HUNTER
YOUR GOAL: Help identify werewolves. If eliminated, you can take one player with you.

# BASELINE VERSION: Strategic guidance removed - only rules provided
# STRATEGIC GUIDANCE:
# - You're a powerful role - werewolves will be cautious about eliminating you
# - Use your threat to deter werewolves from targeting you
# - If you're eliminated, you MUST shoot someone - choose wisely
# - Consider shooting confirmed werewolves or highly suspicious players
# - Your shot is your final act - make it count for the village

WHAT YOU KNOW:
- If eliminated, you can shoot one player (they die immediately)
- You must shoot someone if you are eliminated""",
    }

    @staticmethod
    def build_prompt(
        game_state: GameState,
        agent: AgentProfile,
        discussion_context: List[Dict[str, Any]] = None,
        storage=None,
        is_last_words: bool = False
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
            variables["heal_status"] = "AVAILABLE" if not game_state.witch_heal_used else "USED"
            variables["poison_status"] = "AVAILABLE" if not game_state.witch_poison_used else "USED"
        else:
            variables["heal_status"] = "N/A"
            variables["poison_status"] = "N/A"
        
        # Build role instruction (with dynamic formatting for werewolf)
        role_instruction_template = PromptBuilder.ROLE_INSTRUCTIONS.get(role, "Follow the rules of the game.")
        try:
            variables["role_instruction"] = role_instruction_template.format(**variables)
        except KeyError:
            # If formatting fails, use template as-is
            variables["role_instruction"] = role_instruction_template
        
        # BASELINE VERSION: Remove strategic language from reasoning prompts
        # Replace "strategic" with neutral language in response format instructions
        
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
        
        # Role-specific investigation results
        if role == AgentRole.SEER:
            variables["investigation_results"] = PromptBuilder._format_investigation_results(
                game_state, agent_id
            )
        else:
            variables["investigation_results"] = "N/A"
        
        # Witch-specific killed info
        if role == AgentRole.WITCH:
            if game_state.killed_this_night:
                variables["killed_info"] = f"WEREWOLF VICTIM: {game_state.killed_this_night} was targeted by werewolves tonight."
            else:
                variables["killed_info"] = "No one was targeted by werewolves tonight."
        else:
            variables["killed_info"] = ""
        
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
            return "You are the first to speak this round. Set the tone for the discussion."
        
        lines = []
        for msg in discussion_context:
            speaker = msg.get("agent_id", "unknown")
            content = msg.get("content", msg.get("discussion_content", ""))
            if len(content) > 150:
                content = content[:147] + "..."
            lines.append(f"  {speaker}: \"{content}\"")
        
        return "\n".join(lines) if lines else "You are the first to speak this round."
    
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

