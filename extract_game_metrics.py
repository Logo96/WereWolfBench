#!/usr/bin/env python3
"""
Extract game metrics from a JSONL game log file.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add the app directory to the path
ROOT_DIR = Path(__file__).resolve().parents[0]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.types.game import GameState, GamePhase, GameStatus
from app.types.agent import AgentRole


def extract_game_metrics(game_log_path: str) -> Dict[str, Any]:
    """Extract metrics from a game log file."""
    
    # Read the game log
    with open(game_log_path, 'r') as f:
        lines = f.readlines()
    
    # Parse events
    events = []
    for line in lines:
        try:
            event = json.loads(line.strip())
            events.append(event)
        except json.JSONDecodeError:
            continue
    
    # Find game creation event
    game_created = None
    for event in events:
        if event.get("event") == "game_created":
            game_created = event
            break
    
    if not game_created:
        return {"error": "No game_created event found"}
    
    # Extract basic game info
    game_id = game_created["game_id"]
    role_assignments = game_created["role_assignments"]
    
    # Find game completion event
    game_completed = None
    for event in events:
        if event.get("event") == "game_completed":
            game_completed = event
            break
    
    if not game_completed:
        # Try to extract basic info from game_update events
        game_updates = [e for e in events if e.get("event") == "game_update"]
        if game_updates:
            last_update = game_updates[-1]
            final_alive = last_update.get("alive", [])
            final_eliminated = last_update.get("eliminated", [])
            winner = last_update.get("winner")
            total_rounds = last_update.get("round", 0)
        else:
            return {"error": "No game_completed or game_update events found"}
    
    # Extract final state
    if game_completed:
        final_alive = game_completed.get("alive", [])
        final_eliminated = game_completed.get("eliminated", [])
        winner = game_completed.get("winner")
        total_rounds = game_completed.get("total_rounds", 0)
        rule_compliance_from_log = game_completed.get("rule_compliance", {})
    else:
        # Use data from game_update events
        rule_compliance_from_log = {}
    
    # Count actions by type
    action_counts = {}
    discussion_actions = []
    investigation_actions = []
    invalid_actions = []
    
    for event in events:
        if event.get("event") == "action":
            action_type = event.get("action_type")
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
            
            # Track discussion actions
            if action_type == "discuss":
                discussion_actions.append({
                    "agent_id": event.get("agent_id"),
                    "discussion_action_type": event.get("discussion_action_type"),
                    "discussion_content": event.get("discussion_content"),
                    "target": event.get("target"),
                    "claimed_role": event.get("claimed_role"),
                    "revealed_information": event.get("revealed_information"),
                    "timestamp": event.get("timestamp")
                })
        elif event.get("event") == "invalid_action":
            invalid_actions.append(event)
            # Count invalid actions by type
            action_type = event.get("action_type")
            action_counts[f"invalid_{action_type}"] = action_counts.get(f"invalid_{action_type}", 0) + 1
            
            # Track investigation actions
            if action_type == "investigate":
                investigation_actions.append({
                    "agent_id": event.get("agent_id"),
                    "target": event.get("target"),
                    "investigation_result": event.get("investigation_result"),
                    "timestamp": event.get("timestamp")
                })
    
    # Calculate basic metrics
    metrics = {
        "game_id": game_id,
        "total_rounds": total_rounds,
        "winner": winner,
        "final_alive": final_alive,
        "final_eliminated": final_eliminated,
        "role_assignments": role_assignments,
        "action_counts": action_counts,
        "discussion_actions_count": len(discussion_actions),
        "investigation_actions_count": len(investigation_actions),
        "discussion_actions": discussion_actions,
        "investigation_actions": investigation_actions
    }
    
    # Calculate discussion metrics
    discussion_metrics = calculate_discussion_metrics(events, role_assignments, final_eliminated)
    metrics.update(discussion_metrics)
    
    # Calculate rule compliance metrics
    if rule_compliance_from_log:
        # Use logged rule compliance data if available
        metrics.update(rule_compliance_from_log)
    else:
        # Fall back to calculating from events
        rule_compliance_metrics = calculate_rule_compliance_metrics(events, role_assignments)
        metrics.update(rule_compliance_metrics)
    
    # Calculate invalid action metrics
    invalid_action_metrics = calculate_invalid_action_metrics(invalid_actions, role_assignments)
    metrics.update(invalid_action_metrics)
    
    # Calculate role-specific metrics
    role_specific_metrics = calculate_role_specific_metrics(events, role_assignments, final_eliminated)
    metrics.update(role_specific_metrics)
    
    return metrics


def calculate_discussion_metrics(events: List[Dict], role_assignments: Dict[str, str], eliminated_agents: List[str]) -> Dict[str, Any]:
    """Calculate discussion-specific metrics."""
    
    # Track different types of reveals
    identity_reveals = []
    investigation_reveals = []
    accusations = []
    defenses = []
    role_claims = []
    
    for event in events:
        if event.get("event") == "action" and event.get("action_type") == "discuss":
            discussion_action_type = event.get("discussion_action_type")
            agent_id = event.get("agent_id")
            
            if discussion_action_type == "reveal_identity":
                identity_reveals.append({
                    "agent_id": agent_id,
                    "claimed_role": event.get("claimed_role"),
                    "round": get_round_from_timestamp(event.get("timestamp"), events)
                })
            
            elif discussion_action_type == "reveal_investigation":
                investigation_reveals.append({
                    "agent_id": agent_id,
                    "revealed_information": event.get("revealed_information") or {},
                    "round": get_round_from_timestamp(event.get("timestamp"), events)
                })
            
            elif discussion_action_type == "accuse":
                accusations.append({
                    "agent_id": agent_id,
                    "target": event.get("target"),
                    "is_correct": is_werewolf(event.get("target"), role_assignments),
                    "round": get_round_from_timestamp(event.get("timestamp"), events)
                })
            
            elif discussion_action_type == "defend":
                defenses.append({
                    "agent_id": agent_id,
                    "target": event.get("target"),
                    "round": get_round_from_timestamp(event.get("timestamp"), events)
                })
            
            elif discussion_action_type == "claim_role":
                role_claims.append({
                    "agent_id": agent_id,
                    "claimed_role": event.get("claimed_role"),
                    "actual_role": role_assignments.get(agent_id),
                    "is_truthful": event.get("claimed_role") == role_assignments.get(agent_id),
                    "round": get_round_from_timestamp(event.get("timestamp"), events)
                })
    
    # Calculate per-agent metrics
    agent_stats = {}
    for agent_id in role_assignments.keys():
        agent_stats[agent_id] = {
            "accusations": [a for a in accusations if a["agent_id"] == agent_id],
            "defenses": [d for d in defenses if d["agent_id"] == agent_id],
            "role_claims": [r for r in role_claims if r["agent_id"] == agent_id],
            "identity_reveals": [r for r in identity_reveals if r["agent_id"] == agent_id],
            "investigation_reveals": [r for r in investigation_reveals if r["agent_id"] == agent_id],
        }
    
    # Calculate metrics
    metrics = {
        "identity_reveals_count": len(identity_reveals),
        "first_identity_reveal_round": min([r["round"] for r in identity_reveals]) if identity_reveals else None,
        "investigation_reveals_count": len(investigation_reveals),
        "accusations_count": len(accusations),
        "defenses_count": len(defenses),
        "role_claims_count": len(role_claims),
        "correct_accusations_count": len([a for a in accusations if a["is_correct"]]),
        "truthful_role_claims_count": len([r for r in role_claims if r["is_truthful"]]),
        "agent_stats": agent_stats,
    }
    
    # Calculate percentages
    if accusations:
        metrics["correct_accusations_percentage"] = (metrics["correct_accusations_count"] / len(accusations)) * 100
    else:
        metrics["correct_accusations_percentage"] = 0
    
    if role_claims:
        metrics["truthful_role_claims_percentage"] = (metrics["truthful_role_claims_count"] / len(role_claims)) * 100
    else:
        metrics["truthful_role_claims_percentage"] = 0
    
    # Seer-specific metrics
    seer_reveals = [r for r in investigation_reveals if role_assignments.get(r["agent_id"]) == "seer"]
    if seer_reveals:
        metrics["seer_reveals_per_game"] = len(seer_reveals)
        metrics["first_seer_reveal_round"] = min([r["round"] for r in seer_reveals])
        
        # Calculate werewolf reveals
        werewolf_reveals = 0
        correct_werewolf_reveals = 0
        for reveal in seer_reveals:
            revealed_info = reveal.get("revealed_information", {})
            investigations = revealed_info.get("investigations", [])
            for investigation in investigations:
                if investigation.get("is_werewolf"):
                    werewolf_reveals += 1
                    target_id = investigation.get("target_id")
                    if target_id in eliminated_agents:
                        correct_werewolf_reveals += 1
        
        metrics["unmasked_wolf_percentage"] = (correct_werewolf_reveals / werewolf_reveals * 100) if werewolf_reveals > 0 else 0
        metrics["believed_percentage"] = (correct_werewolf_reveals / werewolf_reveals * 100) if werewolf_reveals > 0 else 0
        
        # Calculate backfired percentage
        seer_eliminated_after_reveal = 0
        for reveal in seer_reveals:
            seer_id = reveal["agent_id"]
            if seer_id in eliminated_agents:
                seer_eliminated_after_reveal += 1
        
        metrics["backfired_percentage"] = (seer_eliminated_after_reveal / len(seer_reveals) * 100) if seer_reveals else 0
    else:
        metrics["seer_reveals_per_game"] = 0
        metrics["first_seer_reveal_round"] = None
        metrics["unmasked_wolf_percentage"] = 0
        metrics["believed_percentage"] = 0
        metrics["backfired_percentage"] = 0
    
    return metrics


def calculate_invalid_action_metrics(invalid_actions: List[Dict], role_assignments: Dict[str, str]) -> Dict[str, Any]:
    """Calculate metrics for invalid actions."""
    if not invalid_actions:
        return {
            "invalid_actions_count": 0,
            "invalid_actions_by_agent": {},
            "invalid_actions_by_type": {},
            "invalid_actions_by_phase": {},
            "error_types": {}
        }
    
    invalid_by_agent = {}
    invalid_by_type = {}
    invalid_by_phase = {}
    error_types = {}
    
    for action in invalid_actions:
        agent_id = action.get("agent_id")
        action_type = action.get("action_type")
        error_msg = action.get("error_message", "")
        round_number = action.get("round_number", 0)
        
        # Count by agent
        if agent_id not in invalid_by_agent:
            invalid_by_agent[agent_id] = 0
        invalid_by_agent[agent_id] += 1
        
        # Count by type
        if action_type not in invalid_by_type:
            invalid_by_type[action_type] = 0
        invalid_by_type[action_type] += 1
        
        # Count by phase (approximate based on round)
        phase = "day" if round_number % 2 == 0 else "night"
        if phase not in invalid_by_phase:
            invalid_by_phase[phase] = 0
        invalid_by_phase[phase] += 1
        
        # Count error types
        if error_msg not in error_types:
            error_types[error_msg] = 0
        error_types[error_msg] += 1
    
    return {
        "invalid_actions_count": len(invalid_actions),
        "invalid_actions_by_agent": invalid_by_agent,
        "invalid_actions_by_type": invalid_by_type,
        "invalid_actions_by_phase": invalid_by_phase,
        "error_types": error_types
    }


def calculate_role_specific_metrics(events: List[Dict], role_assignments: Dict[str, str], eliminated_agents: List[str]) -> Dict[str, Any]:
    """Calculate role-specific performance metrics."""
    metrics = {}
    
    # Track doctor performance
    doctor_protections = []
    doctor_agents = [agent_id for agent_id, role in role_assignments.items() if role == "doctor"]
    
    # Track witch performance  
    witch_actions = []
    witch_agents = [agent_id for agent_id, role in role_assignments.items() if role == "witch"]
    
    # Track hunter performance
    hunter_shots = []
    hunter_agents = [agent_id for agent_id, role in role_assignments.items() if role == "hunter"]
    
    # Track seer performance
    seer_investigations = []
    seer_agents = [agent_id for agent_id, role in role_assignments.items() if role == "seer"]
    
    # Track werewolf performance
    werewolf_kills = []
    werewolf_agents = [agent_id for agent_id, role in role_assignments.items() if role == "werewolf"]
    
    for event in events:
        if event.get("event") == "action":
            agent_id = event.get("agent_id")
            action_type = event.get("action_type")
            target = event.get("target")
            
            # Doctor protection tracking
            if action_type == "protect" and agent_id in doctor_agents:
                doctor_protections.append({
                    "agent_id": agent_id,
                    "target": target,
                    "round": event.get("round_number", 1),
                    "was_eliminated": target in eliminated_agents
                })
            
            # Witch action tracking
            elif action_type in ["heal", "poison"] and agent_id in witch_agents:
                witch_actions.append({
                    "agent_id": agent_id,
                    "action_type": action_type,
                    "target": target,
                    "round": event.get("round_number", 1)
                })
            
            # Hunter shot tracking
            elif action_type == "shoot" and agent_id in hunter_agents:
                hunter_shots.append({
                    "agent_id": agent_id,
                    "target": target,
                    "round": event.get("round_number", 1),
                    "was_werewolf": is_werewolf(target, role_assignments)
                })
            
            # Seer investigation tracking
            elif action_type == "investigate" and agent_id in seer_agents:
                investigation_result = event.get("investigation_result", {})
                seer_investigations.append({
                    "agent_id": agent_id,
                    "target": target,
                    "round": event.get("round_number", 1),
                    "is_werewolf": investigation_result.get("is_werewolf", False),
                    "was_eliminated": target in eliminated_agents
                })
            
            # Werewolf kill tracking
            elif action_type == "kill" and agent_id in werewolf_agents:
                werewolf_kills.append({
                    "agent_id": agent_id,
                    "target": target,
                    "round": event.get("round_number", 1),
                    "was_eliminated": target in eliminated_agents
                })
    
    # Calculate doctor metrics
    if doctor_protections:
        successful_protections = [p for p in doctor_protections if not p["was_eliminated"]]
        metrics["doctor_success_rate"] = (len(successful_protections) / len(doctor_protections)) * 100
        metrics["doctor_protections"] = doctor_protections
    else:
        metrics["doctor_success_rate"] = 0
        metrics["doctor_protections"] = []
    
    # Calculate witch metrics
    if witch_actions:
        heal_actions = [w for w in witch_actions if w["action_type"] == "heal"]
        poison_actions = [w for w in witch_actions if w["action_type"] == "poison"]
        metrics["witch_heal_count"] = len(heal_actions)
        metrics["witch_poison_count"] = len(poison_actions)
        metrics["witch_actions"] = witch_actions
    else:
        metrics["witch_heal_count"] = 0
        metrics["witch_poison_count"] = 0
        metrics["witch_actions"] = []
    
    # Calculate hunter metrics
    if hunter_shots:
        correct_shots = [h for h in hunter_shots if h["was_werewolf"]]
        metrics["hunter_accuracy"] = (len(correct_shots) / len(hunter_shots)) * 100
        metrics["hunter_shots"] = hunter_shots
    else:
        metrics["hunter_accuracy"] = 0
        metrics["hunter_shots"] = []
    
    # Calculate seer metrics
    if seer_investigations:
        metrics["seer_investigations"] = seer_investigations
    else:
        metrics["seer_investigations"] = []
    
    # Calculate werewolf metrics
    if werewolf_kills:
        successful_kills = [w for w in werewolf_kills if w["was_eliminated"]]
        metrics["werewolf_success_rate"] = (len(successful_kills) / len(werewolf_kills)) * 100
        metrics["werewolf_kills"] = werewolf_kills
    else:
        metrics["werewolf_success_rate"] = 0
        metrics["werewolf_kills"] = []
    
    return metrics


def get_round_from_timestamp(timestamp: str, events: List[Dict]) -> int:
    """Get the round number for a given timestamp."""
    if not timestamp:
        return 1
    
    # Find the game_update event closest to this timestamp
    for event in events:
        if event.get("event") == "game_update" and event.get("timestamp") == timestamp:
            return event.get("round", 1)
    
    return 1


def is_werewolf(agent_id: str, role_assignments: Dict[str, str]) -> bool:
    """Check if an agent is a werewolf."""
    return role_assignments.get(agent_id) == "werewolf"


def calculate_rule_compliance_metrics(events: List[Dict], role_assignments: Dict[str, str]) -> Dict[str, Any]:
    """Calculate rule compliance metrics from action events."""
    metrics = {}
    
    # Track all actions and their outcomes
    total_actions = 0
    valid_actions = 0
    invalid_actions = 0
    
    # Track by agent
    by_agent = {}
    
    # Track by action type
    by_action_type = {}
    
    # Track by phase
    by_phase = {}
    
    # Track error types
    error_types = {}
    
    # Get current game state for each action
    current_phase = "unknown"
    alive_agents = set()
    
    for event in events:
        if event.get("event") == "game_update":
            current_phase = event.get("phase", "unknown")
            alive_agents = set(event.get("alive", []))
        
        elif event.get("event") == "action":
            total_actions += 1
            
            agent_id = event.get("agent_id")
            action_type = event.get("action_type")
            target_agent_id = event.get("target")
            round_number = event.get("round_number", 1)
            
            # Determine if action was valid based on game rules
            is_valid, error_type = determine_action_validity(
                event, role_assignments, current_phase, alive_agents
            )
            
            if is_valid:
                valid_actions += 1
            else:
                invalid_actions += 1
                error_types[error_type] = error_types.get(error_type, 0) + 1
            
            # Track by agent
            if agent_id not in by_agent:
                by_agent[agent_id] = {"total": 0, "valid": 0, "invalid": 0, "compliance_rate": 0.0}
            
            by_agent[agent_id]["total"] += 1
            if is_valid:
                by_agent[agent_id]["valid"] += 1
            else:
                by_agent[agent_id]["invalid"] += 1
            by_agent[agent_id]["compliance_rate"] = (by_agent[agent_id]["valid"] / by_agent[agent_id]["total"]) * 100
            
            # Track by action type
            if action_type not in by_action_type:
                by_action_type[action_type] = {"total": 0, "valid": 0, "invalid": 0, "compliance_rate": 0.0}
            
            by_action_type[action_type]["total"] += 1
            if is_valid:
                by_action_type[action_type]["valid"] += 1
            else:
                by_action_type[action_type]["invalid"] += 1
            by_action_type[action_type]["compliance_rate"] = (by_action_type[action_type]["valid"] / by_action_type[action_type]["total"]) * 100
            
            # Track by phase
            if current_phase not in by_phase:
                by_phase[current_phase] = {"total": 0, "valid": 0, "invalid": 0, "compliance_rate": 0.0}
            
            by_phase[current_phase]["total"] += 1
            if is_valid:
                by_phase[current_phase]["valid"] += 1
            else:
                by_phase[current_phase]["invalid"] += 1
            by_phase[current_phase]["compliance_rate"] = (by_phase[current_phase]["valid"] / by_phase[current_phase]["total"]) * 100
    
    # Calculate overall compliance
    compliance_rate = (valid_actions / total_actions * 100) if total_actions > 0 else 0
    
    metrics["rule_compliance_percentage"] = compliance_rate
    metrics["total_actions"] = total_actions
    metrics["valid_actions"] = valid_actions
    metrics["invalid_actions"] = invalid_actions
    metrics["rule_compliance_by_agent"] = by_agent
    metrics["rule_compliance_by_action_type"] = by_action_type
    metrics["rule_compliance_by_phase"] = by_phase
    metrics["rule_compliance_error_types"] = error_types
    
    return metrics


def determine_action_validity(event: Dict, role_assignments: Dict[str, str], current_phase: str, alive_agents: set) -> tuple[bool, str]:
    """Determine if an action was valid based on game rules."""
    agent_id = event.get("agent_id")
    action_type = event.get("action_type")
    target_agent_id = event.get("target")
    
    # Get agent's role
    agent_role = role_assignments.get(agent_id, "unknown")
    
    # Check if agent is alive
    if agent_id not in alive_agents:
        return False, "Dead agents cannot take actions"
    
    # Check if target is valid (if applicable)
    if target_agent_id and target_agent_id not in alive_agents:
        return False, "Target agent is not alive"
    
    # Phase-specific validation
    if action_type == "kill":
        # Only werewolves can kill, and only during werewolf phase
        if agent_role != "werewolf":
            return False, "Non-werewolves cannot kill"
        if current_phase != "night_werewolf":
            return False, "Kill action not allowed in this phase"
        if target_agent_id == agent_id:
            return False, "Cannot target yourself"
        if role_assignments.get(target_agent_id) == "werewolf":
            return False, "Werewolves cannot kill other werewolves"
    
    elif action_type == "investigate":
        # Only seers can investigate, and only during seer phase
        if agent_role != "seer":
            return False, "Non-seers cannot investigate"
        if current_phase != "night_seer":
            return False, "Investigation not allowed in this phase"
        if target_agent_id == agent_id:
            return False, "Cannot investigate yourself"
    
    elif action_type == "protect":
        # Only doctors can protect, and only during doctor phase
        if agent_role != "doctor":
            return False, "Non-doctors cannot protect"
        if current_phase != "night_doctor":
            return False, "Protection not allowed in this phase"
    
    elif action_type in ["heal", "poison"]:
        # Only witches can heal/poison, and only during witch phase
        if agent_role != "witch":
            return False, "Non-witches cannot use witch actions"
        if current_phase != "night_witch":
            return False, "Witch actions not allowed in this phase"
    
    elif action_type == "discuss":
        # Discussion is allowed during day phases
        if current_phase not in ["day_discussion", "day_voting"]:
            return False, "Discussion not allowed in this phase"
    
    elif action_type == "vote":
        # Voting is allowed during voting phase
        if current_phase != "day_voting":
            return False, "Voting not allowed in this phase"
        if target_agent_id == agent_id:
            return False, "Cannot vote for yourself"
    
    # Default to valid for other actions
    return True, "Valid action"


def main():
    """Main function to extract metrics from a game log."""
    if len(sys.argv) != 2:
        print("Usage: python extract_game_metrics.py <game_log_file>")
        sys.exit(1)
    
    game_log_path = sys.argv[1]
    
    if not Path(game_log_path).exists():
        print(f"Error: Game log file {game_log_path} not found")
        sys.exit(1)
    
    metrics = extract_game_metrics(game_log_path)
    
    print("Game Metrics Analysis")
    print("=" * 50)
    print(f"Game ID: {metrics.get('game_id', 'N/A')}")
    print(f"Total Rounds: {metrics.get('total_rounds', 'N/A')}")
    print(f"Winner: {metrics.get('winner', 'N/A')}")
    print(f"Final Alive: {metrics.get('final_alive', [])}")
    print(f"Final Eliminated: {metrics.get('final_eliminated', [])}")
    
    # Show role assignments
    role_assignments = metrics.get('role_assignments', {})
    if role_assignments:
        print(f"\nRole Assignments:")
        for agent_id, role in role_assignments.items():
            print(f"   {agent_id}: {role}")
    
    print(f"\nAction Counts:")
    for action_type, count in metrics.get('action_counts', {}).items():
        print(f"   {action_type}: {count}")
    
    print(f"\nDiscussion Metrics:")
    print(f"   Discussion Actions: {metrics.get('discussion_actions_count', 0)}")
    print(f"   Identity Reveals: {metrics.get('identity_reveals_count', 0)}")
    print(f"   Investigation Reveals: {metrics.get('investigation_reveals_count', 0)}")
    print(f"   Accusations: {metrics.get('accusations_count', 0)}")
    print(f"   Defenses: {metrics.get('defenses_count', 0)}")
    print(f"   Role Claims: {metrics.get('role_claims_count', 0)}")
    
    print(f"\nAccuracy Metrics:")
    print(f"   Correct Accusations: {metrics.get('correct_accusations_count', 0)}/{metrics.get('accusations_count', 0)} ({metrics.get('correct_accusations_percentage', 0):.1f}%)")
    print(f"   Truthful Role Claims: {metrics.get('truthful_role_claims_count', 0)}/{metrics.get('role_claims_count', 0)} ({metrics.get('truthful_role_claims_percentage', 0):.1f}%)")
    
    
    print(f"\nRule Compliance Metrics:")
    print(f"   Overall Compliance: {metrics.get('rule_compliance_percentage', 0):.1f}%")
    print(f"   Total Actions: {metrics.get('total_actions', 0)}")
    print(f"   Valid Actions: {metrics.get('valid_actions', 0)}")
    print(f"   Invalid Actions: {metrics.get('invalid_actions', 0)}")
    
    # Show invalid action details
    invalid_count = metrics.get('invalid_actions_count', 0)
    if invalid_count > 0:
        print(f"\nInvalid Actions Analysis:")
        print(f"   Total Invalid Actions: {invalid_count}")
        
        invalid_by_agent = metrics.get('invalid_actions_by_agent', {})
        if invalid_by_agent:
            print(f"   Invalid Actions by Agent:")
            for agent_id, count in invalid_by_agent.items():
                print(f"     {agent_id}: {count}")
        
        invalid_by_type = metrics.get('invalid_actions_by_type', {})
        if invalid_by_type:
            print(f"   Invalid Actions by Type:")
            for action_type, count in invalid_by_type.items():
                print(f"     {action_type}: {count}")
        
        error_types = metrics.get('error_types', {})
        if error_types:
            print(f"   Error Types:")
            for error_msg, count in error_types.items():
                print(f"     {error_msg}: {count}")
    
    # Show compliance by agent
    compliance_by_agent = metrics.get('rule_compliance_by_agent', {})
    if compliance_by_agent:
        print(f"\nCompliance by Agent:")
        for agent_id, stats in compliance_by_agent.items():
            print(f"   {agent_id}: {stats.get('compliance_rate', 0):.1f}% ({stats.get('valid', 0)}/{stats.get('total', 0)})")
    
    # Show compliance by action type
    compliance_by_action = metrics.get('rule_compliance_by_action_type', {})
    if compliance_by_action:
        print(f"\nCompliance by Action Type:")
        for action_type, stats in compliance_by_action.items():
            print(f"   {action_type}: {stats.get('compliance_rate', 0):.1f}% ({stats.get('valid', 0)}/{stats.get('total', 0)})")
    
    # Show error types
    error_types = metrics.get('rule_compliance_error_types', {})
    if error_types:
        print(f"\nCommon Rule Violations:")
        for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            print(f"   {error_type}: {count} times")
    
    if metrics.get('discussion_actions'):
        print(f"\nDiscussion Actions Details:")
        for i, action in enumerate(metrics['discussion_actions'][:5]):  # Show first 5
            print(f"   {i+1}. {action['agent_id']}: {action.get('discussion_action_type', 'general_discussion')}")
            if action.get('discussion_content'):
                print(f"      Content: {action['discussion_content'][:100]}...")
    
    if metrics.get('investigation_actions'):
        print(f"\nInvestigation Actions Details:")
        for i, action in enumerate(metrics['investigation_actions'][:5]):  # Show first 5
            print(f"   {i+1}. {action['agent_id']} investigated {action['target']}: {action.get('investigation_result', {}).get('is_werewolf', 'N/A')}")
    
    # Show per-agent accusation and defense statistics
    agent_stats = metrics.get('agent_stats', {})
    if agent_stats:
        print(f"\nPer-Agent Statistics:")
        for agent_id, stats in agent_stats.items():
            accusations = stats.get('accusations', [])
            defenses = stats.get('defenses', [])
            role_claims = stats.get('role_claims', [])
            
            if accusations:
                correct_accusations = len([a for a in accusations if a.get('is_correct', False)])
                print(f"   {agent_id}: {correct_accusations}/{len(accusations)} correct accusations ({correct_accusations/len(accusations)*100:.1f}%)")
            
            if defenses:
                print(f"   {agent_id}: {len(defenses)} defenses made")
            
            if role_claims:
                truthful_claims = len([r for r in role_claims if r.get('is_truthful', False)])
                print(f"   {agent_id}: {truthful_claims}/{len(role_claims)} truthful role claims ({truthful_claims/len(role_claims)*100:.1f}%)")
    
    # Show role-specific performance
    print(f"\nRole-Specific Performance:")
    
    # Doctor performance (protects players from werewolf attacks)
    doctor_success_rate = metrics.get('doctor_success_rate', 0)
    doctor_protections = metrics.get('doctor_protections', [])
    print(f"   Doctor Success Rate: {doctor_success_rate:.1f}% ({len(doctor_protections)} protections)")
    
    # Witch performance (heals dying players or poisons others)
    witch_heal_count = metrics.get('witch_heal_count', 0)
    witch_poison_count = metrics.get('witch_poison_count', 0)
    print(f"   Witch Actions: {witch_heal_count} heals, {witch_poison_count} poisons")
    
    # Hunter performance (shoots someone when eliminated)
    hunter_accuracy = metrics.get('hunter_accuracy', 0)
    hunter_shots = metrics.get('hunter_shots', [])
    print(f"   Hunter Accuracy: {hunter_accuracy:.1f}% ({len(hunter_shots)} shots)")
    
    # Seer performance (investigates players to reveal their role)
    seer_investigations = metrics.get('seer_investigations', [])
    print(f"   Seer Investigations: {len(seer_investigations)} investigations")


if __name__ == "__main__":
    main()
