#!/bin/bash
# White Agent entry point for AgentBeats controller
echo "=== white_run.sh started ===" >&2
echo "Environment variables:" >&2
echo "  HOST=$HOST" >&2
echo "  PORT=$PORT" >&2
echo "  AGENT_PORT=$AGENT_PORT" >&2
echo "  AGENT_URL=$AGENT_URL" >&2
echo "  OPENAI_API_KEY is set: $(if [ -n "$OPENAI_API_KEY" ]; then echo yes; else echo no; fi)" >&2
echo "Working directory: $(pwd)" >&2
echo "Starting white agent via white_main.py..." >&2
python white_main.py
echo "=== white_run.sh finished (exit code: $?) ===" >&2

