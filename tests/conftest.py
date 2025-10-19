"""Shared test fixtures for Werewolf game logic."""

from collections.abc import Callable
from typing import Dict, Iterable, Optional

import pytest

from app.types.agent import AgentRole
from app.types.game import GameConfig, GamePhase, GameState, GameStatus


@pytest.fixture
def game_state_factory() -> Callable[..., GameState]:
    """Factory fixture that builds customizable game states for tests."""

    def _factory(
        *,
        phase: GamePhase = GamePhase.DAY_DISCUSSION,
        alive_agents: Optional[Iterable[str]] = None,
        eliminated_agents: Optional[Iterable[str]] = None,
        current_votes: Optional[Dict[str, str]] = None,
        role_assignments: Optional[Dict[str, str]] = None,
        config: Optional[GameConfig] = None,
        status: GameStatus = GameStatus.IN_PROGRESS,
        round_number: int = 1,
        agent_ids: Optional[Iterable[str]] = None,
    ) -> GameState:
        base_agent_ids = list(agent_ids or [f"agent_{i}" for i in range(5)])

        default_roles: Dict[str, str] = {
            base_agent_ids[0]: AgentRole.WEREWOLF.value,
        }
        if len(base_agent_ids) > 1:
            default_roles[base_agent_ids[1]] = AgentRole.WEREWOLF.value
        if len(base_agent_ids) > 2:
            default_roles[base_agent_ids[2]] = AgentRole.SEER.value
        if len(base_agent_ids) > 3:
            default_roles[base_agent_ids[3]] = AgentRole.DOCTOR.value

        for agent_id in base_agent_ids:
            default_roles.setdefault(agent_id, AgentRole.VILLAGER.value)

        alive_list = list(base_agent_ids) if alive_agents is None else list(alive_agents)
        eliminated_list = [] if eliminated_agents is None else list(eliminated_agents)

        return GameState(
            game_id="test-game",
            status=status,
            phase=phase,
            round_number=round_number,
            agent_ids=base_agent_ids,
            alive_agent_ids=alive_list,
            eliminated_agent_ids=eliminated_list,
            role_assignments=role_assignments or default_roles,
            current_votes=current_votes or {},
            config=config or GameConfig(),
            round_history=[],
        )

    return _factory
