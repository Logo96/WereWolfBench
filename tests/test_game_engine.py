"""End-to-end tests for the Werewolf game engine."""

from datetime import datetime

import pytest

from app.game.engine import GameEngine
from app.types.agent import ActionType, WerewolfAction
from app.types.game import GameConfig, GamePhase, GameState, GameStatus


def _make_action(agent_id: str, action_type: ActionType, target: str | None = None) -> WerewolfAction:
    return WerewolfAction(
        agent_id=agent_id,
        action_type=action_type,
        target_agent_id=target,
        reasoning="test",
        confidence=0.7,
    )


def test_create_game_initializes_state(monkeypatch):
    engine = GameEngine()
    agent_urls = [f"http://agent{i}.test" for i in range(8)]

    state = engine.create_game(agent_urls)
    assert state.game_id
    assert state.status == GameStatus.WAITING
    assert state.phase == GamePhase.SETUP
    assert state.round_number == 0
    assert state.agent_ids == [f"agent_{i}" for i in range(8)]
    assert state.alive_agent_ids == state.agent_ids
    assert len(state.role_assignments) == len(agent_urls)


def test_create_game_requires_minimum_agents():
    engine = GameEngine()
    with pytest.raises(ValueError):
        engine.create_game(["http://agent.test"] * 3)


def test_start_game_transitions_state(game_state_factory):
    state = GameState(
        game_id="game-1",
        status=GameStatus.WAITING,
        phase=GamePhase.SETUP,
        round_number=0,
        agent_ids=[f"agent_{i}" for i in range(5)],
        alive_agent_ids=[f"agent_{i}" for i in range(5)],
        role_assignments={
            "agent_0": "werewolf",
            "agent_1": "werewolf",
            "agent_2": "seer",
            "agent_3": "doctor",
            "agent_4": "villager",
        },
    )

    engine = GameEngine()
    started = engine.start_game(state)
    assert started.status == GameStatus.IN_PROGRESS
    assert started.phase == GamePhase.DAY_DISCUSSION
    assert started.round_number == 1
    assert isinstance(started.started_at, datetime)


def test_process_action_rejects_invalid_vote(game_state_factory):
    state = game_state_factory(phase=GamePhase.DAY_VOTING)
    engine = GameEngine()

    invalid_vote = _make_action(state.alive_agent_ids[0], ActionType.VOTE)

    success, error = engine.process_action(state, invalid_vote)
    assert not success
    assert error == "Vote must specify a target"
    assert state.current_votes == {}


def test_process_action_records_valid_vote(game_state_factory):
    state = game_state_factory(phase=GamePhase.DAY_VOTING)
    engine = GameEngine()

    vote = _make_action(state.alive_agent_ids[0], ActionType.VOTE, state.alive_agent_ids[1])
    success, error = engine.process_action(state, vote)

    assert success and error is None
    assert state.current_votes[vote.agent_id] == vote.target_agent_id


def test_should_advance_phase_requires_all_day_actions(game_state_factory):
    state = game_state_factory(phase=GamePhase.DAY_DISCUSSION)
    engine = GameEngine()

    actions = [
        _make_action(state.alive_agent_ids[0], ActionType.DISCUSS),
        _make_action(state.alive_agent_ids[1], ActionType.DISCUSS),
    ]
    assert not engine.should_advance_phase(state, actions)

    actions.append(_make_action(state.alive_agent_ids[2], ActionType.DISCUSS))
    actions.append(_make_action(state.alive_agent_ids[3], ActionType.DISCUSS))
    actions.append(_make_action(state.alive_agent_ids[4], ActionType.DISCUSS))
    assert engine.should_advance_phase(state, actions)


def test_should_advance_phase_night_requires_role_actions(game_state_factory):
    state = game_state_factory(phase=GamePhase.NIGHT_WEREWOLF)
    engine = GameEngine()

    actions = [_make_action("agent_0", ActionType.KILL, "agent_4")]
    assert not engine.should_advance_phase(state, actions)

    actions.append(_make_action("agent_1", ActionType.KILL, "agent_4"))
    assert engine.should_advance_phase(state, actions)


def test_advance_phase_day_voting_eliminates_agent(game_state_factory):
    agent_ids = [f"agent_{i}" for i in range(6)]
    state = game_state_factory(phase=GamePhase.DAY_VOTING, agent_ids=agent_ids)
    state.current_votes = {
        "agent_0": "agent_4",
        "agent_1": "agent_4",
        "agent_2": "agent_4",
    }

    engine = GameEngine()
    updated, eliminated = engine.advance_phase(state, [])

    assert eliminated == ["agent_4"]
    assert "agent_4" not in updated.alive_agent_ids
    assert updated.phase == GamePhase.NIGHT_WEREWOLF
    assert updated.round_history
    assert updated.current_votes == {}


def test_advance_phase_werewolf_night_respects_doctor_protection(game_state_factory):
    state = game_state_factory(phase=GamePhase.NIGHT_WEREWOLF)

    actions = [
        _make_action("agent_0", ActionType.KILL, "agent_4"),
        _make_action("agent_1", ActionType.KILL, "agent_4"),
        _make_action("agent_3", ActionType.PROTECT, "agent_4"),
    ]

    engine = GameEngine()
    updated, eliminated = engine.advance_phase(state, actions)

    assert eliminated == []
    assert "agent_4" in updated.alive_agent_ids
    assert updated.phase == GamePhase.NIGHT_SEER


def test_advance_phase_triggers_game_end_on_last_werewolf(game_state_factory):
    state = game_state_factory(
        phase=GamePhase.DAY_VOTING,
        alive_agents=["agent_0", "agent_2", "agent_3"],
        eliminated_agents=["agent_1"],
    )
    state.current_votes = {
        "agent_2": "agent_0",
        "agent_3": "agent_0",
    }

    engine = GameEngine()
    updated, eliminated = engine.advance_phase(state, [])

    assert eliminated == ["agent_0"]
    assert updated.status == GameStatus.COMPLETED
    assert updated.phase == GamePhase.GAME_OVER
    assert updated.winner == "villagers"
    assert updated.completed_at is not None
