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
• Identity reveals and role claims
• Investigation reveals and accuracy
• Accusation patterns and correctness
• Action counts by type
• Game progression and outcomes
• Error categorization and frequency
• Seer-specific metrics (reveals, unmasked wolf %, backfired %)
    """)


def demonstrate_dummy_agent_testing():
    """Demonstrate how dummy agents test the system implementation"""
    print_section("🤖 DUMMY AGENT TESTING SYSTEM", """
🧪 HOW DUMMY AGENTS TEST THE IMPLEMENTATION:

1. AUTOMATED TESTING FRAMEWORK:
   • Dummy agents simulate real AI agents with predictable behaviors
   • Each agent has role-specific strategies and decision patterns
   • 10% mistake rate intentionally introduced to test error handling
   • Probabilistic actions ensure varied test scenarios

2. ROLE-SPECIFIC BEHAVIOR TESTING:
   
   SEER AGENTS:
   • 60% chance to reveal investigation results
   • 30% chance to reveal identity as seer
   • 35% chance to make accusations
   • Tests investigation reveal patterns and accuracy

   DOCTOR AGENTS:
   • 50% chance to reveal protection actions
   • 30% chance to reveal identity as doctor
   • 35% chance to defend other players
   • Tests protection strategy and communication

   WITCH AGENTS:
   • 35% chance to reveal healing/killing actions
   • 30% chance to reveal identity as witch
   • 35% chance to make accusations
   • Tests healing/poisoning strategy and information sharing

   WEREWOLF AGENTS:
   • 60% chance to accuse villagers
   • 30% chance to defend teammates
   • 35% chance to claim fake roles
   • Tests deception strategies and team coordination

   VILLAGER AGENTS:
   • 40% chance to reveal identity
   • 30% chance to make accusations
   • 25% chance to defend others
   • Tests basic participation and reasoning

3. INVALID ACTION TESTING:
   • 10% mistake rate introduces rule violations
   • Tests system's ability to handle invalid actions
   • Examples: Voting for self, killing during day phase
   • Validates error logging and compliance tracking

4. SYSTEM COMPONENT TESTING:

   GAME ENGINE TESTING:
   • Action validation and rule enforcement
   • State transitions and phase management
   • Role-specific ability processing
   • Error handling and recovery

   EVALUATION SYSTEM TESTING:
   • Metrics calculation accuracy
   • Compliance tracking and reporting
   • Performance scoring algorithms
   • Multi-dimensional assessment

   LOGGING SYSTEM TESTING:
   • Event capture and serialization
   • Invalid action logging
   • Game completion tracking
   • JSONL format validation
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
   python scripts/run_dummy_simulation.py --num-agents 8 --num-werewolves 2 --has-hunter --has-witch --start-game

3. Parse metrics from the game:
   python parse_evaluation_metrics.py game_logs/game_<game_id>.jsonl

4. View the results:
   • Rule compliance percentages
   • Agent performance scores
   • Strategic effectiveness metrics
   • Communication quality analysis

The system will automatically:
• Assign roles to agents
• Run the game with all phases
• Evaluate each agent's performance
• Parse comprehensive metrics from game logs
• Display detailed reports in a clean format
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
    
    # 5. Dummy Agent Testing
    demonstrate_dummy_agent_testing()
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
