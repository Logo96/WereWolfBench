"""Werewolf Benchmark Green Agent - A2A Server"""

import os
import logging
import json
import tomllib
from typing import Optional, Dict, Any
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCard
from a2a.utils import new_agent_text_message

from app.orchestrator import GameOrchestrator
from app.logging.storage import GameLogger
from app.types.game import GameConfig

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
storage: Optional[GameLogger] = None
orchestrator: Optional[GameOrchestrator] = None


def init_globals():
    """Initialize global storage and orchestrator."""
    global storage, orchestrator
    storage = GameLogger()
    orchestrator = GameOrchestrator(storage)
    logger.info("Initialized Werewolf Benchmark Green Agent")


async def cleanup_globals():
    """Cleanup global resources."""
    global orchestrator
    if orchestrator:
        await orchestrator.close()


class WerewolfGreenAgentExecutor(AgentExecutor):
    """Executor for Werewolf Benchmark Green Agent."""

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute a task based on the incoming message."""
        global storage, orchestrator

        # Parse the incoming message
        user_message = context.message
        task_name = None
        task_params = {}

        for part in user_message.parts:
            if hasattr(part, 'root') and hasattr(part.root, 'text'):
                text = part.root.text
            elif hasattr(part, 'text'):
                text = part.text
            else:
                continue

            try:
                task_data = json.loads(text)
                task_name = task_data.get("task")
                task_params = task_data.get("parameters", {})
                break
            except json.JSONDecodeError:
                continue

        try:
            if task_name == "start_game":
                result = await self._handle_start_game(task_params)
            elif task_name == "get_game_status":
                result = await self._handle_get_game_status(task_params)
            elif task_name == "list_games":
                result = await self._handle_list_games(task_params)
            else:
                result = {"error": f"Unknown task: {task_name}"}

            # Send response
            response_message = new_agent_text_message(json.dumps(result))
            await event_queue.enqueue_event(response_message)

        except Exception as e:
            logger.error(f"Error executing task: {e}", exc_info=True)
            error_message = new_agent_text_message(json.dumps({"error": str(e)}))
            await event_queue.enqueue_event(error_message)

    async def _handle_start_game(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle start_game task."""
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

    async def _handle_get_game_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_game_status task."""
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

    async def _handle_list_games(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list_games task."""
        summaries = [
            storage.get_game_summary(game_id)
            for game_id in storage.list_games()
        ]
        return {
            "total_games": len(summaries),
            "games": [s for s in summaries if s]
        }

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel a running task."""
        pass


def load_agent_card_toml(agent_name: str = "green_agent") -> dict:
    """Load agent card configuration from TOML file."""
    # Look for TOML file in project root
    toml_path = Path(__file__).parent.parent / f"{agent_name}.toml"
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def start_green_agent(agent_name: str = "green_agent", host: str = "localhost", port: int = 9001):
    """Start the green agent server."""
    logger.info("Starting Werewolf Benchmark Green Agent...")

    # Initialize globals
    init_globals()

    # Load agent card from TOML
    agent_card_dict = load_agent_card_toml(agent_name)

    # Set URL from AGENT_URL environment variable (set by AgentBeats platform)
    # Fallback to BASE_URL or construct from host/port for local dev
    agent_url = os.getenv("AGENT_URL") or os.getenv("BASE_URL") or f"http://{host}:{port}"
    agent_card_dict["url"] = agent_url

    logger.info(f"Agent URL: {agent_card_dict['url']}")

    # Create request handler with executor
    request_handler = DefaultRequestHandler(
        agent_executor=WerewolfGreenAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    # Create A2A application
    agent_card = AgentCard(**agent_card_dict)
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # Run the server - controller handles /status and /agents
    uvicorn.run(a2a_app.build(), host=host, port=port)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    start_green_agent(host=host, port=port)
