# WereWolfBench - AI Agent Werewolf Game Benchmark

A benchmark for evaluating AI agents playing the social deduction game Werewolf, built on the [A2A (Agent-to-Agent) protocol](https://github.com/google/A2A) and deployed on GCP Cloud Run via [AgentBeats](https://agentbeats.ai/).

## Architecture

The system consists of two agent types:

- **Green Agent**: Game orchestrator that manages game state, coordinates phases, and communicates with white agents
- **White Agent**: LLM-powered player that makes decisions (discuss, vote, use abilities) based on game context


## White Agent Implementation

The white agent uses direct Gemini API calls (via `httpx`) to generate strategic responses. Key features:

- **Direct API Integration**: Uses `httpx` for fast startup (no litellm dependency)
- **Tool Calling**: Supports `get_game_memory` tool for accessing game history
- **Role-Aware Responses**: Generates appropriate actions based on assigned role (Werewolf, Villager, Seer, Doctor, etc.)
- **Retry Logic**: Handles rate limits with exponential backoff

### Key Files

| File | Description |
|------|-------------|
| `white_agent/llm_handler.py` | Core LLM handler with Gemini API integration and tool calling |
| `white_agent/main.py` | A2A server setup and request handling |
| `white_agent/prompt_parser.py` | Parses prompts from green agent |
| `white_agent/response_formatter.py` | Formats LLM responses into game actions |
| `white_main.py` | Entry point for AgentBeats controller |
| `Dockerfile.white` | Docker configuration for white agent |

## Running the White Agent

### Prerequisites

1. Python 3.13+
2. Docker (for containerized deployment)
3. GCP account with Cloud Run enabled (for cloud deployment)
4. Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

### Local Development

```bash
# Clone the repository
git clone https://github.com/Logo96/WereWolfBench.git
cd WereWolfBench

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GEMINI_API_KEY="your-gemini-api-key"
export LLM_MODEL="gemini-2.5-flash"  # or gemini-2.0-flash, gemini-1.5-pro

# Run white agent locally
python white_main.py
```

The agent will start on `http://localhost:9002` by default.

### Docker Build & Run

```bash
# Build the Docker image
docker build -f Dockerfile.white -t werewolf-white:latest .

# Run locally with Docker
docker run -p 8080:8080 \
  -e GEMINI_API_KEY="your-gemini-api-key" \
  -e LLM_MODEL="gemini-2.5-flash" \
  werewolf-white:latest
```

### Deploy to GCP Cloud Run

```bash
# Authenticate with GCP
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Build and push to Google Container Registry
docker build -f Dockerfile.white -t gcr.io/YOUR_PROJECT_ID/werewolf-white:latest .
docker push gcr.io/YOUR_PROJECT_ID/werewolf-white:latest

# Deploy to Cloud Run
gcloud run deploy werewolf-white \
  --image gcr.io/YOUR_PROJECT_ID/werewolf-white:latest \
  --platform managed \
  --region us-central1 \
  --memory 2Gi \
  --cpu 4 \
  --timeout 300 \
  --set-env-vars "GEMINI_API_KEY=your-api-key,LLM_MODEL=gemini-2.5-flash" \
  --allow-unauthenticated
```

## Running a Game Locally

To run a Werewolf game locally with the green agent orchestrating white agents:

```bash
# Terminal 1: Start the green agent (orchestrator)
export GEMINI_API_KEY="your-gemini-api-key"
python -m app.main

# Terminal 2-5: Start 4 white agents on different ports
export GEMINI_API_KEY="your-gemini-api-key"
PORT=9001 python white_main.py  # Agent 1
PORT=9002 python white_main.py  # Agent 2
PORT=9003 python white_main.py  # Agent 3
PORT=9004 python white_main.py  # Agent 4
```

Then start a game by sending a request to the green agent:

```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"text": "{\"task\": \"start_game\", \"params\": {\"agent_urls\": [\"http://localhost:9001\", \"http://localhost:9002\", \"http://localhost:9003\", \"http://localhost:9004\"]}}"}]
      }
    },
    "id": "1"
  }'
```

## Reproducing Evaluation Results

### Register on AgentBeats

1. Go to [AgentBeats](https://agentbeats.ai/)
2. Create an account and register your deployed white agent(s)
3. Note your agent URLs (e.g., `https://werewolf-white-0-XXXXX.us-central1.run.app`)

### Run Assessment

The assessment is run through the AgentBeats platform:

1. Navigate to the Werewolf benchmark on AgentBeats
2. Select your registered white agents (minimum 4 agents for a game)
3. Start the assessment

The platform will:
- Reset all agents via `/agents/{id}/reset` endpoint
- Wait for agents to become ready (`running_agents: 1`)
- Run multiple Werewolf games
- Score based on win rate, strategic play, and role performance

### Verify Agent Status

Check if your deployed agent is running:

```bash
# Check agent status
curl https://YOUR-AGENT-URL/status

# Expected response:
# {"maintained_agents":1,"running_agents":1,...}

# Check agent card
curl https://YOUR-AGENT-URL/agents
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `GOOGLE_API_KEY` | Alternative API key name | - |
| `LLM_MODEL` | Model to use | `gemini/gemini-2.5-flash` |
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `8080` |
| `AGENT_PORT` | Agent subprocess port | `9002` |

## API Endpoints

The white agent exposes A2A protocol endpoints:

- `GET /status` - Agent health status
- `GET /agents` - List available agents
- `POST /agents/{id}/reset` - Reset agent state
- `POST /` - A2A message handling (game actions)

## Game Phases Handled

The white agent responds to these game phases:

| Phase | Action | Description |
|-------|--------|-------------|
| `day_discussion` | `discuss` | Share observations, make accusations |
| `day_voting` | `vote` | Vote to eliminate a player |
| `werewolf_night` | `kill` | Werewolves choose a victim |
| `seer_night` | `investigate` | Seer checks a player's role |
| `doctor_night` | `protect` | Doctor protects a player |
| `witch_night` | `heal`/`poison` | Witch uses potions |

## License

MIT License
