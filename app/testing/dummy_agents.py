"""Utility helpers to spin up deterministic dummy agents for testing."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Iterable, Optional, Sequence
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from app.types.agent import ActionType, AgentRole

logger = logging.getLogger(__name__)


def _first_alive(
    alive: Sequence[str],
    skip: Optional[Iterable[str]] = None,
    fallback: Optional[str] = None
) -> Optional[str]:
    """Return the first alive agent that is not in the skip collection."""
    skip_set = set(skip or [])
    for agent_id in alive:
        if agent_id not in skip_set:
            return agent_id
    return fallback


def _build_action_payload(
    agent_id: str,
    task_payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Create an action payload matching the AgentResponse schema."""
    visible_state: Dict[str, Any] = task_payload.get("game_state", {})
    alive_agents: Sequence[str] = visible_state.get("alive_agents", [])
    role = task_payload.get("your_role") or visible_state.get("your_role")
    phase = task_payload.get("phase")

    action_type = ActionType.PASS.value
    target: Optional[str] = None
    reasoning = "aaaa"

    if phase == "day_discussion":
        action_type = ActionType.DISCUSS.value
    elif phase == "day_voting":
        action_type = ActionType.VOTE.value
        target = _first_alive(alive_agents, skip=[agent_id])
        if not target:
            action_type = ActionType.PASS.value
    elif phase == "night_werewolf":
        if role == AgentRole.WEREWOLF.value:
            teammates = set(visible_state.get("werewolf_teammates", []))
            teammates.add(agent_id)
            target = _first_alive(alive_agents, skip=teammates)
            if target:
                action_type = ActionType.KILL.value
            else:
                action_type = ActionType.PASS.value
        else:
            action_type = ActionType.PASS.value
    elif phase == "night_seer":
        if role == AgentRole.SEER.value:
            target = _first_alive(alive_agents, skip=[agent_id])
            action_type = ActionType.INVESTIGATE.value if target else ActionType.PASS.value
        else:
            action_type = ActionType.PASS.value
    elif phase == "night_doctor":
        if role == AgentRole.DOCTOR.value:
            target = _first_alive(alive_agents) or agent_id
            action_type = ActionType.PROTECT.value
        else:
            action_type = ActionType.PASS.value

    return {
        "action": {
            "agent_id": agent_id,
            "action_type": action_type,
            "target_agent_id": target,
            "reasoning": reasoning,
            "confidence": 0.75,
            "metadata": {"origin": "dummy"},
        },
        "game_understanding": {
            "phase": phase,
            "alive_agents": list(alive_agents),
        },
        "suspicions": [],
    }


def create_dummy_agent_app(agent_name: str) -> FastAPI:
    """Create a FastAPI application that emulates a basic white agent."""
    app = FastAPI(title=f"Dummy Agent {agent_name}")

    @app.get("/")
    async def root():
        return {"name": agent_name, "type": "dummy_agent"}

    @app.post("/")
    async def handle_message(request: Request):
        payload = await request.json()
        method = payload.get("method")
        request_id = payload.get("id")

        if method != "message/send":
            logger.warning("Unsupported method %s", method)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"},
                },
                status_code=400,
            )

        message_params = payload.get("params", {}).get("message", {})
        text_parts = [
            part.get("text")
            for part in message_params.get("parts", [])
            if part.get("kind") == "text"
        ]

        task_payload: Dict[str, Any] = {}
        if text_parts and text_parts[0]:
            try:
                task_payload = json.loads(text_parts[0])
            except json.JSONDecodeError as exc:
                logger.error("Failed to decode task payload: %s", exc)

        response_payload = _build_action_payload(agent_name, task_payload)

        response_message = {
            "messageId": str(uuid4()),
            "role": "agent",
            "parts": [
                {
                    "kind": "text",
                    "text": json.dumps(response_payload),
                }
            ],
        }

        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": response_message,
            }
        )

    return app


class DummyAgentServer:
    """Manage a dummy agent server lifecycle for integration tests or manual runs."""

    def __init__(self, agent_name: str, host: str = "127.0.0.1", port: int = 9000):
        self.agent_name = agent_name
        self.host = host
        self.port = port
        self._app = create_dummy_agent_app(agent_name)
        config = uvicorn.Config(
            app=self._app,
            host=host,
            port=port,
            log_level="warning",
            loop="asyncio",
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        self._server.install_signal_handlers = lambda: None  # type: ignore[assignment]
        self._task: Optional[asyncio.Task[None]] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def start(self) -> None:
        if self._task:
            return

        config = self._server.config
        if not config.loaded:
            config.load()
        self._server.lifespan = config.lifespan_class(config)  # type: ignore[attr-defined]

        await self._server.startup()
        self._task = asyncio.create_task(self._server.main_loop())
        while not self._server.started:
            await asyncio.sleep(0.01)

    async def close(self) -> None:
        if not self._task:
            return

        self._server.should_exit = True
        await self._task
        await self._server.shutdown()
        self._task = None
