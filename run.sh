#!/bin/bash
# AgentBeats controller will set HOST and AGENT_PORT environment variables
echo "=== run.sh started ===" >&2
echo "Environment variables:" >&2
echo "  HOST=$HOST" >&2
echo "  PORT=$PORT" >&2
echo "  AGENT_PORT=$AGENT_PORT" >&2
echo "  AGENT_URL=$AGENT_URL" >&2
echo "  BASE_URL=$BASE_URL" >&2
echo "Working directory: $(pwd)" >&2
echo "Files in current directory:" >&2
ls -la >&2
echo "Starting agent via main.py..." >&2
python main.py
echo "=== run.sh finished (exit code: $?) ===" >&2
