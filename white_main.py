"""Werewolf White Agent - Entry point for AgentBeats controller."""

import os
import sys
import traceback

# Add directories to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the white agent
from white_agent.main import start_white_agent

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_PORT") or os.getenv("PORT") or "9002")
    print(f"=== white_main.py starting agent on {host}:{port} ===", file=sys.stderr)
    try:
        start_white_agent(host=host, port=port)
        print("=== white_main.py agent finished normally ===", file=sys.stderr)
    except Exception as e:
        print(f"=== white_main.py agent crashed with error: {e} ===", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

