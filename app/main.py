"""Werewolf Benchmark Green Agent - A2A Server"""

import os
import logging
import uuid
import json
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

from a2a.types import (
    AgentCard, AgentSkill, AgentCapabilities, AgentInterface,
    SendMessageRequest, Message, Part, TextPart, Role,
    Task, TaskStatus, TaskState
)

from app.orchestrator import GameOrchestrator
from app.logging.storage import GameLogger
from app.types.game import GameConfig

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

storage: Optional[GameLogger] = None
orchestrator: Optional[GameOrchestrator] = None


async def handle_start_game(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle start_game task"""
    agent_urls = params.get("agent_urls", [])
    config = params.get("config")

    if len(agent_urls) < 4:
        raise ValueError("Minimum 4 agents required")

    game_config = GameConfig(**config) if config else None
    game_id = await orchestrator.start_game(agent_urls, game_config)

    return {
        "game_id": game_id,
        "status": "started",
        "num_agents": len(agent_urls)
    }


async def handle_get_game_status(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_game_status task"""
    game_id = params.get("game_id")
    if not game_id:
        raise ValueError("game_id is required")

    game_state = storage.get_game(game_id)
    if not game_state:
        raise ValueError(f"Game {game_id} not found")

    return {
        "game_id": game_id,
        "status": game_state.status.value,
        "phase": game_state.phase.value,
        "round_number": game_state.round_number,
        "alive_agents": game_state.alive_agent_ids,
        "eliminated_agents": game_state.eliminated_agent_ids,
        "winner": game_state.winner
    }


async def handle_list_games(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle list_games task"""
    summaries = [
        storage.get_game_summary(game_id)
        for game_id in storage.list_games()
    ]
    return {
        "total_games": len(summaries),
        "games": [s for s in summaries if s]
    }


TASK_HANDLERS = {
    "start_game": handle_start_game,
    "get_game_status": handle_get_game_status,
    "list_games": handle_list_games,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, orchestrator

    storage = GameLogger()
    orchestrator = GameOrchestrator(storage)

    logger.info("Started Werewolf Benchmark Green Agent")
    yield

    if orchestrator:
        await orchestrator.close()


app = FastAPI(
    title="Werewolf Benchmark Green Agent",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "Werewolf Benchmark Green Agent",
        "type": "A2A",
        "discovery": "/agent.json"
    }


@app.get("/agent.json")
async def get_agent_card():
    """Return the A2A AgentCard"""
    agent_card = AgentCard(
        name="Werewolf Benchmark Green Agent",
        version="0.1.0",
        description="Orchestrates Werewolf games between A2A agents. White agents must implement werewolf_action capability.",
        url=os.getenv("BASE_URL", "http://localhost:8000"),
        preferred_transport="JSONRPC",
        protocol_version="0.3.0",
        capabilities=AgentCapabilities(
            streaming=False,
            push_notifications=False,
            state_transition_history=False
        ),
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="start_game",
                name="Start Game",
                description="Start a new Werewolf game with A2A agents",
                tags=["werewolf", "game", "orchestration"],
                examples=["Start a game with 4 agents"]
            ),
            AgentSkill(
                id="get_game_status",
                name="Get Game Status",
                description="Get the current status of a game",
                tags=["werewolf", "game", "status"],
                examples=["What's the status of game abc-123?"]
            ),
            AgentSkill(
                id="list_games",
                name="List Games",
                description="List all games",
                tags=["werewolf", "game", "list"],
                examples=["Show all games"]
            )
        ]
    )
    return agent_card.model_dump(exclude_none=True)


@app.post("/")
async def handle_jsonrpc(request: Request):
    """Handle A2A JSON-RPC requests"""
    try:
        data = await request.json()
        method = data.get("method")
        params = data.get("params", {})
        req_id = data.get("id")

        if method == "message/send":
            # Extract the task from the message
            message_params = params.get("message")
            if not message_params:
                raise ValueError("message parameter required")

            # Parse the message to determine task
            message_parts = message_params.get("parts", [])
            task_name = None
            task_params = {}

            for part in message_parts:
                if part.get("kind") == "text":
                    text = part.get("text", "")
                    try:
                        task_data = json.loads(text)
                        task_name = task_data.get("task")
                        task_params = task_data.get("parameters", {})
                    except:
                        pass

            if not task_name or task_name not in TASK_HANDLERS:
                raise ValueError(f"Unknown task: {task_name}")

            result_data = await TASK_HANDLERS[task_name](task_params)

            task_id = str(uuid.uuid4())
            context_id = str(uuid.uuid4())

            response_message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[
                    TextPart(kind="text", text=json.dumps(result_data))
                ]
            )

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": response_message.model_dump(exclude_none=True)
            }
        else:
            raise ValueError(f"Unsupported method: {method}")

    except Exception as e:
        logger.error(f"Error handling JSON-RPC request: {e}", exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": req_id if 'req_id' in locals() else None,
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": str(e)
            }
        }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "storage": storage is not None,
        "orchestrator": orchestrator is not None
    }


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)