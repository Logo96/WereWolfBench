"""Werewolf White Agent - Entry point for AgentBeats controller."""

import os
import sys
import traceback


def main():
    """Main entry point - deferred import to avoid module-level hanging."""
    print("=== white_main.py main() called ===", file=sys.stderr, flush=True)

    # Add app directory to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    print(f"sys.path[0]: {sys.path[0]}", file=sys.stderr, flush=True)

    # Import inside function to defer heavy module loading
    print("About to import from white_agent.main...", file=sys.stderr, flush=True)
    from white_agent.main import start_white_agent
    print("Import completed successfully!", file=sys.stderr, flush=True)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_PORT") or os.getenv("PORT") or "9002")
    print(f"Starting agent on {host}:{port}", file=sys.stderr, flush=True)

    start_white_agent(agent_name="agent_card", host=host, port=port)
    print("Agent finished normally", file=sys.stderr, flush=True)


if __name__ == "__main__":
    print("=== white_main.py STARTED ===", file=sys.stderr, flush=True)
    print(f"Python: {sys.executable}", file=sys.stderr, flush=True)
    try:
        main()
    except Exception as e:
        print(f"=== white_main.py crashed: {e} ===", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

