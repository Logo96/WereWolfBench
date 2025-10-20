"""Async integration test covering the orchestrator loop and logging."""

import asyncio

import pytest

from app.game.state import StateManager
from app.orchestrator import GameOrchestrator
from app.logging.storage import GameLogger
from app.types.agent import ActionType, WerewolfAction
from app.types.game import GameConfig, GamePhase, GameStatus


@pytest.mark.asyncio
async def test_orchestrator_runs_full_round_and_logs(tmp_path, monkeypatch):
    """Run a full day cycle and assert log output captures actions."""

    # Force deterministic role assignment for reproducibility
    def fake_assign_roles(agent_ids, config_dict):
        roles = {agent_ids[0]: "werewolf"}
        for agent_id in agent_ids[1:]:
            roles[agent_id] = "villager"
        return roles

    monkeypatch.setattr(
        StateManager,
        "assign_roles",
        staticmethod(fake_assign_roles),
    )

    log_dir = tmp_path / "logs"
    storage = GameLogger(log_dir=str(log_dir))
    orchestrator = GameOrchestrator(storage)

    async def fake_request_agent_action(self, game_id, agent, game_state):
        """Provide deterministic actions for each phase."""
        if game_state.phase == GamePhase.DAY_DISCUSSION:
            action_type = ActionType.DISCUSS
            target = None
            reasoning = f"{agent.agent_id} shares thoughts"
        elif game_state.phase == GamePhase.DAY_VOTING:
            action_type = ActionType.VOTE
            target = "agent_0" if agent.agent_id != "agent_0" else "agent_1"
            reasoning = f"{agent.agent_id} votes {target}"
        else:
            action_type = ActionType.PASS
            target = None
            reasoning = f"{agent.agent_id} passes"

        action = WerewolfAction(
            agent_id=agent.agent_id,
            action_type=action_type,
            target_agent_id=target,
            reasoning=reasoning,
            confidence=0.95,
        )
        self._process_action(game_id, action)
        return action

    monkeypatch.setattr(
        GameOrchestrator,
        "_request_agent_action",
        fake_request_agent_action,
    )

    agent_urls = [f"http://agent{i}.test" for i in range(8)]
    config = GameConfig(
        num_werewolves=2,
        has_seer=True,
        has_doctor=True,
        has_hunter=True,
        has_witch=True,
        max_rounds=5,
    )

    try:
        game_id = await orchestrator.start_game(agent_urls, config)

        async def wait_for_completion():
            while True:
                state = storage.get_game(game_id)
                if state and state.status == GameStatus.COMPLETED:
                    return state
                await asyncio.sleep(0.05)

        final_state = await asyncio.wait_for(wait_for_completion(), timeout=2.0)

        assert final_state.winner == "villagers"
        assert final_state.phase == GamePhase.GAME_OVER

        events_payload = storage.load_game_from_log(game_id)
        assert events_payload is not None
        events = events_payload["events"]
        event_kinds = {event["event"] for event in events}

        assert {"game_created", "game_started", "action", "game_ended"}.issubset(event_kinds)

        action_events = [event for event in events if event["event"] == "action"]
        assert action_events, "Expected logged actions in game history"

        # Ensure votes were recorded, showing the orchestrator ran the voting phase.
        vote_targets = {
            event["target"]
            for event in action_events
            if event["action_type"] == ActionType.VOTE.value
        }
        assert "agent_0" in vote_targets

    finally:
        await orchestrator.close()
