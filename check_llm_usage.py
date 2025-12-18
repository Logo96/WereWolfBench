#!/usr/bin/env python3
"""
Check if LLMs are actually being called in game logs.
Shows LLM vs fallback usage statistics.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

def analyze_log(log_file: Path):
    """Analyze a game log to see LLM vs fallback usage."""
    print(f"\n{'='*70}")
    print(f"Analyzing: {log_file.name}")
    print(f"{'='*70}")
    
    llm_calls = 0
    fallback_calls = 0
    llm_responses = []
    fallback_responses = []
    
    with open(log_file) as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                
                if event.get("event") == "DEBUG_agent_response":
                    raw_response = event.get("raw_response", "")
                    agent_id = event.get("agent_id", "unknown")
                    phase = event.get("phase", "unknown")
                    response_time = event.get("response_time_ms", 0)
                    
                    # Check if it's fallback
                    if '"source": "fallback"' in raw_response:
                        fallback_calls += 1
                        fallback_responses.append({
                            "agent": agent_id,
                            "phase": phase,
                            "time": response_time,
                            "response": raw_response[:200]
                        })
                    elif '"source": "llm"' in raw_response:
                        llm_calls += 1
                        llm_responses.append({
                            "agent": agent_id,
                            "phase": phase,
                            "time": response_time,
                            "response": raw_response[:500]
                        })
                
            except json.JSONDecodeError:
                continue
    
    print(f"\n📊 LLM Usage Statistics:")
    print(f"   ✅ Real LLM calls: {llm_calls}")
    print(f"   ⚠️  Fallback calls: {fallback_calls}")
    print(f"   Total: {llm_calls + fallback_calls}")
    
    if llm_calls + fallback_calls == 0:
        print("\n   ⚠️  No agent responses found in log!")
        return
    
    percentage_llm = (llm_calls / (llm_calls + fallback_calls) * 100) if (llm_calls + fallback_calls) > 0 else 0
    print(f"   LLM usage: {percentage_llm:.1f}%")
    
    if llm_calls > 0:
        print(f"\n✅ REAL LLM RESPONSES ({llm_calls}):")
        for i, resp in enumerate(llm_responses[:5], 1):  # Show first 5
            print(f"\n   {i}. Agent: {resp['agent']}, Phase: {resp['phase']}, Time: {resp['time']:.1f}ms")
            print(f"      Response: {resp['response'][:300]}...")
        if len(llm_responses) > 5:
            print(f"   ... and {len(llm_responses) - 5} more")
    else:
        print("\n❌ NO REAL LLM RESPONSES FOUND!")
        print("   All responses are using fallback logic.")
        print("\n   Possible causes:")
        print("   1. LiteLLM not installed in the Python environment used by White Agents")
        print("   2. OPENAI_API_KEY not set when White Agents started")
        print("   3. Model name invalid (check if 'gpt-5.2' and 'gpt-5-mini' are valid)")
        print("   4. White Agents were started before installing LiteLLM/setting API key")
    
    if fallback_calls > 0:
        print(f"\n⚠️  FALLBACK RESPONSES ({fallback_calls}):")
        for i, resp in enumerate(fallback_responses[:3], 1):  # Show first 3
            print(f"\n   {i}. Agent: {resp['agent']}, Phase: {resp['phase']}, Time: {resp['time']:.1f}ms")
            print(f"      Response: {resp['response'][:200]}...")
        if len(fallback_responses) > 3:
            print(f"   ... and {len(fallback_responses) - 3} more")
    
    # Response time analysis
    if llm_calls > 0:
        llm_times = [r['time'] for r in llm_responses]
        avg_llm_time = sum(llm_times) / len(llm_times)
        print(f"\n⏱️  Response Times:")
        print(f"   LLM average: {avg_llm_time:.1f}ms")
        print(f"   LLM range: {min(llm_times):.1f}ms - {max(llm_times):.1f}ms")
    
    if fallback_calls > 0:
        fallback_times = [r['time'] for r in fallback_responses]
        avg_fallback_time = sum(fallback_times) / len(fallback_times)
        if llm_calls == 0:
            print(f"\n⏱️  Response Times:")
        print(f"   Fallback average: {avg_fallback_time:.1f}ms")
        print(f"   Fallback range: {min(fallback_times):.1f}ms - {max(fallback_times):.1f}ms")
        
        # Warning if fallback times are suspiciously fast
        if avg_fallback_time < 50:
            print(f"\n   ⚠️  Fallback responses are very fast (< 50ms) - confirms they're not using LLM")

def main():
    if len(sys.argv) > 1:
        log_file = Path(sys.argv[1])
        if not log_file.exists():
            print(f"Error: Log file not found: {log_file}")
            sys.exit(1)
        analyze_log(log_file)
    else:
        # Find most recent log
        log_dir = Path("game_logs/baseline")
        if not log_dir.exists():
            log_dir = Path("game_logs")
        
        log_files = list(log_dir.glob("game_*.jsonl"))
        if not log_files:
            print("No game logs found!")
            sys.exit(1)
        
        # Get most recent
        latest_log = max(log_files, key=lambda p: p.stat().st_mtime)
        print(f"Analyzing most recent log: {latest_log.name}")
        analyze_log(latest_log)

if __name__ == "__main__":
    main()

