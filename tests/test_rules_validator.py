"""Tests covering the Werewolf rules validator."""

from app.game.rules import RulesValidator
from app.types.agent import ActionType, AgentRole, WerewolfAction
from app.types.game import GamePhase


def _make_action(
    agent_id: str,
    action_type: ActionType,
    target: str | None = None,
) -> WerewolfAction:
    """Helper to build minimal Werewolf actions for testing."""
    return WerewolfAction(
        agent_id=agent_id,
        action_type=action_type,
        target_agent_id=target,
        reasoning="test",
        confidence=0.9,
    )


def test_discussion_phase_allows_discuss_and_pass(game_state_factory):
    state = game_state_factory(phase=GamePhase.DAY_DISCUSSION)
    rules = RulesValidator()

    discuss_action = _make_action(state.alive_agent_ids[0], ActionType.DISCUSS)
    role = AgentRole(state.role_assignments[discuss_action.agent_id])
    valid, error = rules.is_action_valid(discuss_action, state, role)
    assert valid and error is None

    pass_action = _make_action(state.alive_agent_ids[1], ActionType.PASS)
    role = AgentRole(state.role_assignments[pass_action.agent_id])
    valid, error = rules.is_action_valid(pass_action, state, role)
    assert valid and error is None


def test_discussion_phase_rejects_other_actions(game_state_factory):
    state = game_state_factory(phase=GamePhase.DAY_DISCUSSION)
    rules = RulesValidator()

    vote_action = _make_action(state.alive_agent_ids[0], ActionType.VOTE, state.alive_agent_ids[1])
    role = AgentRole(state.role_assignments[vote_action.agent_id])
    valid, error = rules.is_action_valid(vote_action, state, role)
    assert not valid
    assert error == "Only discussion or pass allowed during discussion phase"


def test_voting_requires_valid_target(game_state_factory):
    state = game_state_factory(phase=GamePhase.DAY_VOTING)
    rules = RulesValidator()

    missing_target = _make_action(state.alive_agent_ids[0], ActionType.VOTE)
    role = AgentRole(state.role_assignments[missing_target.agent_id])
    valid, error = rules.is_action_valid(missing_target, state, role)
    assert not valid
    assert error == "Vote must specify a target"

    invalid_target = _make_action(state.alive_agent_ids[0], ActionType.VOTE, "ghost")
    role = AgentRole(state.role_assignments[invalid_target.agent_id])
    valid, error = rules.is_action_valid(invalid_target, state, role)
    assert not valid
    assert error == "Target agent does not exist"


def test_voting_disallows_self_or_dead_targets(game_state_factory):
    state = game_state_factory(phase=GamePhase.DAY_VOTING)
    rules = RulesValidator()

    voter = state.alive_agent_ids[0]
    state.alive_agent_ids.remove(state.alive_agent_ids[1])

    dead_target = _make_action(voter, ActionType.VOTE, state.agent_ids[1])
    role = AgentRole(state.role_assignments[voter])
    valid, error = rules.is_action_valid(dead_target, state, role)
    assert not valid
    assert error == "Can only vote for living agents"

    self_vote = _make_action(voter, ActionType.VOTE, voter)
    valid, error = rules.is_action_valid(self_vote, state, role)
    assert not valid
    assert error == "Cannot vote for yourself"


def test_werewolf_phase_validates_roles(game_state_factory):
    state = game_state_factory(phase=GamePhase.NIGHT_WEREWOLF)
    rules = RulesValidator()

    non_wolf = state.alive_agent_ids[2]
    non_wolf_role = AgentRole(state.role_assignments[non_wolf])
    invalid_action = _make_action(non_wolf, ActionType.KILL, state.alive_agent_ids[3])
    valid, error = rules.is_action_valid(invalid_action, state, non_wolf_role)
    assert not valid
    assert error == "Non-werewolves must pass during werewolf phase"

    wolf = state.alive_agent_ids[0]
    wolf_role = AgentRole(state.role_assignments[wolf])
    kill_fellow_wolf = _make_action(wolf, ActionType.KILL, state.alive_agent_ids[1])
    valid, error = rules.is_action_valid(kill_fellow_wolf, state, wolf_role)
    assert not valid
    assert error == "Werewolves cannot kill other werewolves"


def test_seer_phase_validates_actions(game_state_factory):
    state = game_state_factory(phase=GamePhase.NIGHT_SEER)
    rules = RulesValidator()

    seer = state.alive_agent_ids[2]
    seer_role = AgentRole(state.role_assignments[seer])

    invalid_action = _make_action(seer, ActionType.KILL, state.alive_agent_ids[0])
    valid, error = rules.is_action_valid(invalid_action, state, seer_role)
    assert not valid
    assert error == "Seer can only investigate or pass"

    investigate_self = _make_action(seer, ActionType.INVESTIGATE, seer)
    valid, error = rules.is_action_valid(investigate_self, state, seer_role)
    assert not valid
    assert error == "Cannot investigate yourself"


def test_doctor_phase_protection_rules(game_state_factory):
    state = game_state_factory(phase=GamePhase.NIGHT_DOCTOR)
    rules = RulesValidator()

    doctor = state.alive_agent_ids[3]
    doctor_role = AgentRole(state.role_assignments[doctor])

    invalid_action = _make_action(doctor, ActionType.VOTE, state.alive_agent_ids[0])
    valid, error = rules.is_action_valid(invalid_action, state, doctor_role)
    assert not valid
    assert error == "Doctor can only protect or pass"

    missing_target = _make_action(doctor, ActionType.PROTECT)
    valid, error = rules.is_action_valid(missing_target, state, doctor_role)
    assert not valid
    assert error == "Protection must specify a target"


def test_non_role_players_must_pass_at_night(game_state_factory):
    state = game_state_factory(phase=GamePhase.NIGHT_DOCTOR)
    rules = RulesValidator()

    villager = state.alive_agent_ids[4]
    villager_role = AgentRole(state.role_assignments[villager])

    invalid_action = _make_action(villager, ActionType.PROTECT, state.alive_agent_ids[0])
    valid, error = rules.is_action_valid(invalid_action, state, villager_role)
    assert not valid
    assert error == "Non-doctors must pass during doctor phase"


def test_game_end_conditions_draw_when_no_alive(game_state_factory):
    state = game_state_factory(alive_agents=[])
    ended, winner = RulesValidator.check_game_end_condition(state)
    assert ended and winner == "draw"


def test_game_end_conditions_werewolf_majority(game_state_factory):
    state = game_state_factory(alive_agents=["agent_0", "agent_1"])
    ended, winner = RulesValidator.check_game_end_condition(state)
    assert ended and winner == "werewolves"


def test_game_end_conditions_villagers_win_when_no_wolves(game_state_factory):
    state = game_state_factory(alive_agents=["agent_2", "agent_3", "agent_4"])
    ended, winner = RulesValidator.check_game_end_condition(state)
    assert ended and winner == "villagers"


def test_game_end_conditions_max_rounds(monkeypatch, game_state_factory):
    state = game_state_factory(alive_agents=["agent_0", "agent_4"])
    state.round_number = state.config.max_rounds
    ended, winner = RulesValidator.check_game_end_condition(state)
    assert ended and winner == "werewolves"
