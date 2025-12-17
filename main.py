"""Werewolf Benchmark Green Agent - Entry point for AgentBeats controller."""

import os
import sys
import traceback

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the agent from app module
from app.main import start_green_agent

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_PORT") or os.getenv("PORT") or "9001")
    print(f"=== main.py starting agent on {host}:{port} ===", file=sys.stderr)
    try:
        start_green_agent(agent_name="agent_card", host=host, port=port)
        print("=== main.py agent finished normally ===", file=sys.stderr)
    except Exception as e:
        print(f"=== main.py agent crashed with error: {e} ===", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
