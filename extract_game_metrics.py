#!/usr/bin/env python3
"""
Extract game metrics from a JSONL game log file.
Only extracts metrics specified in the agent-level metric specification.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
import statistics

# Add the app directory to the path
ROOT_DIR = Path(__file__).resolve().parents[0]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def extract_game_metrics(game_log_path: str) -> Dict[str, Any]:
    """Extract metrics from a game log file."""
    
    # Read the game log
    with open(game_log_path, 'r', encoding='utf-8') as f:
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
    all_agent_ids = list(role_assignments.keys())
    
    # Extract agent model information from agents_assigned event
    agent_models = {}
    for event in events:
        if event.get("event") == "agents_assigned":
            for agent in event.get("agents", []):
                agent_id = agent.get("id")
                model = agent.get("model")
                if agent_id and model:
                    agent_models[agent_id] = model
    
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
    else:
        final_alive = game_completed.get("alive", [])
        final_eliminated = game_completed.get("eliminated", [])
        winner = game_completed.get("winner")
        total_rounds = game_completed.get("total_rounds", 0)
    
    # Determine which team won
    if winner == "werewolves":
        winning_team = "werewolves"
    elif winner == "villagers":
        winning_team = "villagers"
    else:
        winning_team = None
    
    # Track elimination rounds for each agent
    elimination_rounds = {}
    for event in events:
        if event.get("event") == "game_update":
            round_num = event.get("round", 0)
            eliminated = event.get("eliminated", [])
            for agent_id in eliminated:
                if agent_id not in elimination_rounds:
                    elimination_rounds[agent_id] = round_num
    
    # Initialize per-agent metrics
    agent_metrics = {}
    for agent_id in all_agent_ids:
        role = role_assignments.get(agent_id)
        agent_won = False
        if winning_team:
            if winning_team == "werewolves" and role == "werewolf":
                agent_won = True
            elif winning_team == "villagers" and role != "werewolf":
                agent_won = True
        
        agent_metrics[agent_id] = {
            "agent_won_game": agent_won,
            "agent_survived": agent_id in final_alive,
            "agent_elimination_round": elimination_rounds.get(agent_id, total_rounds),
        }
    
    # Calculate all metrics
    calculate_core_metrics(agent_metrics, events, role_assignments, final_alive, final_eliminated, total_rounds, winner)
    calculate_role_specific_metrics(agent_metrics, events, role_assignments, final_eliminated)
    calculate_discussion_metrics(agent_metrics, events, role_assignments, final_eliminated)
    calculate_voting_metrics(agent_metrics, events, role_assignments, final_eliminated)
    calculate_system_metrics(agent_metrics, events, agent_models)
    
    # Calculate model-level aggregated metrics
    model_aggregated = calculate_model_aggregated_metrics(agent_metrics, agent_models, role_assignments)
    
    return {
        "game_id": game_id,
        "total_rounds": total_rounds,
        "winner": winner,
        "role_assignments": role_assignments,
        "agent_models": agent_models,
        "agent_metrics": agent_metrics,
        "model_aggregated_metrics": model_aggregated
    }


def calculate_core_metrics(
    agent_metrics: Dict[str, Dict],
    events: List[Dict],
    role_assignments: Dict[str, str],
    final_alive: List[str],
    final_eliminated: List[str],
    total_rounds: int,
    winner: Optional[str]
):
    """Calculate core game outcome metrics."""
    # Already set in extract_game_metrics: agent_won_game, agent_survived, agent_elimination_round
    pass


def calculate_role_specific_metrics(
    agent_metrics: Dict[str, Dict],
    events: List[Dict],
    role_assignments: Dict[str, str],
    eliminated_agents: List[str]
):
    """Calculate role-specific effectiveness metrics."""
    
    # Track werewolf kills and who was actually eliminated
    werewolf_kills_by_round = {}  # round -> target_id
    actual_eliminations_by_round = {}  # round -> eliminated_id
    
    # Track doctor protections
    doctor_protections = []  # {doctor_id, target, round, was_killed_this_night}
    
    # Track witch actions
    witch_heals = []  # {witch_id, target, round, was_werewolf}
    witch_poisons = []  # {witch_id, target, round, was_werewolf, target_eliminated}
    
    # Track hunter shots
    hunter_shots = []  # {hunter_id, target, round, target_role, target_eliminated}
    
    # Track seer investigations
    seer_investigations = []  # {seer_id, target, round, is_werewolf}
    
    # Track eliminations by round
    for event in events:
        if event.get("event") == "game_update":
            round_num = event.get("round", 0)
            eliminated = event.get("eliminated", [])
            for agent_id in eliminated:
                if round_num not in actual_eliminations_by_round:
                    actual_eliminations_by_round[round_num] = []
                if agent_id not in actual_eliminations_by_round[round_num]:
                    actual_eliminations_by_round[round_num].append(agent_id)
    
    # Process all actions to track night actions
    for event in events:
        if event.get("event") != "action":
            continue
        
        agent_id = event.get("agent_id")
        action_type = event.get("action_type")
        round_num = event.get("round_number", 0)
        target = event.get("target")
        role = role_assignments.get(agent_id)
        
        # WEREWOLF: Track kill attempts (this is who was targeted at night)
        if action_type == "kill" and role == "werewolf":
            werewolf_kills_by_round[round_num] = target
        
        # SEER: Track investigations
        if action_type == "investigate" and role == "seer":
            investigation_result = event.get("investigation_result", {})
            is_werewolf = investigation_result.get("is_werewolf", False)
            seer_investigations.append({
                "seer_id": agent_id,
                "target": target,
                "round": round_num,
                "is_werewolf": is_werewolf
            })
        
        # DOCTOR: Track protections
        if action_type == "protect" and role == "doctor":
            # Check if this protection saved someone (target was killed by werewolves this night)
            was_killed_this_night = False
            if round_num in werewolf_kills_by_round and werewolf_kills_by_round[round_num] == target:
                was_killed_this_night = True
            
            doctor_protections.append({
                "doctor_id": agent_id,
                "target": target,
                "round": round_num,
                "was_killed_this_night": was_killed_this_night
            })
        
        # WITCH: Track heal and poison
        if action_type == "heal" and role == "witch":
            target_role = role_assignments.get(target, "unknown")
            witch_heals.append({
                "witch_id": agent_id,
                "target": target,
                "round": round_num,
                "was_werewolf": target_role == "werewolf"
            })
        
        if action_type == "poison" and role == "witch":
            target_role = role_assignments.get(target, "unknown")
            target_eliminated = target in eliminated_agents
            witch_poisons.append({
                "witch_id": agent_id,
                "target": target,
                "round": round_num,
                "was_werewolf": target_role == "werewolf",
                "target_eliminated": target_eliminated
            })
        
        # HUNTER: Track shots
        if action_type == "shoot" and role == "hunter":
            target_role = role_assignments.get(target, "unknown")
            target_eliminated = target in eliminated_agents
            hunter_shots.append({
                "hunter_id": agent_id,
                "target": target,
                "round": round_num,
                "target_role": target_role,
                "target_eliminated": target_eliminated,
                "was_werewolf": target_role == "werewolf"
            })
        
        # WEREWOLF: Track kill attempts
        if action_type == "kill" and role == "werewolf":
            werewolf_kills_by_round[round_num] = target
    
    # Calculate SEER metrics
    for agent_id in agent_metrics:
        if role_assignments.get(agent_id) == "seer":
            seer_invs = [inv for inv in seer_investigations if inv["seer_id"] == agent_id]
            werewolf_discoveries = [inv for inv in seer_invs if inv["is_werewolf"]]
            
            agent_metrics[agent_id]["seer_investigation_count"] = len(seer_invs)
            agent_metrics[agent_id]["seer_werewolf_discovery_rate"] = (
                (len(werewolf_discoveries) / len(seer_invs) * 100) if seer_invs else 0
            )
    
    # Calculate DOCTOR metrics
    for agent_id in agent_metrics:
        if role_assignments.get(agent_id) == "doctor":
            doc_prots = [p for p in doctor_protections if p["doctor_id"] == agent_id]
            successful_saves = [p for p in doc_prots if p["was_killed_this_night"]]
            werewolf_prots = [p for p in doc_prots if role_assignments.get(p["target"]) == "werewolf"]
            good_role_prots = [p for p in doc_prots if role_assignments.get(p["target"]) in ["seer", "doctor", "hunter", "witch", "villager"]]
            
            agent_metrics[agent_id]["doctor_protection_count"] = len(doc_prots)
            agent_metrics[agent_id]["doctor_save_success_rate"] = (
                (len(successful_saves) / len(doc_prots) * 100) if doc_prots else 0
            )
            agent_metrics[agent_id]["doctor_werewolf_protection_rate"] = (
                (len(werewolf_prots) / len(doc_prots) * 100) if doc_prots else 0
            )
            agent_metrics[agent_id]["doctor_good_role_protection_rate"] = (
                (len(good_role_prots) / len(doc_prots) * 100) if doc_prots else 0
            )
    
    # Calculate WITCH metrics
    for agent_id in agent_metrics:
        if role_assignments.get(agent_id) == "witch":
            witch_heal_list = [h for h in witch_heals if h["witch_id"] == agent_id]
            witch_poison_list = [p for p in witch_poisons if p["witch_id"] == agent_id]
            
            agent_metrics[agent_id]["witch_action_count"] = len(witch_heal_list) + len(witch_poison_list)
            
            # Poison accuracy (did poison go to werewolf)
            if witch_poison_list:
                poison = witch_poison_list[0]  # Only one poison
                agent_metrics[agent_id]["witch_poison_accuracy"] = 100.0 if poison["was_werewolf"] else 0.0
            else:
                agent_metrics[agent_id]["witch_poison_accuracy"] = None
            
            # Heal value rate (did heal go to good person)
            if witch_heal_list:
                heal = witch_heal_list[0]  # Only one heal
                agent_metrics[agent_id]["witch_heal_value_rate"] = 0.0 if heal["was_werewolf"] else 100.0
            else:
                agent_metrics[agent_id]["witch_heal_value_rate"] = None
    
    # Calculate HUNTER metrics
    for agent_id in agent_metrics:
        if role_assignments.get(agent_id) == "hunter":
            hunter_was_eliminated = agent_id in eliminated_agents
            hunter_shot_list = [s for s in hunter_shots if s["hunter_id"] == agent_id]
            
            agent_metrics[agent_id]["hunter_triggered"] = hunter_was_eliminated
            agent_metrics[agent_id]["hunter_shot_taken"] = len(hunter_shot_list) > 0
            
            if hunter_shot_list:
                shot = hunter_shot_list[0]  # Only one shot
                agent_metrics[agent_id]["hunter_shot_target_role"] = shot["target_role"]
                agent_metrics[agent_id]["hunter_shot_accuracy"] = shot["was_werewolf"]
            else:
                agent_metrics[agent_id]["hunter_shot_target_role"] = None
                agent_metrics[agent_id]["hunter_shot_accuracy"] = None
    
    # Calculate WEREWOLF metrics
    for agent_id in agent_metrics:
        if role_assignments.get(agent_id) == "werewolf":
            # Count kill attempts (all werewolves participate in each kill)
            kill_attempts = len(werewolf_kills_by_round)
            successful_kills = []
            key_role_kills = []
            
            for round_num, target in werewolf_kills_by_round.items():
                # Check if target was actually eliminated by day (meaning they survived the night kill)
                # Werewolf kill success = target eliminated by vote later (survived night, died by day)
                target_eliminated = target in eliminated_agents
                if target_eliminated:
                    # Find when target was eliminated
                    eliminated_round = None
                    for r, eliminated_list in actual_eliminations_by_round.items():
                        if target in eliminated_list:
                            eliminated_round = r
                            break
                    
                    # Success if eliminated in same round (by vote) or later round
                    if eliminated_round is not None and eliminated_round >= round_num:
                        successful_kills.append(target)
                        target_role = role_assignments.get(target)
                        if target_role in ["seer", "doctor"]:
                            key_role_kills.append(target)
            
            agent_metrics[agent_id]["werewolf_kill_attempt_count"] = kill_attempts
            agent_metrics[agent_id]["werewolf_kill_success_rate"] = (
                (len(successful_kills) / kill_attempts * 100) if kill_attempts > 0 else 0
            )
            agent_metrics[agent_id]["werewolf_key_role_elimination_rate"] = (
                (len(key_role_kills) / kill_attempts * 100) if kill_attempts > 0 else 0
            )


def calculate_discussion_metrics(
    agent_metrics: Dict[str, Dict],
    events: List[Dict],
    role_assignments: Dict[str, str],
    eliminated_agents: List[str]
):
    """Calculate discussion & persuasion metrics."""
    
    # Track accusations and defenses by round
    accusations_by_round = defaultdict(list)  # round -> [{agent_id, target, round}]
    defenses_by_round = defaultdict(list)  # round -> [{agent_id, target, round}]
    role_claims = []  # [{agent_id, claimed_role, true_role, round}]
    
    # Track voting results by round
    votes_by_round = {}  # round -> {voter: target}
    eliminated_by_vote_by_round = {}  # round -> eliminated_id
    
    # Process discussion actions
    for event in events:
        if event.get("event") != "action" or event.get("action_type") != "discuss":
            continue
        
        agent_id = event.get("agent_id")
        round_num = event.get("round_number", 0)
        
        # Handle multiple subactions
        discussion_subactions = event.get("discussion_subactions", [])
        discussion_targets = event.get("discussion_targets", [])
        
        # Backward compatibility
        if not discussion_subactions:
            discussion_action_type = event.get("discussion_action_type")
            if discussion_action_type:
                discussion_subactions = [discussion_action_type]
                target = event.get("target")
                discussion_targets = [[target]] if target else [[]]
        
        # Process each subaction
        for i, subaction_type in enumerate(discussion_subactions):
            target_list = discussion_targets[i] if i < len(discussion_targets) else []
            
            if subaction_type == "accuse":
                for target in target_list:
                    if target:
                        accusations_by_round[round_num].append({
                            "agent_id": agent_id,
                            "target": target,
                            "round": round_num
                        })
            
            elif subaction_type == "defend":
                for target in target_list:
                    if target:
                        defenses_by_round[round_num].append({
                            "agent_id": agent_id,
                            "target": target,
                            "round": round_num
                        })
            
            elif subaction_type == "claim_role":
                claimed_role = event.get("claimed_role")
                true_role = role_assignments.get(agent_id)
                role_claims.append({
                    "agent_id": agent_id,
                    "claimed_role": claimed_role,
                    "true_role": true_role,
                    "round": round_num
                })
    
    # Process votes to find who was eliminated by vote each round
    for event in events:
        if event.get("event") == "action" and event.get("action_type") == "vote":
            round_num = event.get("round_number", 0)
            voter = event.get("agent_id")
            target = event.get("target")
            
            if round_num not in votes_by_round:
                votes_by_round[round_num] = {}
            votes_by_round[round_num][voter] = target
    
    # Find who was eliminated by vote each round
    for event in events:
        if event.get("event") == "game_update":
            round_num = event.get("round", 0)
            eliminated = event.get("eliminated", [])
            # Check if this was a voting elimination (happens after day_voting phase)
            phase = event.get("phase", "")
            if phase == "day_voting" or (round_num > 0 and len(eliminated) > len(eliminated_by_vote_by_round.get(round_num - 1, []))):
                if eliminated:
                    eliminated_by_vote_by_round[round_num] = eliminated[-1]
    
    # Calculate per-agent metrics
    for agent_id in agent_metrics:
        # Count discussion subactions
        discussion_count = 0
        accusation_count = 0
        defense_count = 0
        role_claim_count = 0
        
        for event in events:
            if event.get("event") == "action" and event.get("action_type") == "discuss":
                if event.get("agent_id") == agent_id:
                    discussion_subactions = event.get("discussion_subactions", [])
                    if not discussion_subactions:
                        discussion_action_type = event.get("discussion_action_type")
                        if discussion_action_type:
                            discussion_subactions = [discussion_action_type]
                    
                    for subaction in discussion_subactions:
                        discussion_count += 1
                        if subaction == "accuse":
                            accusation_count += 1
                        elif subaction == "defend":
                            defense_count += 1
                        elif subaction == "claim_role":
                            role_claim_count += 1
        
        agent_metrics[agent_id]["discussion_action_count"] = discussion_count
        agent_metrics[agent_id]["accusation_count"] = accusation_count
        agent_metrics[agent_id]["defense_count"] = defense_count
        agent_metrics[agent_id]["role_claim_count"] = role_claim_count
        
        # Accusation effectiveness: fraction of accused targets eliminated by vote this round
        effective_accusations = 0
        total_accusations = 0
        for round_num, accusations in accusations_by_round.items():
            agent_accusations = [a for a in accusations if a["agent_id"] == agent_id]
            for acc in agent_accusations:
                total_accusations += 1
                # Check if target was eliminated by vote this round
                if round_num in eliminated_by_vote_by_round:
                    if eliminated_by_vote_by_round[round_num] == acc["target"]:
                        effective_accusations += 1
        
        agent_metrics[agent_id]["accusation_effectiveness_rate"] = (
            (effective_accusations / total_accusations * 100) if total_accusations > 0 else 0
        )
        
        # Defense failure rate: fraction of defended targets still eliminated by vote this round
        failed_defenses = 0
        total_defenses = 0
        for round_num, defenses in defenses_by_round.items():
            agent_defenses = [d for d in defenses if d["agent_id"] == agent_id]
            for defense in agent_defenses:
                total_defenses += 1
                # Check if target was still eliminated by vote this round
                if round_num in eliminated_by_vote_by_round:
                    if eliminated_by_vote_by_round[round_num] == defense["target"]:
                        failed_defenses += 1
        
        agent_metrics[agent_id]["defense_failure_rate"] = (
            (failed_defenses / total_defenses * 100) if total_defenses > 0 else 0
        )
        
        # Truthful role claim rate
        agent_role_claims = [rc for rc in role_claims if rc["agent_id"] == agent_id]
        truthful_claims = [rc for rc in agent_role_claims if rc["claimed_role"] == rc["true_role"]]
        
        agent_metrics[agent_id]["truthful_role_claim_rate"] = (
            (len(truthful_claims) / len(agent_role_claims) * 100) if agent_role_claims else 0
        )


def calculate_voting_metrics(
    agent_metrics: Dict[str, Dict],
    events: List[Dict],
    role_assignments: Dict[str, str],
    eliminated_agents: List[str]
):
    """Calculate voting behavior metrics."""
    
    # Track votes and who was eliminated by vote each round
    votes_by_round = defaultdict(dict)  # round -> {voter: target}
    eliminated_by_vote_by_round = {}  # round -> eliminated_id
    
    # Process votes
    for event in events:
        if event.get("event") == "action" and event.get("action_type") == "vote":
            round_num = event.get("round_number", 0)
            voter = event.get("agent_id")
            target = event.get("target")
            votes_by_round[round_num][voter] = target
    
    # Find who was eliminated by vote each round
    for event in events:
        if event.get("event") == "game_update":
            round_num = event.get("round", 0)
            eliminated = event.get("eliminated", [])
            phase = event.get("phase", "")
            if phase == "day_voting" or (round_num > 0):
                if eliminated:
                    eliminated_by_vote_by_round[round_num] = eliminated[-1]
    
    # Calculate per-agent metrics
    for agent_id in agent_metrics:
        vote_count = 0
        aligned_votes = 0
        self_vote_attempted = False
        
        for round_num, votes in votes_by_round.items():
            if agent_id in votes:
                vote_count += 1
                target = votes[agent_id]
                
                # Check self-vote
                if target == agent_id:
                    self_vote_attempted = True
                
                # Check alignment (voted for eventual eliminated)
                if round_num in eliminated_by_vote_by_round:
                    if eliminated_by_vote_by_round[round_num] == target:
                        aligned_votes += 1
        
        agent_metrics[agent_id]["vote_count"] = vote_count
        agent_metrics[agent_id]["vote_alignment_rate"] = (
            (aligned_votes / vote_count * 100) if vote_count > 0 else 0
        )
        agent_metrics[agent_id]["self_vote_attempted"] = self_vote_attempted


def calculate_system_metrics(
    agent_metrics: Dict[str, Dict],
    events: List[Dict],
    agent_models: Dict[str, str]
):
    """Calculate system & reliability metrics."""
    
    # Track response times
    response_times_by_agent = defaultdict(list)
    
    for event in events:
        if event.get("event") == "DEBUG_agent_response":
            agent_id = event.get("agent_id")
            response_time = event.get("response_time_ms")
            if response_time is not None:
                response_times_by_agent[agent_id].append(response_time)
    
    # Track invalid actions
    invalid_actions_by_agent = defaultdict(int)
    total_actions_by_agent = defaultdict(int)
    
    for event in events:
        if event.get("event") == "action":
            agent_id = event.get("agent_id")
            if agent_id:
                total_actions_by_agent[agent_id] += 1
        elif event.get("event") == "invalid_action":
            agent_id = event.get("agent_id")
            if agent_id:
                invalid_actions_by_agent[agent_id] += 1
                total_actions_by_agent[agent_id] += 1
    
    # Calculate per-agent metrics
    for agent_id in agent_metrics:
        # Response time metrics
        response_times = response_times_by_agent.get(agent_id, [])
        if response_times:
            sorted_times = sorted(response_times)
            agent_metrics[agent_id]["mean_response_time_ms"] = statistics.mean(response_times)
            p95_index = int(len(sorted_times) * 0.95)
            agent_metrics[agent_id]["p95_response_time_ms"] = sorted_times[p95_index] if p95_index < len(sorted_times) else sorted_times[-1]
        else:
            agent_metrics[agent_id]["mean_response_time_ms"] = None
            agent_metrics[agent_id]["p95_response_time_ms"] = None
        
        # Invalid action rate
        total_actions = total_actions_by_agent.get(agent_id, 0)
        invalid_actions = invalid_actions_by_agent.get(agent_id, 0)
        agent_metrics[agent_id]["invalid_action_rate"] = (
            (invalid_actions / total_actions * 100) if total_actions > 0 else 0
        )


def calculate_model_aggregated_metrics(
    agent_metrics: Dict[str, Dict],
    agent_models: Dict[str, str],
    role_assignments: Dict[str, str]
) -> Dict[str, Dict]:
    """Calculate model-level aggregated metrics."""
    
    # Group agents by model
    agents_by_model = defaultdict(list)
    for agent_id, model in agent_models.items():
        agents_by_model[model].append(agent_id)
    
    model_aggregated = {}
    
    for model, agent_ids in agents_by_model.items():
        model_metrics = {
            "agent_count": len(agent_ids),
            "agent_ids": agent_ids
        }
        
        # Aggregate general metrics (all agents)
        general_metrics = []
        for agent_id in agent_ids:
            if agent_id in agent_metrics:
                general_metrics.append(agent_metrics[agent_id])
        
        if general_metrics:
            # Core metrics
            model_metrics["avg_agent_won_game"] = statistics.mean([m.get("agent_won_game", False) for m in general_metrics]) * 100
            model_metrics["avg_agent_survived"] = statistics.mean([m.get("agent_survived", False) for m in general_metrics]) * 100
            model_metrics["avg_agent_elimination_round"] = statistics.mean([m.get("agent_elimination_round", 0) for m in general_metrics])
            
            # Discussion metrics
            discussion_counts = [m.get("discussion_action_count", 0) for m in general_metrics]
            accusation_counts = [m.get("accusation_count", 0) for m in general_metrics]
            defense_counts = [m.get("defense_count", 0) for m in general_metrics]
            role_claim_counts = [m.get("role_claim_count", 0) for m in general_metrics]
            
            model_metrics["avg_discussion_action_count"] = statistics.mean(discussion_counts) if discussion_counts else 0
            model_metrics["avg_accusation_count"] = statistics.mean(accusation_counts) if accusation_counts else 0
            model_metrics["avg_defense_count"] = statistics.mean(defense_counts) if defense_counts else 0
            model_metrics["avg_role_claim_count"] = statistics.mean(role_claim_counts) if role_claim_counts else 0
            
            # Effectiveness rates (only for agents who performed the action)
            accusation_rates = [m.get("accusation_effectiveness_rate", 0) for m in general_metrics if m.get("accusation_count", 0) > 0]
            defense_rates = [m.get("defense_failure_rate", 0) for m in general_metrics if m.get("defense_count", 0) > 0]
            role_claim_rates = [m.get("truthful_role_claim_rate", 0) for m in general_metrics if m.get("role_claim_count", 0) > 0]
            
            if accusation_rates:
                model_metrics["avg_accusation_effectiveness_rate"] = statistics.mean(accusation_rates)
            if defense_rates:
                model_metrics["avg_defense_failure_rate"] = statistics.mean(defense_rates)
            if role_claim_rates:
                model_metrics["avg_truthful_role_claim_rate"] = statistics.mean(role_claim_rates)
            
            # Voting metrics
            vote_counts = [m.get("vote_count", 0) for m in general_metrics]
            vote_alignment_rates = [m.get("vote_alignment_rate", 0) for m in general_metrics if m.get("vote_count", 0) > 0]
            
            model_metrics["avg_vote_count"] = statistics.mean(vote_counts) if vote_counts else 0
            if vote_alignment_rates:
                model_metrics["avg_vote_alignment_rate"] = statistics.mean(vote_alignment_rates)
            
            # System metrics
            response_times = [m.get("mean_response_time_ms") for m in general_metrics if m.get("mean_response_time_ms") is not None]
            p95_times = [m.get("p95_response_time_ms") for m in general_metrics if m.get("p95_response_time_ms") is not None]
            invalid_rates = [m.get("invalid_action_rate", 0) for m in general_metrics]
            
            if response_times:
                model_metrics["avg_mean_response_time_ms"] = statistics.mean(response_times)
            if p95_times:
                model_metrics["avg_p95_response_time_ms"] = statistics.mean(p95_times)
            if invalid_rates:
                model_metrics["avg_invalid_action_rate"] = statistics.mean(invalid_rates)
        
        # Aggregate role-specific metrics (separated by role)
        role_specific = {}
        
        # SEER metrics
        seer_agents = [aid for aid in agent_ids if role_assignments.get(aid) == "seer"]
        if seer_agents:
            seer_metrics_list = [agent_metrics[aid] for aid in seer_agents if aid in agent_metrics]
            if seer_metrics_list:
                investigation_counts = [m.get("seer_investigation_count", 0) for m in seer_metrics_list]
                discovery_rates = [m.get("seer_werewolf_discovery_rate", 0) for m in seer_metrics_list if m.get("seer_investigation_count", 0) > 0]
                
                role_specific["seer"] = {
                    "avg_seer_investigation_count": statistics.mean(investigation_counts) if investigation_counts else 0,
                    "avg_seer_werewolf_discovery_rate": statistics.mean(discovery_rates) if discovery_rates else 0,
                    "seer_count": len(seer_agents)
                }
        
        # DOCTOR metrics
        doctor_agents = [aid for aid in agent_ids if role_assignments.get(aid) == "doctor"]
        if doctor_agents:
            doctor_metrics_list = [agent_metrics[aid] for aid in doctor_agents if aid in agent_metrics]
            if doctor_metrics_list:
                protection_counts = [m.get("doctor_protection_count", 0) for m in doctor_metrics_list]
                save_rates = [m.get("doctor_save_success_rate", 0) for m in doctor_metrics_list if m.get("doctor_protection_count", 0) > 0]
                werewolf_prot_rates = [m.get("doctor_werewolf_protection_rate", 0) for m in doctor_metrics_list if m.get("doctor_protection_count", 0) > 0]
                good_role_prot_rates = [m.get("doctor_good_role_protection_rate", 0) for m in doctor_metrics_list if m.get("doctor_protection_count", 0) > 0]
                
                role_specific["doctor"] = {
                    "avg_doctor_protection_count": statistics.mean(protection_counts) if protection_counts else 0,
                    "avg_doctor_save_success_rate": statistics.mean(save_rates) if save_rates else 0,
                    "avg_doctor_werewolf_protection_rate": statistics.mean(werewolf_prot_rates) if werewolf_prot_rates else 0,
                    "avg_doctor_good_role_protection_rate": statistics.mean(good_role_prot_rates) if good_role_prot_rates else 0,
                    "doctor_count": len(doctor_agents)
                }
        
        # WITCH metrics
        witch_agents = [aid for aid in agent_ids if role_assignments.get(aid) == "witch"]
        if witch_agents:
            witch_metrics_list = [agent_metrics[aid] for aid in witch_agents if aid in agent_metrics]
            if witch_metrics_list:
                action_counts = [m.get("witch_action_count", 0) for m in witch_metrics_list]
                poison_accuracies = [m.get("witch_poison_accuracy") for m in witch_metrics_list if m.get("witch_poison_accuracy") is not None]
                heal_values = [m.get("witch_heal_value_rate") for m in witch_metrics_list if m.get("witch_heal_value_rate") is not None]
                
                role_specific["witch"] = {
                    "avg_witch_action_count": statistics.mean(action_counts) if action_counts else 0,
                    "avg_witch_poison_accuracy": statistics.mean(poison_accuracies) if poison_accuracies else None,
                    "avg_witch_heal_value_rate": statistics.mean(heal_values) if heal_values else None,
                    "witch_count": len(witch_agents)
                }
        
        # HUNTER metrics
        hunter_agents = [aid for aid in agent_ids if role_assignments.get(aid) == "hunter"]
        if hunter_agents:
            hunter_metrics_list = [agent_metrics[aid] for aid in hunter_agents if aid in agent_metrics]
            if hunter_metrics_list:
                triggered = [m.get("hunter_triggered", False) for m in hunter_metrics_list]
                shots_taken = [m.get("hunter_shot_taken", False) for m in hunter_metrics_list]
                accuracies = [m.get("hunter_shot_accuracy") for m in hunter_metrics_list if m.get("hunter_shot_accuracy") is not None]
                
                role_specific["hunter"] = {
                    "avg_hunter_triggered": statistics.mean([1 if t else 0 for t in triggered]) * 100 if triggered else 0,
                    "avg_hunter_shot_taken": statistics.mean([1 if s else 0 for s in shots_taken]) * 100 if shots_taken else 0,
                    "avg_hunter_shot_accuracy": statistics.mean([1 if a else 0 for a in accuracies]) * 100 if accuracies else None,
                    "hunter_count": len(hunter_agents)
                }
        
        # WEREWOLF metrics
        werewolf_agents = [aid for aid in agent_ids if role_assignments.get(aid) == "werewolf"]
        if werewolf_agents:
            werewolf_metrics_list = [agent_metrics[aid] for aid in werewolf_agents if aid in agent_metrics]
            if werewolf_metrics_list:
                kill_attempts = [m.get("werewolf_kill_attempt_count", 0) for m in werewolf_metrics_list]
                success_rates = [m.get("werewolf_kill_success_rate", 0) for m in werewolf_metrics_list if m.get("werewolf_kill_attempt_count", 0) > 0]
                key_role_rates = [m.get("werewolf_key_role_elimination_rate", 0) for m in werewolf_metrics_list if m.get("werewolf_kill_attempt_count", 0) > 0]
                
                role_specific["werewolf"] = {
                    "avg_werewolf_kill_attempt_count": statistics.mean(kill_attempts) if kill_attempts else 0,
                    "avg_werewolf_kill_success_rate": statistics.mean(success_rates) if success_rates else 0,
                    "avg_werewolf_key_role_elimination_rate": statistics.mean(key_role_rates) if key_role_rates else 0,
                    "werewolf_count": len(werewolf_agents)
                }
        
        if role_specific:
            model_metrics["role_specific"] = role_specific
        
        model_aggregated[model] = model_metrics
    
    return model_aggregated


def find_game_log(game_name_or_path: str) -> Path:
    """Find the game log file from a game name or path.
    
    Args:
        game_name_or_path: Either a game name (e.g., 'all_flash-lite') or a full path
        
    Returns:
        Path to the game log file
    """
    game_input = Path(game_name_or_path)
    
    # If it's already a valid file path, use it
    if game_input.exists() and game_input.is_file():
        return game_input
    
    # If it contains path separators but doesn't exist, try to resolve it
    if '/' in game_name_or_path or '\\' in game_name_or_path:
        if not game_input.exists():
            raise FileNotFoundError(f"Game log file not found: {game_input}")
        return game_input
    
    # Otherwise, treat it as a game name and look in standard locations
    # Try baseline directory first
    baseline_log = ROOT_DIR / "game_logs" / "baseline" / f"game_{game_name_or_path}.jsonl"
    if baseline_log.exists():
        return baseline_log
    
    # Try root game_logs directory
    root_log = ROOT_DIR / "game_logs" / f"game_{game_name_or_path}.jsonl"
    if root_log.exists():
        return root_log
    
    # If game name already includes "game_" prefix, try without adding it
    if game_name_or_path.startswith("game_"):
        baseline_log = ROOT_DIR / "game_logs" / "baseline" / f"{game_name_or_path}.jsonl"
        if baseline_log.exists():
            return baseline_log
        root_log = ROOT_DIR / "game_logs" / f"{game_name_or_path}.jsonl"
        if root_log.exists():
            return root_log
    
    raise FileNotFoundError(
        f"Game log not found for '{game_name_or_path}'. "
        f"Tried: game_logs/baseline/game_{game_name_or_path}.jsonl and game_logs/game_{game_name_or_path}.jsonl"
    )


def main():
    """Main function to extract metrics from a game log."""
    if len(sys.argv) != 2:
        print("Usage: python extract_game_metrics.py <game_name_or_path>")
        print("\nExamples:")
        print("  python extract_game_metrics.py all_flash-lite")
        print("  python extract_game_metrics.py game_logs/baseline/game_all_flash-lite.jsonl")
        sys.exit(1)
    
    game_input = sys.argv[1]
    
    try:
        game_log_path = find_game_log(game_input)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    print(f"Processing game log: {game_log_path}")
    
    metrics = extract_game_metrics(str(game_log_path))
    
    if "error" in metrics:
        print(f"Error: {metrics['error']}")
        sys.exit(1)
    
    # Extract game name from filename
    game_name = game_log_path.stem.replace("game_", "")
    
    # Determine output directory (prefer baseline if log is in baseline)
    if "baseline" in str(game_log_path):
        output_path = ROOT_DIR / "metrics" / "baseline"
    else:
        output_path = ROOT_DIR / "metrics"
    
    output_path.mkdir(parents=True, exist_ok=True)
    metrics_file = output_path / f"{game_name}_metrics.json"
    
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Metrics extracted and saved to: {metrics_file}")
    print(f"\nGame ID: {metrics.get('game_id', 'N/A')}")
    print(f"Total Rounds: {metrics.get('total_rounds', 'N/A')}")
    print(f"Winner: {metrics.get('winner', 'N/A')}")
    print(f"\nAgent Metrics: {len(metrics.get('agent_metrics', {}))} agents")
    print(f"Model Aggregated Metrics: {len(metrics.get('model_aggregated_metrics', {}))} models")


if __name__ == "__main__":
    main()
