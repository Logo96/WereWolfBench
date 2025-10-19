"""End-to-end test exercising the live HTTP path with dummy agents."""

import asyncio
import socket

import pytest

from app.logging.storage import GameLogger
from app.orchestrator import GameOrchestrator
from app.testing.dummy_agents import DummyAgentServer
from app.types.game import GameConfig, GamePhase, GameStatus


def _can_bind_localhost() -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.close()
        return True
    except OSError:
        return False


CAN_BIND = _can_bind_localhost()


def _reserve_ports(host: str, count: int) -> list[int]:
    """Reserve a list of free TCP ports by binding then releasing."""
    sockets: list[socket.socket] = []
    ports: list[int] = []

    try:
        for _ in range(count):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((host, 0))
            sockets.append(sock)
            ports.append(sock.getsockname()[1])
    finally:
        for sock in sockets:
            sock.close()

    return ports


pytestmark = pytest.mark.skipif(
    not CAN_BIND,
    reason="Local TCP binding is not permitted in this environment",
)


@pytest.mark.asyncio
async def test_full_http_game_flow(tmp_path):
    """Spin up dummy agents and ensure a full game completes with logs."""
    host = "127.0.0.1"
    ports = _reserve_ports(host, 6)
    servers = [
        DummyAgentServer(agent_name=f"agent_{idx}", host=host, port=ports[idx])
        for idx in range(6)
    ]

    for server in servers:
        await server.start()

    storage = GameLogger(log_dir=str(tmp_path / "logs"))
    orchestrator = GameOrchestrator(storage)

    try:
        agent_urls = [server.url for server in servers]
        config = GameConfig(num_werewolves=2, has_seer=True, has_doctor=True)
        game_id = await orchestrator.start_game(agent_urls, config)

        async def wait_for_completion():
            while True:
                game_state = storage.get_game(game_id)
                if game_state and game_state.status == GameStatus.COMPLETED:
                    return game_state
                await asyncio.sleep(0.1)

        final_state = await asyncio.wait_for(wait_for_completion(), timeout=15.0)

        assert final_state.phase == GamePhase.GAME_OVER
        assert final_state.winner in {"villagers", "werewolves"}

        log_data = storage.load_game_from_log(game_id)
        assert log_data is not None
        events = log_data["events"]
        event_types = {event["event"] for event in events}
        assert {"game_created", "game_started", "action", "game_ended"}.issubset(event_types)

    finally:
        await orchestrator.close()
        await asyncio.gather(*(server.close() for server in servers))
