"""End-to-end tests for the Werewolf game engine."""

from datetime import datetime

import pytest

from app.game.engine import GameEngine
from app.types.agent import ActionType, WerewolfAction, DiscussionActionType
from app.types.game import GameConfig, GamePhase, GameState, GameStatus


def _make_action(agent_id: str, action_type: ActionType, target: str | None = None, 
                discussion_action_type: DiscussionActionType = None, discussion_content: str = None) -> WerewolfAction:
    return WerewolfAction(
        agent_id=agent_id,
        action_type=action_type,
        target_agent_id=target,
        reasoning="test",
        confidence=0.7,
        discussion_action_type=discussion_action_type,
        discussion_content=discussion_content
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
    assert started.phase == GamePhase.NIGHT_WEREWOLF
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


def test_advance_phase_seer_investigation_stores_results(game_state_factory):
    state = game_state_factory(phase=GamePhase.NIGHT_SEER)
    state.role_assignments = {
        "agent_0": "werewolf",
        "agent_1": "werewolf", 
        "agent_2": "seer",
        "agent_3": "doctor",
        "agent_4": "villager",
    }

    actions = [
        _make_action("agent_2", ActionType.INVESTIGATE, "agent_0"),  # Investigate werewolf
        _make_action("agent_2", ActionType.INVESTIGATE, "agent_4"),  # Investigate villager
    ]

    engine = GameEngine()
    updated, eliminated = engine.advance_phase(state, actions)

    # Check that investigation results were stored
    assert len(updated.seer_investigations) == 2
    
    # Check first investigation (werewolf)
    werewolf_investigation = None
    villager_investigation = None
    for investigation in updated.seer_investigations.values():
        if investigation["target_id"] == "agent_0":
            werewolf_investigation = investigation
        elif investigation["target_id"] == "agent_4":
            villager_investigation = investigation
    
    assert werewolf_investigation is not None
    assert werewolf_investigation["is_werewolf"] is True
    assert werewolf_investigation["seer_id"] == "agent_2"
    
    assert villager_investigation is not None
    assert villager_investigation["is_werewolf"] is False
    assert villager_investigation["seer_id"] == "agent_2"


def test_seer_visible_state_includes_investigation_results(game_state_factory):
    state = game_state_factory()
    state.role_assignments = {"agent_0": "seer", "agent_1": "werewolf", "agent_2": "villager"}
    
    # Add some investigation results
    state.seer_investigations = {
        "investigation_1": {
            "seer_id": "agent_0",
            "target_id": "agent_1", 
            "is_werewolf": True,
            "round": 1,
            "timestamp": datetime.utcnow()
        },
        "investigation_2": {
            "seer_id": "agent_0",
            "target_id": "agent_2",
            "is_werewolf": False, 
            "round": 2,
            "timestamp": datetime.utcnow()
        }
    }

    from app.game.state import StateManager
    visible_state = StateManager.get_visible_state(state, "agent_0")
    
    assert "investigation_results" in visible_state
    investigations = visible_state["investigation_results"]
    assert len(investigations) == 2
    
    # Check that results are properly formatted
    werewolf_result = next(r for r in investigations if r["target_id"] == "agent_1")
    villager_result = next(r for r in investigations if r["target_id"] == "agent_2")
    
    assert werewolf_result["is_werewolf"] is True
    assert villager_result["is_werewolf"] is False


def test_discussion_action_identity_reveal_tracking(game_state_factory):
    """Test that identity reveals are properly tracked in game metadata."""
    state = game_state_factory(phase=GamePhase.DAY_DISCUSSION)
    state.role_assignments = {"agent_0": "seer", "agent_1": "werewolf", "agent_2": "villager"}
    
    action = _make_action(
        "agent_0", 
        ActionType.DISCUSS, 
        discussion_action_type=DiscussionActionType.REVEAL_IDENTITY,
        discussion_content="I am the seer"
    )
    
    engine = GameEngine()
    success, error = engine.process_action(state, action)
    
    assert success
    assert "identity_reveals" in state.metadata
    assert len(state.metadata["identity_reveals"]) == 1
    assert state.metadata["identity_reveals"][0]["agent_id"] == "agent_0"
    assert state.metadata["identity_reveals"][0]["revealed_role"] == "seer"


def test_discussion_action_investigation_reveal_tracking(game_state_factory):
    """Test that investigation reveals are properly tracked."""
    state = game_state_factory(phase=GamePhase.DAY_DISCUSSION)
    state.role_assignments = {"agent_0": "seer", "agent_1": "werewolf", "agent_2": "villager"}
    
    # Add some investigation results
    state.seer_investigations = {
        "inv1": {
            "seer_id": "agent_0",
            "target_id": "agent_1",
            "is_werewolf": True,
            "round": 1,
            "timestamp": datetime.utcnow()
        }
    }
    
    action = _make_action(
        "agent_0", 
        ActionType.DISCUSS, 
        discussion_action_type=DiscussionActionType.REVEAL_INVESTIGATION,
        discussion_content="I investigated agent_1 and they are a werewolf"
    )
    
    engine = GameEngine()
    success, error = engine.process_action(state, action)
    
    assert success
    assert "investigation_reveals" in state.metadata
    assert len(state.metadata["investigation_reveals"]) == 1
    reveal = state.metadata["investigation_reveals"][0]
    assert reveal["seer_id"] == "agent_0"
    assert len(reveal["revealed_investigations"]) == 1
    assert reveal["revealed_investigations"][0]["target_id"] == "agent_1"
    assert reveal["revealed_investigations"][0]["is_werewolf"] is True


def test_discussion_action_accusation_tracking(game_state_factory):
    """Test that accusations are properly tracked with correctness."""
    state = game_state_factory(phase=GamePhase.DAY_DISCUSSION)
    state.role_assignments = {"agent_0": "villager", "agent_1": "werewolf", "agent_2": "villager"}
    
    # Correct accusation
    correct_action = _make_action(
        "agent_0", 
        ActionType.DISCUSS, 
        target="agent_1",
        discussion_action_type=DiscussionActionType.ACCUSE,
        discussion_content="I think agent_1 is a werewolf"
    )
    
    # Incorrect accusation
    incorrect_action = _make_action(
        "agent_2", 
        ActionType.DISCUSS, 
        target="agent_0",
        discussion_action_type=DiscussionActionType.ACCUSE,
        discussion_content="I think agent_0 is a werewolf"
    )
    
    engine = GameEngine()
    
    # Process correct accusation
    success, error = engine.process_action(state, correct_action)
    assert success
    
    # Process incorrect accusation
    success, error = engine.process_action(state, incorrect_action)
    assert success
    
    assert "accusations" in state.metadata
    assert len(state.metadata["accusations"]) == 2
    
    # Check correctness
    correct_accusations = [a for a in state.metadata["accusations"] if a["is_correct"]]
    incorrect_accusations = [a for a in state.metadata["accusations"] if not a["is_correct"]]
    
    assert len(correct_accusations) == 1
    assert len(incorrect_accusations) == 1
    assert correct_accusations[0]["accused_id"] == "agent_1"
    assert incorrect_accusations[0]["accused_id"] == "agent_0"


def test_discussion_action_role_validation(game_state_factory):
    """Test that role-specific discussion actions are properly validated."""
    state = game_state_factory(phase=GamePhase.DAY_DISCUSSION)
    state.role_assignments = {"agent_0": "villager", "agent_1": "seer", "agent_2": "witch"}
    
    engine = GameEngine()
    
    # Villager trying to reveal investigation (should fail)
    invalid_action = _make_action(
        "agent_0", 
        ActionType.DISCUSS, 
        discussion_action_type=DiscussionActionType.REVEAL_INVESTIGATION,
        discussion_content="I investigated someone"
    )
    
    success, error = engine.process_action(state, invalid_action)
    assert not success
    assert "Only seers can reveal investigation results" in error
    
    # Seer revealing investigation (should succeed)
    valid_action = _make_action(
        "agent_1", 
        ActionType.DISCUSS, 
        discussion_action_type=DiscussionActionType.REVEAL_INVESTIGATION,
        discussion_content="I investigated someone"
    )
    
    success, error = engine.process_action(state, valid_action)
    assert success


def test_discussion_metrics_calculation():
    """Test that discussion metrics are calculated correctly."""
    from app.logging.storage import GameLogger
    
    # Create a mock game state with reveals
    state = GameState(
        game_id="test_game",
        agent_ids=["agent_0", "agent_1", "agent_2"],
        alive_agent_ids=["agent_0", "agent_1"],
        eliminated_agent_ids=["agent_2"],
        role_assignments={"agent_0": "seer", "agent_1": "werewolf", "agent_2": "villager"},
        metadata={
            "identity_reveals": [
                {"agent_id": "agent_0", "round": 1, "timestamp": datetime.utcnow(), "revealed_role": "seer"}
            ],
            "investigation_reveals": [
                {
                    "seer_id": "agent_0", 
                    "round": 1, 
                    "timestamp": datetime.utcnow(),
                    "revealed_investigations": [
                        {"target_id": "agent_1", "is_werewolf": True, "round": 1}
                    ]
                }
            ],
            "accusations": [
                {"accuser_id": "agent_0", "accused_id": "agent_1", "round": 1, "timestamp": datetime.utcnow(), "is_correct": True}
            ]
        }
    )
    
    logger = GameLogger()
    metrics = logger._calculate_discussion_metrics(state)
    
    assert metrics["identity_reveals_count"] == 1
    assert metrics["first_identity_reveal_round"] == 1
    assert metrics["investigation_reveals_count"] == 1
    assert metrics["seer_reveals_per_game"] == 1
    assert metrics["first_seer_reveal_round"] == 1
    assert metrics["accusations_count"] == 1
    assert metrics["correct_accusations_percentage"] == 100.0
