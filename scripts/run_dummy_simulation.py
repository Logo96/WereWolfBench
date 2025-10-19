#!/usr/bin/env python3
"""Launch dummy agents and optionally drive a full Werewolf game against the live orchestrator."""

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.testing.dummy_agents import DummyAgentServer


async def _send_jsonrpc(
    client: httpx.AsyncClient,
    url: str,
    task: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send a JSON-RPC message/send request to the orchestrator."""
    message = {
        "messageId": str(uuid4()),
        "role": "user",
        "parts": [
            {
                "kind": "text",
                "text": json.dumps({"task": task, "parameters": parameters or {}}),
            }
        ],
    }
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {"message": message},
    }

    response = await client.post(url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"JSON-RPC error: {data['error']}")

    parts = data.get("result", {}).get("parts", [])
    text_parts = [part.get("text") for part in parts if part.get("kind") == "text"]
    if not text_parts:
        raise RuntimeError("Unexpected response format (no text parts)")

    return json.loads(text_parts[0])


async def run_simulation(args: argparse.Namespace) -> None:
    base_port = args.port_start
    servers: List[DummyAgentServer] = [
        DummyAgentServer(agent_name=f"agent_{idx}", host=args.host, port=base_port + idx)
        for idx in range(args.num_agents)
    ]

    async def shutdown(*_signals: object) -> None:
        await asyncio.gather(*(server.close() for server in servers), return_exceptions=True)
        raise SystemExit(0)

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, sig_name):
            sig = getattr(signal, sig_name)
            try:
                loop.add_signal_handler(
                    sig, lambda s=sig: asyncio.create_task(shutdown(s))
                )
            except NotImplementedError:
                pass

    try:
        await asyncio.gather(*(server.start() for server in servers))
        print("Dummy agents started:")
        for server in servers:
            print(f"  {server.agent_name} -> {server.url}")

        if not args.start_game:
            print("Waiting for Ctrl+C. Use these URLs in the green agent configuration.")
            while True:
                await asyncio.sleep(3600)

        config = {
            "num_werewolves": args.num_werewolves,
            "has_seer": not args.no_seer,
            "has_doctor": not args.no_doctor,
            "max_rounds": args.max_rounds,
        }

        async with httpx.AsyncClient() as client:
            start_result = await _send_jsonrpc(
                client,
                args.orchestrator_url,
                "start_game",
                {"agent_urls": [server.url for server in servers], "config": config},
            )

            game_id = start_result.get("game_id")
            if not game_id:
                raise RuntimeError(f"Unexpected start_game response: {start_result}")

            print(f"Game started: {game_id}")

            completed = False
            while not completed:
                status_result = await _send_jsonrpc(
                    client,
                    args.orchestrator_url,
                    "get_game_status",
                    {"game_id": game_id},
                )
                status = status_result.get("status")
                phase = status_result.get("phase")
                round_number = status_result.get("round_number")
                alive = status_result.get("alive_agents", [])

                print(
                    f"[round {round_number}] status={status} phase={phase} "
                    f"alive={len(alive)}"
                )

                if status == "completed":
                    completed = True
                    print(f"Winner: {status_result.get('winner')}")
                    log_path = args.log_dir or "game_logs"
                    print(
                        f"Check logs under {log_path}/game_{game_id}.jsonl for full history."
                    )
                else:
                    await asyncio.sleep(args.poll_interval)

    finally:
        await asyncio.gather(*(server.close() for server in servers), return_exceptions=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run dummy agents and optionally drive a full Werewolf game."
    )
    parser.add_argument("--num-agents", type=int, default=6, help="Number of dummy agents")
    parser.add_argument("--num-werewolves", type=int, default=2, help="Werewolves in the game")
    parser.add_argument("--no-seer", action="store_true", help="Disable the seer role")
    parser.add_argument("--no-doctor", action="store_true", help="Disable the doctor role")
    parser.add_argument("--max-rounds", type=int, default=20, help="Maximum rounds before forced end")
    parser.add_argument("--host", default="127.0.0.1", help="Host for dummy agents")
    parser.add_argument("--port-start", type=int, default=9500, help="Starting port for agents")
    parser.add_argument(
        "--orchestrator-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running green agent (JSON-RPC endpoint)",
    )
    parser.add_argument(
        "--start-game",
        action="store_true",
        help="Automatically start a game against the orchestrator once agents are ready",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between status polls when monitoring the game",
    )
    parser.add_argument(
        "--log-dir",
        default="game_logs",
        help="Directory where the orchestrator writes JSONL logs",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_simulation(args))


if __name__ == "__main__":
    main()
