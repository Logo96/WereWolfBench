"""Werewolf Benchmark Green Agent - A2A Server"""

import os
import logging
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

from a2a_sdk import A2AServer, A2AHandler, TaskResult
from a2a_sdk.models import AgentInfo, Capability

from app.orchestrator import GameOrchestrator
from app.storage import GameLogger
from app.types.game import GameConfig

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

storage: Optional[GameLogger] = None
orchestrator: Optional[GameOrchestrator] = None
a2a_server: Optional[A2AServer] = None


class WerewolfBenchmarkHandler(A2AHandler):
    def __init__(self, orchestrator: GameOrchestrator, storage: GameLogger):
        self.orchestrator = orchestrator
        self.storage = storage

    async def start_game(self, agent_urls: List[str], config: Optional[Dict[str, Any]] = None) -> TaskResult:
        try:
            if len(agent_urls) < 4:
                raise ValueError("Minimum 4 agents required")

            game_config = GameConfig(**config) if config else None
            game_id = await self.orchestrator.start_game(agent_urls, game_config)

            return TaskResult(
                success=True,
                data={"game_id": game_id, "status": "started", "num_agents": len(agent_urls)}
            )
        except Exception as e:
            logger.error(f"Error starting game: {e}")
            return TaskResult(success=False, error=str(e))

    async def get_game_status(self, game_id: str) -> TaskResult:
        try:
            game_state = self.storage.get_game(game_id)
            if not game_state:
                raise ValueError(f"Game {game_id} not found")

            return TaskResult(
                success=True,
                data={
                    "game_id": game_id,
                    "status": game_state.status.value,
                    "phase": game_state.phase.value,
                    "round_number": game_state.round_number,
                    "alive_agents": game_state.alive_agent_ids,
                    "eliminated_agents": game_state.eliminated_agent_ids,
                    "winner": game_state.winner
                }
            )
        except Exception as e:
            logger.error(f"Error getting game status: {e}")
            return TaskResult(success=False, error=str(e))

    async def list_games(self) -> TaskResult:
        try:
            summaries = [
                self.storage.get_game_summary(game_id)
                for game_id in self.storage.list_games()
            ]
            return TaskResult(
                success=True,
                data={"total_games": len(summaries), "games": [s for s in summaries if s]}
            )
        except Exception as e:
            logger.error(f"Error listing games: {e}")
            return TaskResult(success=False, error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, orchestrator, a2a_server

    storage = GameLogger()
    orchestrator = GameOrchestrator(storage)
    handler = WerewolfBenchmarkHandler(orchestrator, storage)

    agent_info = AgentInfo(
        name="Werewolf Benchmark Green Agent",
        version="0.1.0",
        description="Orchestrates Werewolf games between A2A agents. White agents must implement werewolf_action capability.",
        capabilities=[
            Capability(
                name="start_game",
                description="Start a new Werewolf game",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_urls": {
                            "type": "array",
                            "items": {"type": "string", "format": "uri"},
                            "minItems": 4
                        },
                        "config": {"type": "object"}
                    },
                    "required": ["agent_urls"]
                }
            ),
            Capability(
                name="get_game_status",
                description="Get game status",
                input_schema={
                    "type": "object",
                    "properties": {"game_id": {"type": "string"}},
                    "required": ["game_id"]
                }
            ),
            Capability(
                name="list_games",
                description="List all games",
                input_schema={"type": "object", "properties": {}}
            )
        ]
    )

    a2a_server = A2AServer(agent_info=agent_info, handler=handler)
    a2a_server.register_task("start_game", handler.start_game)
    a2a_server.register_task("get_game_status", handler.get_game_status)
    a2a_server.register_task("list_games", handler.list_games)

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
        "discovery": "/.well-known/agent.json",
        "tasks": "/tasks"
    }


@app.get("/.well-known/agent.json")
async def get_agent_card():
    if not a2a_server:
        raise HTTPException(status_code=500, detail="A2A server not initialized")
    return a2a_server.get_agent_info()


@app.post("/tasks")
async def handle_task(request: Request):
    if not a2a_server:
        raise HTTPException(status_code=500, detail="A2A server not initialized")

    try:
        request_data = await request.json()
        return await a2a_server.handle_task(request_data)
    except Exception as e:
        logger.error(f"Error handling task: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "storage": storage is not None,
        "orchestrator": orchestrator is not None,
        "a2a": a2a_server is not None
    }


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)