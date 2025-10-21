"""Utility helpers to spin up deterministic dummy agents for testing."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Dict, Iterable, Optional, Sequence
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from app.types.agent import ActionType, AgentRole, DiscussionActionType

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


def _choose_discussion_sub_action(
    agent_id: str, 
    role: str, 
    visible_state: Dict[str, Any], 
    alive_agents: Sequence[str]
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Choose a discussion sub-action based on role and game state."""
    
    # 70% chance to take a discussion sub-action (increased from 30%)
    if random.random() < 0.7:
        if role == "seer":
            return _seer_discussion_action(visible_state, alive_agents)
        elif role == "doctor":
            return _doctor_discussion_action(visible_state, alive_agents)
        elif role == "witch":
            return _witch_discussion_action(visible_state, alive_agents)
        elif role == "werewolf":
            return _werewolf_discussion_action(visible_state, alive_agents)
        else:  # villager, hunter, etc.
            return _villager_discussion_action(visible_state, alive_agents)
    else:
        return None, None, None


def _seer_discussion_action(visible_state: Dict[str, Any], alive_agents: Sequence[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Seer discussion actions."""
    investigation_results = visible_state.get("investigation_results", [])
    
    # 60% chance to reveal investigation results (increased from 40%)
    if random.random() < 0.6 and investigation_results:
        investigation = random.choice(investigation_results)
        target_id = investigation["target_id"]
        is_werewolf = investigation["is_werewolf"]
        
        if is_werewolf:
            content = f"I investigated {target_id} and they are a werewolf! We need to eliminate them!"
        else:
            content = f"I investigated {target_id} and they are innocent. We can trust them."
        
        return DiscussionActionType.REVEAL_INVESTIGATION.value, content, None
    
    # 30% chance to reveal identity (increased from 20%)
    elif random.random() < 0.3:
        return DiscussionActionType.REVEAL_IDENTITY.value, "I am the seer. I have been investigating players at night to find werewolves.", "seer"
    
    # 25% chance to accuse someone (increased from 15%)
    elif random.random() < 0.35:
        target = _first_alive(alive_agents, skip=[visible_state.get("agent_id")])
        if target:
            return DiscussionActionType.ACCUSE.value, f"I suspect {target} is acting suspicious. We should watch them closely.", None
    
    # Default to general discussion
    return DiscussionActionType.GENERAL_DISCUSSION.value, "I'm analyzing the information we have. We need to be careful about who we trust.", None


def _doctor_discussion_action(visible_state: Dict[str, Any], alive_agents: Sequence[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Doctor discussion actions."""
    # 50% chance to reveal protection (increased from 30%)
    if random.random() < 0.5:
        target = _first_alive(alive_agents, skip=[visible_state.get("agent_id")])
        if target:
            return DiscussionActionType.REVEAL_PROTECTED.value, f"I protected {target} last night. They should be safe from werewolf attacks.", None
    
    # 30% chance to reveal identity (increased from 20%)
    elif random.random() < 0.3:
        return DiscussionActionType.REVEAL_IDENTITY.value, "I am the doctor. I have been protecting players at night.", "doctor"
    
    # 15% chance to defend someone
    elif random.random() < 0.35:
        target = _first_alive(alive_agents, skip=[visible_state.get("agent_id")])
        if target:
            return DiscussionActionType.DEFEND.value, f"I think {target} is innocent. We should not vote for them.", None
    
    # Default to general discussion
    return DiscussionActionType.GENERAL_DISCUSSION.value, "I'm trying to keep everyone safe. We need to work together to find the werewolves.", None


def _witch_discussion_action(visible_state: Dict[str, Any], alive_agents: Sequence[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Witch discussion actions."""
    killed_this_night = visible_state.get("killed_this_night", [])
    
    # 25% chance to reveal healing info
    if random.random() < 0.35 and killed_this_night:
        healed = random.choice(killed_this_night)
        return DiscussionActionType.REVEAL_HEALED_KILLED.value, f"I healed {healed} last night. They were attacked but are now safe.", None
    
    # 20% chance to reveal identity
    elif random.random() < 0.3:
        return DiscussionActionType.REVEAL_IDENTITY.value, "I am the witch. I have been healing and poisoning players at night.", "witch"
    
    # 15% chance to accuse someone
    elif random.random() < 0.35:
        target = _first_alive(alive_agents, skip=[visible_state.get("agent_id")])
        if target:
            return DiscussionActionType.ACCUSE.value, f"I think {target} might be a werewolf. We should investigate them.", None
    
    # Default to general discussion
    return DiscussionActionType.GENERAL_DISCUSSION.value, "I'm using my powers to help the village. We need to be strategic about this.", None


def _werewolf_discussion_action(visible_state: Dict[str, Any], alive_agents: Sequence[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Werewolf discussion actions."""
    werewolf_teammates = visible_state.get("werewolf_teammates", [])
    
    # 60% chance to accuse a villager (increased from 40%)
    if random.random() < 0.6:
        villagers = [aid for aid in alive_agents if aid not in werewolf_teammates]
        target = _first_alive(villagers)
        if target:
            return DiscussionActionType.ACCUSE.value, f"I think {target} is acting suspicious. We should vote for them.", None
    
    # 30% chance to defend a teammate (increased from 20%)
    elif random.random() < 0.3:
        teammates = [aid for aid in alive_agents if aid in werewolf_teammates]
        target = _first_alive(teammates)
        if target:
            return DiscussionActionType.DEFEND.value, f"I think {target} is innocent. We should not vote for them.", None
    
    # 35% chance to claim a fake role (increased from 15%)
    elif random.random() < 0.35:
        fake_roles = ["villager", "hunter", "doctor"]
        fake_role = random.choice(fake_roles)
        return DiscussionActionType.CLAIM_ROLE.value, f"I am a {fake_role}. I have been helping the village.", fake_role
    
    # Default to general discussion
    return DiscussionActionType.GENERAL_DISCUSSION.value, "I'm trying to figure out who the werewolves are. We need to be careful.", None


def _villager_discussion_action(visible_state: Dict[str, Any], alive_agents: Sequence[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Villager discussion actions."""
    # 40% chance to reveal identity (increased from 25%)
    if random.random() < 0.4:
        return DiscussionActionType.REVEAL_IDENTITY.value, "I am a villager. I have been trying to help find the werewolves.", "villager"
    
    # 30% chance to accuse someone (increased from 20%)
    elif random.random() < 0.3:
        target = _first_alive(alive_agents, skip=[visible_state.get("agent_id")])
        if target:
            return DiscussionActionType.ACCUSE.value, f"I think {target} might be a werewolf. We should watch them.", None
    
    # 25% chance to defend someone (increased from 15%)
    elif random.random() < 0.25:
        target = _first_alive(alive_agents, skip=[visible_state.get("agent_id")])
        if target:
            return DiscussionActionType.DEFEND.value, f"I think {target} is innocent. We should not vote for them.", None
    
    # Default to general discussion
    return DiscussionActionType.GENERAL_DISCUSSION.value, "I'm trying to help the village. We need to work together to find the werewolves.", None


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
    elif phase == "night_witch":
        if role == AgentRole.WITCH.value:
            # Check if heal is available and someone was killed
            killed_this_night = visible_state.get("killed_this_night")
            heal_available = visible_state.get("heal_available", False)
            poison_available = visible_state.get("poison_available", False)
            
            if heal_available and killed_this_night:
                action_type = ActionType.HEAL.value
                target = killed_this_night
            elif poison_available:
                action_type = ActionType.POISON.value
                target = _first_alive(alive_agents, skip=[agent_id])
                if not target:
                    action_type = ActionType.PASS.value
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
    
    # Hunter elimination check (happens after any elimination)
    elif role == AgentRole.HUNTER.value and agent_id not in alive_agents:
        # Hunter was eliminated, can shoot
        target = _first_alive(alive_agents)
        action_type = ActionType.SHOOT.value if target else ActionType.PASS.value

    # Build action payload
    action_payload = {
        "agent_id": agent_id,
        "action_type": action_type,
        "target_agent_id": target,
        "reasoning": reasoning,
        "confidence": 0.75,
        "metadata": {"origin": "dummy"},
    }
    
    # Add discussion sub-action fields if this is a discuss action
    if phase == "day_discussion" and action_type == ActionType.DISCUSS.value:
        discussion_action_type, discussion_content, claimed_role = _choose_discussion_sub_action(
            agent_id, role, visible_state, alive_agents
        )
        if discussion_action_type:
            action_payload["discussion_action_type"] = discussion_action_type
        if discussion_content:
            action_payload["discussion_content"] = discussion_content
        if claimed_role:
            action_payload["claimed_role"] = claimed_role

    return {
        "action": action_payload,
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
