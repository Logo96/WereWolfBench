#!/usr/bin/env python3
"""
Parse and display evaluation metrics from WereWolf game log files.
This script reads a JSONL game log file and extracts the evaluation_metrics event,
then displays the metrics in a clean, readable format.
"""

import json
import sys
import argparse
from pathlib import Path


def parse_metrics_from_file(file_path):
    """Parse evaluation metrics from a JSONL game log file."""
    try:
        with open(file_path, 'r') as f:
            for line in f:
                event = json.loads(line.strip())
                if event.get('event') == 'evaluation_metrics':
                    return event.get('metrics', {})
        return None
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file '{file_path}': {e}")
        return None
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        return None


def format_percentage(value):
    """Format a percentage value with 1 decimal place."""
    return f"{value:.1f}%"


def display_metrics(metrics):
    """Display the evaluation metrics in a clean, readable format."""
    if not metrics:
        print("No evaluation metrics found in the file.")
        return

    print("AUTOMATIC METRICS CALCULATION SUCCESS!")
    print("=" * 50)
    
    # Basic game information
    print(f"Game ID: {metrics.get('game_id', 'N/A')}")
    print(f"Winner: {metrics.get('winner', 'N/A')}")
    print(f"Total Rounds: {metrics.get('total_rounds', 'N/A')}")
    print(f"Final Alive: {', '.join(metrics.get('final_alive', []))}")
    print(f"Final Eliminated: {', '.join(metrics.get('final_eliminated', []))}")
    print()
    
    # Action statistics
    action_counts = metrics.get('action_counts', {})
    total_actions = metrics.get('total_actions', 0)
    valid_actions = metrics.get('valid_actions', 0)
    invalid_actions = metrics.get('invalid_actions', 0)
    
    print("ACTION STATISTICS:")
    print(f"  Total Actions: {total_actions}")
    print(f"  Valid Actions: {valid_actions}")
    print(f"  Invalid Actions: {invalid_actions}")
    if total_actions > 0:
        compliance_rate = (valid_actions / total_actions) * 100
        print(f"  Overall Compliance: {format_percentage(compliance_rate)}")
    print()
    
    # Role assignments
    print("ROLE ASSIGNMENTS:")
    role_assignments = metrics.get('role_assignments', {})
    for agent, role in role_assignments.items():
        print(f"  {agent}: {role}")
    print()
    
    # Key metrics
    print("KEY METRICS:")
    print(f"  Discussion Actions: {metrics.get('discussion_actions_count', 0)}")
    print(f"  Accusations: {metrics.get('accusations_count', 0)}")
    print(f"  Correct Accusations: {format_percentage(metrics.get('correct_accusations_percentage', 0))}")
    print(f"  Identity Reveals: {metrics.get('identity_reveals_count', 0)}")
    print(f"  Investigation Reveals: {metrics.get('investigation_reveals_count', 0)}")
    print(f"  Defenses: {metrics.get('defenses_count', 0)}")
    print()
    
    # Special role actions
    print("SPECIAL ROLE ACTIONS:")
    print(f"  Seer Investigations: {len(metrics.get('seer_investigations', []))}")
    print(f"  Doctor Success Rate: {format_percentage(metrics.get('doctor_success_rate', 0))}")
    print(f"  Witch Actions: {metrics.get('witch_heal_count', 0)} heals, {metrics.get('witch_poison_count', 0)} poisons")
    print(f"  Werewolf Success Rate: {format_percentage(metrics.get('werewolf_success_rate', 0))}")
    print()
    
    # Agent compliance rates
    print("AGENT COMPLIANCE RATES:")
    by_agent = metrics.get('by_agent', {})
    for agent, stats in by_agent.items():
        compliance_rate = stats.get('compliance_rate', 0)
        total = stats.get('total', 0)
        valid = stats.get('valid', 0)
        invalid = stats.get('invalid', 0)
        print(f"  {agent}: {format_percentage(compliance_rate)} ({valid}/{total} valid, {invalid} invalid)")
    print()
    
    # Action type compliance
    print("ACTION TYPE COMPLIANCE:")
    by_action_type = metrics.get('by_action_type', {})
    for action_type, stats in by_action_type.items():
        compliance_rate = stats.get('compliance_rate', 0)
        total = stats.get('total', 0)
        valid = stats.get('valid', 0)
        invalid = stats.get('invalid', 0)
        print(f"  {action_type}: {format_percentage(compliance_rate)} ({valid}/{total} valid, {invalid} invalid)")
    print()
    
    # Phase compliance
    print("PHASE COMPLIANCE:")
    by_phase = metrics.get('by_phase', {})
    for phase, stats in by_phase.items():
        compliance_rate = stats.get('compliance_rate', 0)
        total = stats.get('total', 0)
        valid = stats.get('valid', 0)
        invalid = stats.get('invalid', 0)
        print(f"  {phase}: {format_percentage(compliance_rate)} ({valid}/{total} valid, {invalid} invalid)")
    print()
    
    # Error types
    error_types = metrics.get('error_types', {})
    if error_types:
        print("ERROR TYPES:")
        for error_type, count in error_types.items():
            print(f"  {error_type}: {count}")
        print()


def main():
    """Main function to parse command line arguments and display metrics."""
    parser = argparse.ArgumentParser(description='Parse evaluation metrics from WereWolf game log files')
    parser.add_argument('file_path', help='Path to the JSONL game log file')
    parser.add_argument('--output', '-o', help='Output file to save formatted metrics (optional)')
    
    args = parser.parse_args()
    
    # Parse metrics from file
    metrics = parse_metrics_from_file(args.file_path)
    
    if metrics is None:
        sys.exit(1)
    
    # Display metrics
    if args.output:
        # Save to file
        with open(args.output, 'w') as f:
            import io
            from contextlib import redirect_stdout
            
            output_buffer = io.StringIO()
            with redirect_stdout(output_buffer):
                display_metrics(metrics)
            
            f.write(output_buffer.getvalue())
        print(f"Metrics saved to {args.output}")
    else:
        # Display to console
        display_metrics(metrics)


if __name__ == "__main__":
    main()



