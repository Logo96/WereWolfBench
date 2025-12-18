#!/usr/bin/env python3
"""
Diagnostic script to identify why LLM fallback responses are being used.
"""

import os
import sys
import json
from pathlib import Path

def check_litellm():
    """Check if LiteLLM is available."""
    print(f"  Checking Python: {sys.executable}")
    print(f"  Python version: {sys.version.split()[0]}")
    
    try:
        import litellm
        print("✓ LiteLLM is installed")
        try:
            version = litellm.__version__
            print(f"  Version: {version}")
            print(f"  Path: {litellm.__file__}")
        except:
            print("  Version: unknown")
        return True
    except ImportError as e:
        print("✗ LiteLLM is NOT installed in this Python environment")
        print(f"  Error: {e}")
        print(f"  Python path: {sys.executable}")
        print("\n  Possible issues:")
        print("  1. LiteLLM not installed: pip install litellm")
        print("  2. Wrong Python environment: Make sure you're using the correct Python")
        print("     (e.g., activate conda env: conda activate werewolf-benchmark)")
        print("  3. White Agents might be using a different Python")
        return False

def check_api_key():
    """Check if OpenAI API key is set."""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print(f"✓ OPENAI_API_KEY is set (length: {len(api_key)})")
        return True
    else:
        print("✗ OPENAI_API_KEY is NOT set")
        print("  Set it with: export OPENAI_API_KEY='your-key'")
        return False

def check_model_name():
    """Check what model is being used."""
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    print(f"Model configured: {model}")
    
    # Check if it's a valid model name
    valid_models = ["gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-3.5-turbo", "gpt-5.1", "gpt-5.2", "gpt-5-mini"]
    if model not in valid_models:
        print(f"⚠ Warning: '{model}' might not be a valid model name")
        print(f"  Valid models include: {', '.join(valid_models)}")
    return model

def analyze_recent_log():
    """Analyze the most recent game log to see if fallback was used."""
    log_dir = Path("game_logs/baseline")
    if not log_dir.exists():
        log_dir = Path("game_logs")
    
    log_files = list(log_dir.glob("game_*.jsonl"))
    if not log_files:
        print("\n✗ No game logs found")
        return
    
    # Get most recent log
    latest_log = max(log_files, key=lambda p: p.stat().st_mtime)
    print(f"\nAnalyzing most recent log: {latest_log.name}")
    
    fallback_count = 0
    llm_count = 0
    error_count = 0
    
    with open(latest_log) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                
                if event.get("event") == "DEBUG_agent_response":
                    raw_response = event.get("raw_response", "")
                    response_time = event.get("response_time_ms", 0)
                    
                    # Check if it looks like fallback
                    if "Targeting based on threat assessment" in raw_response:
                        fallback_count += 1
                    elif "Voting for agent_0 based on suspicion" in raw_response:
                        fallback_count += 1
                    elif "Investigating suspicious player" in raw_response:
                        fallback_count += 1
                    elif "Protecting valuable player" in raw_response:
                        fallback_count += 1
                    else:
                        llm_count += 1
                    
                    # Check response time (fallback is usually < 1ms)
                    if response_time < 1:
                        print(f"  ⚠ Very fast response ({response_time:.2f}ms) - might be fallback")
                
                elif event.get("event") == "DEBUG_agent_error":
                    error_count += 1
                    error_msg = event.get("error_message", "")
                    print(f"  ✗ Error: {error_msg[:100]}")
                    
            except json.JSONDecodeError:
                continue
    
    print(f"\nResponse Analysis:")
    print(f"  Fallback-like responses: {fallback_count}")
    print(f"  LLM-like responses: {llm_count}")
    print(f"  Errors: {error_count}")
    
    if fallback_count > llm_count:
        print("\n⚠ WARNING: More fallback-like responses than LLM responses!")
        print("  This suggests the LLM is not being called successfully.")

def main():
    print("=" * 60)
    print("LLM Availability Diagnostic")
    print("=" * 60)
    
    litellm_ok = check_litellm()
    api_key_ok = check_api_key()
    model = check_model_name()
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    if not litellm_ok:
        print("\n❌ ISSUE: LiteLLM is not installed")
        print("   Fix: pip install litellm")
        return
    
    if not api_key_ok:
        print("\n❌ ISSUE: OPENAI_API_KEY is not set")
        print("   Fix: export OPENAI_API_KEY='your-key'")
        return
    
    if model == "gpt-5.1":
        print("\n⚠ WARNING: Model 'gpt-5.1' might not be valid")
        print("   Check LiteLLM documentation for valid model names")
    
    analyze_recent_log()
    
    print("\n" + "=" * 60)
    print("Next Steps")
    print("=" * 60)
    
    # Check if conda environment might be the issue
    python_path = sys.executable
    if "anaconda" not in python_path and "conda" not in python_path:
        print("⚠️  PYTHON ENVIRONMENT MISMATCH DETECTED!")
        print(f"   Current Python: {python_path}")
        print("   LiteLLM is installed in conda env 'werewolf-benchmark'")
        print("   But you're using system Python")
        print("\n   SOLUTION:")
        print("   1. Activate conda environment:")
        print("      conda activate werewolf-benchmark")
        print("   2. Then run the script again:")
        print("      python diagnose_llm_issue.py")
        print("   3. Or use conda Python directly:")
        print("      /Users/yifansong/anaconda3/envs/werewolf-benchmark/bin/python diagnose_llm_issue.py")
        print("\n   When running games, make sure to:")
        print("   - Activate conda env first: conda activate werewolf-benchmark")
        print("   - Then run: python run_full_game.py")
    else:
        print("1. Ensure LiteLLM is installed: pip install litellm")
        print("2. Set OPENAI_API_KEY: export OPENAI_API_KEY='your-key'")
        print("3. Verify model name is valid for your LiteLLM provider")
        print("4. Check White Agent logs for LLM errors")

if __name__ == "__main__":
    main()

