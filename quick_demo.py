#!/usr/bin/env python3
"""
Quick Werewolf Benchmark Demo
============================

A focused demo that shows the Green Agent evaluating White Agents
without requiring full system startup.
"""

import json
import sys
from pathlib import Path

# Add the app directory to the path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def print_section(title, content):
    """Print a formatted section"""
    print(f"\n{title}")
    print("=" * len(title))
    print(content)

def demonstrate_task_introduction():
    """Demonstrate the task introduction"""
    print_section("TASK INTRODUCTION", """
🎯 WHAT IS THE TASK?
The Werewolf benchmark evaluates AI agents in a social deduction game where:
• Agents must work together to identify and eliminate werewolves
• Each agent has a specific role with unique abilities  
• Agents must communicate, strategize, and make decisions
• The Green Agent (orchestrator) evaluates agent performance

🎭 THE WEREWOLF GAME:
• 8 agents: 2 werewolves, 1 seer, 1 doctor, 1 hunter, 1 witch, 2 villagers
• Night phases: Werewolves kill, Seer investigates, Doctor protects, Witch heals/poisons
• Day phases: Discussion and voting to eliminate suspected werewolves
• Win conditions: Eliminate all werewolves (villagers win) or equal/outnumber villagers (werewolves win)
    """)

def demonstrate_environment():
    """Demonstrate the environment"""
    print_section("ENVIRONMENT OVERVIEW", """
ENVIRONMENT ARCHITECTURE:
• Green Agent (Orchestrator): Manages game flow, evaluates agents
• White Agents (Participants): AI agents playing the game
• Game Engine: Processes actions, validates rules, tracks state
• Evaluation System: Calculates metrics and scores

GAME FLOW:
1. Role Assignment: Agents receive their roles secretly
2. Night Phase: Special roles act (werewolves, seer, doctor, witch)
3. Day Phase: All agents discuss and vote
4. Evaluation: Green Agent assesses performance
5. Repeat until game ends

EVALUATION METRICS:
• Rule Compliance: Percentage of actions following game rules
• Strategic Effectiveness: Quality of decision-making
• Communication Quality: Discussion and persuasion skills
• Role Performance: How well agents use their abilities
• Game Understanding: Awareness of game state and logic
    """)

def demonstrate_agent_actions():
    """Demonstrate available agent actions"""
    print_section("AGENT ACTIONS", """
ROLE-SPECIFIC ACTIONS:

WEREWOLF:
• kill <target>: Eliminate a villager
• discuss: Participate in day discussion
• vote <target>: Vote for elimination

SEER:
• investigate <target>: Check if target is werewolf
• reveal_investigation: Share investigation results
• discuss: Participate in day discussion
• vote <target>: Vote for elimination

DOCTOR:
• protect <target>: Protect target from werewolf attack
• reveal_protected: Share protection information
• discuss: Participate in day discussion
• vote <target>: Vote for elimination

WITCH:
• heal <target>: Save a killed player
• poison <target>: Eliminate a player
• reveal_healed_killed: Share healing/killing info
• discuss: Participate in day discussion
• vote <target>: Vote for elimination

HUNTER:
• shoot <target>: Eliminate someone when eliminated
• discuss: Participate in day discussion
• vote <target>: Vote for elimination

VILLAGER:
• discuss: Participate in day discussion
• vote <target>: Vote for elimination

DISCUSSION SUB-ACTIONS:
• reveal_identity: Claim your role
• accuse <target>: Accuse someone of being werewolf
• defend <target>: Defend someone from accusations
• claim_role <role>: Claim to have a specific role (can be a lie)
    """)

def demonstrate_green_agent_evaluation():
    """Demonstrate Green Agent evaluation"""
    print_section("🔍 GREEN AGENT EVALUATION", """
🎯 WHAT THE GREEN AGENT EVALUATES:

1. RULE COMPLIANCE:
   • Are actions valid for the agent's role/taken in the correct phase?
   • Example: Only werewolves can kill, only during night phase
   • Metrics: Overall compliance %, per-agent compliance

2. DISCUSSION BEHAVIOR:
   • Discussion participation and frequency
   • Identity reveals and role claims
   • Investigation reveals and accusations
   • Example: Seer sharing investigation results
   • Metrics: Discussion count, reveal patterns, accuracy rates

3. ACTION PATTERNS:
   • Voting behavior and target selection
   • Special ability usage (investigate, protect, heal, poison)
   • Example: Doctor protecting key players
   • Metrics: Action counts, target patterns, effectiveness

4. GAME OUTCOMES:
   • Win/loss contribution
   • Role-specific performance
   • Strategic impact on game progression
   • Example: Werewolves successfully eliminating villagers
   • Metrics: Survival rates, elimination patterns, win conditions

METRICS CALCULATED:
• Rule compliance percentages (overall, by agent, by action type, by phase)
• Discussion action counts and types
• Identity reveals and role claims (with truthfulness tracking)
• Investigation reveals and accuracy
• Accusation patterns and correctness
• Action counts by type
• Game progression and outcomes
• Error categorization and frequency
• Seer-specific metrics (reveals, unmasked wolf %, backfired %)
    """)

def show_concrete_examples():
    """Show concrete evaluation examples"""
    print_section("📊 CONCRETE EVALUATION EXAMPLES", """
🎯 SAMPLE AGENT SCORES:
  agent_0: 85.5/100 (Rule Compliance: 100%, Strategic: 80%, Communication: 90%)
  agent_1: 78.2/100 (Rule Compliance: 95%, Strategic: 75%, Communication: 85%)
  agent_2: 92.1/100 (Rule Compliance: 100%, Strategic: 95%, Communication: 88%)
  agent_3: 73.8/100 (Rule Compliance: 90%, Strategic: 70%, Communication: 75%)
  agent_4: 88.9/100 (Rule Compliance: 100%, Strategic: 85%, Communication: 92%)
  agent_5: 81.3/100 (Rule Compliance: 95%, Strategic: 80%, Communication: 82%)
  agent_6: 76.4/100 (Rule Compliance: 90%, Strategic: 75%, Communication: 78%)
  agent_7: 89.7/100 (Rule Compliance: 100%, Strategic: 90%, Communication: 87%)

📏 RULE COMPLIANCE ANALYSIS:
  Total Actions: 25
  Valid Actions: 24
  Invalid Actions: 1
  Compliance Rate: 96.2%

🔍 SPECIFIC EVALUATION EXAMPLES:

Example 1 - Rule Compliance:
• Agent tries to kill during day phase → INVALID (0 points)
• Agent votes for themselves → INVALID (0 points)
• Agent investigates as non-seer → INVALID (0 points)

Example 2 - Strategic Effectiveness:
• Seer investigates likely werewolf → HIGH SCORE (90+ points)
• Villager votes for confirmed werewolf → HIGH SCORE (85+ points)
• Werewolf votes for other werewolf → LOW SCORE (20 points)

Example 3 - Communication Quality:
• Agent provides detailed reasoning → HIGH SCORE (90+ points)
• Agent makes relevant accusations → HIGH SCORE (85+ points)
• Agent stays silent all game → LOW SCORE (30 points)
    """)

def explain_design_notes():
    """Explain design notes and test case selection"""
    print_section("📝 DESIGN NOTES", """
🧪 TEST CASE GENERATION:

1. DUMMY AGENT STRATEGY:
   • Created probabilistic dummy agents with different behaviors
   • Some agents follow rules perfectly (100% compliance)
   • Some agents make occasional mistakes (80-90% compliance)
   • Some agents have strategic preferences (role-specific actions)

2. ROLE DIVERSITY:
   • Each role has unique capabilities and constraints
   • Test cases cover all role-specific actions
   • Include edge cases (self-targeting, wrong phases, etc.)

3. SCENARIO VARIETY:
   • Different game lengths (short vs long games)
   • Different win conditions (werewolf vs villager wins)
   • Different communication patterns (silent vs verbose agents)

🎯 WHY THESE CASES TEST RELIABILITY:

1. RULE COMPLIANCE TESTING:
   • Tests if agents understand game rules
   • Identifies agents that make invalid actions
   • Measures consistency in rule-following

2. STRATEGIC EFFECTIVENESS:
   • Tests decision-making quality
   • Measures impact on game outcomes
   • Identifies agents with good/bad strategies

3. COMMUNICATION ASSESSMENT:
   • Tests discussion participation
   • Measures content quality and relevance
   • Identifies persuasive vs ineffective communicators

4. ROLE PERFORMANCE:
   • Tests specialized ability usage
   • Measures role-specific effectiveness
   • Identifies agents that excel in their roles

5. ADAPTABILITY:
   • Tests response to changing conditions
   • Measures strategy adjustment
   • Identifies flexible vs rigid agents

🔬 EVALUATION RELIABILITY:

• Automated scoring eliminates human bias
• Consistent metrics across all agents
• Quantitative measures for objective comparison
• Multi-dimensional assessment for comprehensive evaluation
• Real-time feedback for immediate assessment
    """)

def run_actual_demo():
    """Run an actual demo with the system"""
    print_section("RUNNING ACTUAL DEMO", """
To run a complete demo with the Werewolf benchmark system:

1. Start the Green Agent (Orchestrator):
   python -m app.main &

2. Start White Agents (Dummy Agents):
   python scripts/run_dummy_simulation.py --num-agents 8 --num-werewolves 2 --has-seer --has-doctor --has-hunter --has-witch --start-game

3. Extract metrics from the game:
   python extract_game_metrics.py game_logs/game_<game_id>.jsonl

4. View the results:
   • Rule compliance percentages
   • Agent performance scores
   • Strategic effectiveness metrics
   • Communication quality analysis

The system will automatically:
• Assign roles to agents
• Run the game with all phases
• Evaluate each agent's performance
• Calculate comprehensive metrics
• Generate detailed reports
    """)

def main():
    """Run the complete demo"""
    print("🎮 Werewolf Benchmark Demo")
    print("=" * 50)
    
    # 1. Task Introduction
    demonstrate_task_introduction()
    input("\nPress Enter to continue...")
    
    # 2. Environment Overview
    demonstrate_environment()
    input("\nPress Enter to continue...")
    
    # 3. Agent Actions
    demonstrate_agent_actions()
    input("\nPress Enter to continue...")
    
    # 4. Green Agent Evaluation
    demonstrate_green_agent_evaluation()
    input("\nPress Enter to continue...")
    
    # 5. Concrete Examples
    show_concrete_examples()
    input("\nPress Enter to continue...")
    
    # 6. Design Notes
    explain_design_notes()
    input("\nPress Enter to continue...")
    
    # 7. Actual Demo Instructions
    run_actual_demo()
    
    print("\nDemo completed!")
    print("Next step is AgentBeats integration!")

if __name__ == "__main__":
    main()
