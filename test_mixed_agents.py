#!/usr/bin/env python3
"""
Test script for mixed White Agents (2 real LLM-powered + 6 dummy agents).

This script:
1. Starts the Green Agent (orchestrator)
2. Starts 2 real White Agents (LLM-powered via LiteLLM)
3. Starts 6 dummy agents (deterministic responses)
4. Runs a complete game
5. Shows results and logs
"""

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import httpx

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.testing.dummy_agents import DummyAgentServer


# Port assignments
GREEN_AGENT_PORT = 8080
WHITE_AGENT_START_PORT = 9002
DUMMY_AGENT_START_PORT = 9500


class AgentProcess:
    """Manages a subprocess for an agent."""
    
    def __init__(self, name: str, command: List[str], env: dict = None):
        self.name = name
        self.command = command
        self.env = env or {}
        self.process: Optional[subprocess.Popen] = None
    
    def start(self, show_output: bool = False):
        """Start the agent process."""
        full_env = os.environ.copy()
        full_env.update(self.env)
        
        print(f"Starting {self.name}...")
        if show_output:
            # Show output in terminal (for Green Agent debugging)
            self.process = subprocess.Popen(
                self.command,
                env=full_env,
                text=True
            )
        else:
            # Capture output (for White Agents and Dummy Agents)
            self.process = subprocess.Popen(
                self.command,
                env=full_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
        print(f"  {self.name} started (PID: {self.process.pid})")
    
    def stop(self):
        """Stop the agent process."""
        if self.process:
            print(f"Stopping {self.name}...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            print(f"  {self.name} stopped")


async def check_agent_health(url: str, timeout: float = 5.0) -> bool:
    """Check if an agent is responding."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try agent-card.json first (for A2A agents)
            try:
                response = await client.get(f"{url}/.well-known/agent-card.json")
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            
            # Fallback to root endpoint (for dummy agents)
            response = await client.get(f"{url}/")
            return response.status_code == 200
    except Exception:
        return False


async def wait_for_agents(agent_urls: List[str], max_wait: int = 30):
    """Wait for all agents to be ready."""
    print("\nWaiting for agents to be ready...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        ready = []
        for url in agent_urls:
            is_ready = await check_agent_health(url)
            ready.append(is_ready)
            if is_ready:
                print(f"  ✓ {url}")
            else:
                print(f"  ✗ {url} (waiting...)")
        
        if all(ready):
            print("\nAll agents are ready!")
            return True
        
        await asyncio.sleep(1)
    
    print(f"\nTimeout: Some agents did not become ready within {max_wait} seconds")
    return False


async def send_jsonrpc(
    client: httpx.AsyncClient,
    url: str,
    task: str,
    parameters: dict = None
) -> dict:
    """Send a JSON-RPC message/send request."""
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
    
    response = await client.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    
    if "error" in data:
        error_info = data['error']
        error_msg = f"JSON-RPC error: {error_info}"
        raise RuntimeError(error_msg)
    
    parts = data.get("result", {}).get("parts", [])
    text_parts = [part.get("text") for part in parts if part.get("kind") == "text"]
    if not text_parts:
        raise RuntimeError("Unexpected response format (no text parts)")
    
    return json.loads(text_parts[0])


async def run_test(args: argparse.Namespace):
    """Run the mixed agent test."""
    processes: List[AgentProcess] = []
    dummy_servers: List[DummyAgentServer] = []
    
    # Track all agent URLs
    agent_urls: List[str] = []
    
    try:
        # 1. Start Green Agent
        print("=" * 60)
        print("Starting Green Agent (Orchestrator)")
        print("=" * 60)
        green_agent = AgentProcess(
            name="Green Agent",
            command=[sys.executable, "-m", "app.main"],
            env={
                "HOST": "0.0.0.0",
                "PORT": str(GREEN_AGENT_PORT),
            }
        )
        green_agent.start(show_output=True)  # Show Green Agent output in terminal
        processes.append(green_agent)
        green_url = f"http://127.0.0.1:{GREEN_AGENT_PORT}"
        
        # Wait a bit for Green Agent to start
        await asyncio.sleep(2)
        
        # 2. Start 2 Real White Agents
        print("\n" + "=" * 60)
        print("Starting 2 Real White Agents (LLM-powered)")
        print("=" * 60)
        
        if not os.getenv("OPENAI_API_KEY"):
            print("\n⚠️  WARNING: OPENAI_API_KEY not set!")
            print("   White Agents will use fallback responses (no real LLM calls)")
            print("   Set OPENAI_API_KEY to use real LLM:\n")
            print("   export OPENAI_API_KEY='your-key-here'\n")
        
        for i in range(2):
            port = WHITE_AGENT_START_PORT + i
            white_agent = AgentProcess(
                name=f"White Agent {i+1}",
                command=[sys.executable, "-m", "white_agent.main"],
                env={
                    "HOST": "0.0.0.0",
                    "PORT": str(port),
                    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                    "LLM_MODEL": args.llm_model,
                }
            )
            white_agent.start(show_output=args.show_agent_output)
            processes.append(white_agent)
            agent_urls.append(f"http://127.0.0.1:{port}")
        
        # 3. Start 6 Dummy Agents
        print("\n" + "=" * 60)
        print("Starting 6 Dummy Agents")
        print("=" * 60)
        
        for i in range(6):
            port = DUMMY_AGENT_START_PORT + i
            dummy_server = DummyAgentServer(
                agent_name=f"dummy_agent_{i}",
                host="127.0.0.1",
                port=port
            )
            dummy_servers.append(dummy_server)
            agent_urls.append(dummy_server.url)
        
        # Start dummy servers
        await asyncio.gather(*(server.start() for server in dummy_servers))
        print(f"Started {len(dummy_servers)} dummy agents")
        
        # 4. Wait for all agents to be ready
        print("\n" + "=" * 60)
        print("Waiting for Agents")
        print("=" * 60)
        
        if not await wait_for_agents([green_url] + agent_urls, max_wait=30):
            print("\n❌ Some agents failed to start. Check logs above.")
            return
        
        # 5. Start the game
        print("\n" + "=" * 60)
        print("Starting Game")
        print("=" * 60)
        
        game_config = {
            "num_werewolves": 2,
            "has_seer": True,
            "has_doctor": True,
            "has_hunter": False,
            "has_witch": False,
            "max_rounds": 2,  # Cost-saving limit
        }
        
        async with httpx.AsyncClient() as client:
            print(f"Starting game with {len(agent_urls)} agents...")
            print(f"  - 2 Real White Agents (LLM-powered)")
            print(f"  - 6 Dummy Agents")
            print(f"\nConfig: {json.dumps(game_config, indent=2)}")
            
            try:
                start_result = await send_jsonrpc(
                    client,
                    green_url,
                    "start_game",
                    {
                        "agent_urls": agent_urls,
                        "config": game_config
                    }
                )
            except RuntimeError as e:
                print(f"\n❌ Failed to start game: {e}")
                print(f"   Check the Green Agent terminal for detailed error logs.")
                return
            
            game_id = start_result.get("game_id")
            if not game_id:
                print(f"\n⚠️  Unexpected start_game response: {start_result}")
                return
            
            print(f"\n✅ Game started! Game ID: {game_id}")
            
            # 6. Monitor game progress
            print("\n" + "=" * 60)
            print("Game Progress")
            print("=" * 60)
            
            completed = False
            last_status = None
            
            while not completed:
                try:
                    status_result = await send_jsonrpc(
                        client,
                        green_url,
                        "get_game_status",
                        {"game_id": game_id}
                    )
                except Exception as e:
                    print(f"\n⚠️  Error getting game status: {e}")
                    await asyncio.sleep(args.poll_interval)
                    continue
                
                status = status_result.get("status")
                phase = status_result.get("phase")
                round_number = status_result.get("round_number")
                alive = status_result.get("alive_agents", [])
                
                # Only print when status changes
                current_status = f"{status}:{phase}:{round_number}"
                if current_status != last_status:
                    print(
                        f"[Round {round_number}] Status: {status} | "
                        f"Phase: {phase} | Alive: {len(alive)}"
                    )
                    last_status = current_status
                
                if status == "completed":
                    completed = True
                    winner = status_result.get("winner")
                    print(f"\n🎉 Game Completed!")
                    print(f"   Winner: {winner}")
                    print(f"   Total Rounds: {round_number}")
                    print(f"   Surviving Agents: {len(alive)}")
                    
                    # Show log file location
                    log_file = f"game_logs/game_{game_id}.jsonl"
                    print(f"\n📋 Game log: {log_file}")
                    
                    # Show some stats
                    if Path(log_file).exists():
                        with open(log_file) as f:
                            events = [json.loads(line) for line in f if line.strip()]
                        
                        prompts = sum(1 for e in events if e.get("event") == "agent_prompt")
                        responses = sum(1 for e in events if e.get("event") == "agent_response")
                        actions = sum(1 for e in events if e.get("event") == "action")
                        errors = sum(1 for e in events if e.get("event") == "agent_error")
                        
                        print(f"\n📊 Game Statistics:")
                        print(f"   Prompts sent: {prompts}")
                        print(f"   Responses received: {responses}")
                        print(f"   Actions processed: {actions}")
                        print(f"   Errors: {errors}")
                        
                        # Show which agents were real vs dummy
                        print(f"\n🤖 Agent Types:")
                        print(f"   Real White Agents (LLM): agent_0, agent_1")
                        print(f"   Dummy Agents: agent_2 through agent_7")
                else:
                    await asyncio.sleep(args.poll_interval)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        print("\n" + "=" * 60)
        print("Cleaning Up")
        print("=" * 60)
        
        # Stop dummy servers
        if dummy_servers:
            await asyncio.gather(
                *(server.close() for server in dummy_servers),
                return_exceptions=True
            )
        
        # Stop processes
        for process in processes:
            process.stop()
        
        print("\n✅ Cleanup complete")


def main():
    parser = argparse.ArgumentParser(
        description="Test Werewolf game with 2 real White Agents + 6 dummy agents"
    )
    parser.add_argument(
        "--llm-model",
        default="gpt-4o-mini",
        help="LLM model to use for White Agents (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between status polls (default: 2.0)"
    )
    parser.add_argument(
        "--show-agent-output",
        action="store_true",
        help="Show output from all agents (not just Green Agent)"
    )
    
    args = parser.parse_args()
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Note: OPENAI_API_KEY not set. White Agents will use fallback responses.")
        print("   Set it to use real LLM: export OPENAI_API_KEY='your-key'\n")
    
    asyncio.run(run_test(args))


if __name__ == "__main__":
    main()

