"""Tests for the Werewolf state manager helpers."""

from collections import Counter
import random

from app.game.state import StateManager
from app.types.agent import ActionType, WerewolfAction
from app.types.game import GameConfig, GamePhase


def _make_action(agent_id: str, action_type: ActionType, target: str | None = None) -> WerewolfAction:
    return WerewolfAction(
        agent_id=agent_id,
        action_type=action_type,
        target_agent_id=target,
        reasoning="test",
        confidence=0.8,
    )


def test_assign_roles_respects_configuration():
    agent_ids = [f"agent_{i}" for i in range(6)]
    config = GameConfig(num_werewolves=2, has_seer=True, has_doctor=True, has_hunter=True)

    roles = StateManager.assign_roles(agent_ids, config.model_dump())

    assert set(roles.keys()) == set(agent_ids)
    role_counts = Counter(roles.values())
    assert role_counts["werewolf"] == 2
    assert role_counts["seer"] == 1
    assert role_counts["doctor"] == 1
    assert role_counts["hunter"] == 1
    assert role_counts["villager"] == len(agent_ids) - 5


def test_get_next_phase_cycles_through_enabled_roles():
    config = GameConfig()

    assert StateManager.get_next_phase(GamePhase.SETUP, config.model_dump()) == GamePhase.DAY_DISCUSSION
    assert StateManager.get_next_phase(GamePhase.DAY_DISCUSSION, config.model_dump()) == GamePhase.DAY_VOTING
    assert StateManager.get_next_phase(GamePhase.DAY_VOTING, config.model_dump()) == GamePhase.NIGHT_WEREWOLF
    assert StateManager.get_next_phase(GamePhase.NIGHT_WEREWOLF, config.model_dump()) == GamePhase.NIGHT_SEER
    assert StateManager.get_next_phase(GamePhase.NIGHT_SEER, config.model_dump()) == GamePhase.NIGHT_DOCTOR
    assert StateManager.get_next_phase(GamePhase.NIGHT_DOCTOR, config.model_dump()) == GamePhase.DAY_DISCUSSION


def test_get_next_phase_skips_disabled_roles():
    config = GameConfig(has_seer=False, has_doctor=False)

    assert StateManager.get_next_phase(GamePhase.DAY_DISCUSSION, config.model_dump()) == GamePhase.DAY_VOTING
    assert StateManager.get_next_phase(GamePhase.DAY_VOTING, config.model_dump()) == GamePhase.NIGHT_WEREWOLF
    assert StateManager.get_next_phase(GamePhase.NIGHT_WEREWOLF, config.model_dump()) == GamePhase.DAY_DISCUSSION


def test_process_voting_results_returns_majority(monkeypatch, game_state_factory):
    state = game_state_factory()
    state.current_votes = {
        "agent_0": "agent_4",
        "agent_1": "agent_4",
        "agent_2": "agent_3",
    }

    eliminated = StateManager.process_voting_results(state)
    assert eliminated == "agent_4"

    # Force deterministic tie-break
    state.current_votes = {
        "agent_0": "agent_4",
        "agent_1": "agent_3",
    }
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    eliminated = StateManager.process_voting_results(state)
    assert eliminated in {"agent_3", "agent_4"}
    assert eliminated == "agent_4"


def test_process_werewolf_kill_requires_majority(game_state_factory):
    state = game_state_factory(phase=GamePhase.NIGHT_WEREWOLF)

    actions = [
        _make_action("agent_0", ActionType.KILL, "agent_4"),
        _make_action("agent_1", ActionType.KILL, "agent_4"),
    ]

    target = StateManager.process_werewolf_kill(state, actions)
    assert target == "agent_4"

    insufficient = [_make_action("agent_0", ActionType.KILL, "agent_3")]
    assert StateManager.process_werewolf_kill(state, insufficient) is None


def test_eliminate_agent_updates_state(game_state_factory):
    state = game_state_factory()
    StateManager.eliminate_agent(state, "agent_4")

    assert "agent_4" not in state.alive_agent_ids
    assert "agent_4" in state.eliminated_agent_ids


def test_advance_round_clears_votes_and_moves_phase(game_state_factory):
    state = game_state_factory(phase=GamePhase.DAY_VOTING)
    state.current_votes = {"agent_0": "agent_4"}
    state.round_number = 1

    StateManager.advance_round(state)
    assert state.current_votes == {}
    assert state.phase == GamePhase.NIGHT_WEREWOLF
    assert state.round_number == 1

    state.phase = GamePhase.NIGHT_DOCTOR
    StateManager.advance_round(state)
    assert state.phase == GamePhase.DAY_DISCUSSION
    assert state.round_number == 2


def test_create_round_record_captures_summary(game_state_factory):
    state = game_state_factory()
    actions = [
        _make_action("agent_0", ActionType.VOTE, "agent_4"),
        _make_action("agent_1", ActionType.VOTE, "agent_4"),
    ]

    record = StateManager.create_round_record(state, actions, ["agent_4"])
    assert record.round_number == state.round_number
    assert record.phase == state.phase
    assert record.eliminated_agents == ["agent_4"]
    assert len(record.actions) == 2


def test_get_visible_state_reveals_role_specific_info(game_state_factory):
    state = game_state_factory()
    state.phase = GamePhase.DAY_VOTING
    state.current_votes = {"agent_0": "agent_4"}

    wolf_view = StateManager.get_visible_state(state, "agent_0")
    assert wolf_view["your_role"] == "werewolf"
    assert set(wolf_view["werewolf_teammates"]) == {"agent_0", "agent_1"}
    assert wolf_view["current_votes"] == {"agent_0": "agent_4"}

    villager_view = StateManager.get_visible_state(state, "agent_4")
    assert villager_view["your_role"] == "villager"
    assert "werewolf_teammates" not in villager_view
