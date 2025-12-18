#!/usr/bin/env python3
"""
Run a full Werewolf game with all real LLM-powered White Agents.

This script:
1. Starts the Green Agent (orchestrator)
2. Starts 8 real White Agents (all LLM-powered via LiteLLM)
3. Runs a complete game with high max_rounds (no artificial limit)
4. Stores metrics to a JSON file
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


# Port assignments
GREEN_AGENT_PORT = 8080
WHITE_AGENT_START_PORT = 9002


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
            # Show output in terminal (for debugging)
            self.process = subprocess.Popen(
                self.command,
                env=full_env,
                text=True
            )
        else:
            # Capture output
            self.process = subprocess.Popen(
                self.command,
                env=full_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
        print(f"  {self.name} started (PID: {self.process.pid})")
    
    def read_output(self) -> tuple[str, str]:
        """Read captured stdout and stderr (only if process has terminated)."""
        stdout, stderr = "", ""
        if self.process:
            # Check if process is still running
            if self.process.poll() is None:
                # Process is still running - can't read output without blocking
                # Return empty strings to avoid hanging
                return "", ""
            
            # Process has terminated - safe to read output
            try:
                if self.process.stdout:
                    stdout = self.process.stdout.read()
                if self.process.stderr:
                    stderr = self.process.stderr.read()
            except Exception:
                # Output already read or pipe closed
                pass
        return stdout, stderr
    
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
            
            # Fallback to root endpoint
            response = await client.get(f"{url}/")
            return response.status_code == 200
    except Exception:
        return False


async def wait_for_agents(agent_urls: List[str], max_wait: int = 60):
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
    
    # High timeout for LLM calls - can take several minutes with network latency
    response = await client.post(url, json=payload, timeout=300.0)  # 5 minutes
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


def save_metrics(game_id: str, metrics: dict, output_dir: str = "metrics", subfolder: str = "baseline"):
    """Save game metrics to a JSON file.
    
    Note: This function saves metrics with the format {game_id}_metrics.json
    to match the format used by extract_game_metrics.py (which removes 'game_' prefix from log filenames).
    """
    output_path = Path(output_dir) / subfolder
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Remove 'game_' prefix if present to match extract_game_metrics.py format
    metrics_name = game_id.replace("game_", "") if game_id.startswith("game_") else game_id
    metrics_file = output_path / f"{metrics_name}_metrics.json"
    
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Metrics saved to: {metrics_file}")
    return metrics_file


async def run_full_game(args: argparse.Namespace):
    """Run a full game with all real agents."""
    processes: List[AgentProcess] = []
    
    # Track all agent URLs
    agent_urls: List[str] = []
    
    try:
        # 1. Start Green Agent
        print("=" * 70)
        print("Starting Green Agent (Orchestrator)")
        print("=" * 70)
        green_agent = AgentProcess(
            name="Green Agent",
            command=[sys.executable, "-m", "app.main"],
            env={
                "HOST": "0.0.0.0",
                "PORT": str(GREEN_AGENT_PORT),
                "GAME_NAME": args.name if args.name else "",
            }
        )
        green_agent.start(show_output=args.show_green_output)
        processes.append(green_agent)
        green_url = f"http://127.0.0.1:{GREEN_AGENT_PORT}"
        
        # Wait a bit for Green Agent to start
        await asyncio.sleep(2)
        
        # 2. Start 8 Real White Agents (all using Gemini 2.5 Flash)
        print("\n" + "=" * 70)
        print("Starting 8 Real White Agents (LLM-powered)")
        print("=" * 70)
        
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            print("\n⚠️  WARNING: GEMINI_API_KEY or GOOGLE_API_KEY not set!")
            print("   White Agents will use fallback responses (no real LLM calls)")
            print("   Set GEMINI_API_KEY to use real LLM:\n")
            print("   export GEMINI_API_KEY='your-key-here'\n")
            print("   Or use: export GOOGLE_API_KEY='your-key-here'\n")
        
        # Model assignments based on --model argument
        FLASH_MODEL = "gemini/gemini-2.0-flash"
        FLASHLITE_MODEL = "gemini/gemini-2.0-flash-lite"
        
        # Determine model assignment based on --model argument
        if args.model == "flashonly":
            model_assignment = [FLASH_MODEL] * 9
            model_description = "All agents: Gemini 2.0 Flash"
        elif args.model == "flashlite":
            model_assignment = [FLASHLITE_MODEL] * 9
            model_description = "All agents: Gemini 2.0 Flash Lite"
        elif args.model == "mixed":
            model_assignment = [FLASH_MODEL] * 4 + [FLASHLITE_MODEL] * 5
            model_description = "Agents 1-4: Gemini 2.0 Flash, Agents 5-9: Gemini 2.0 Flash Lite"
        else:
            # Default: use LLM_MODEL env var or fallback to Gemini 2.5 Flash
            default_model = os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")
            model_assignment = [default_model] * 9
            model_description = f"All agents: {default_model}"
        
        for i in range(9):
            port = WHITE_AGENT_START_PORT + i
            model = model_assignment[i]
            agent_name = f"White Agent {i+1} ({model})"
            
            # Pass both GEMINI_API_KEY and GOOGLE_API_KEY for compatibility
            gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
            white_agent = AgentProcess(
                name=agent_name,
                command=[sys.executable, "-m", "white_agent.main"],
                env={
                    "HOST": "0.0.0.0",
                    "PORT": str(port),
                    "GEMINI_API_KEY": gemini_key,
                    "GOOGLE_API_KEY": gemini_key,  # Also set for LiteLLM compatibility
                    "LLM_MODEL": model,
                }
            )
            white_agent.start(show_output=args.show_agent_output)
            processes.append(white_agent)
            agent_urls.append(f"http://127.0.0.1:{port}")
        
        # 3. Wait for all agents to be ready
        print("\n" + "=" * 70)
        print("Waiting for Agents")
        print("=" * 70)
        
        if not await wait_for_agents([green_url] + agent_urls, max_wait=60):
            print("\n❌ Some agents failed to start. Check logs above.")
            return
        
        # 4. Start the game
        print("\n" + "=" * 70)
        print("Starting Game")
        print("=" * 70)
        
        # No max_rounds limit - game will run to natural completion
        game_config = {
            "num_werewolves": 3,
            "has_seer": True,
            "has_doctor": True,
            "has_hunter": True,
            "has_witch": True,
            "max_rounds": None,  # No limit - game runs until werewolves or villagers win
            "discussion_time_limit": 300,
            "voting_time_limit": 60,
        }
        
        async with httpx.AsyncClient() as client:
            print(f"Starting game with {len(agent_urls)} real White Agents...")
            print(f"  - {model_description}")
            print(f"\nConfig: {json.dumps(game_config, indent=2)}")
            print(f"\n✓ No max_rounds limit - game will run to natural completion\n")
            
            # Create model mapping for tracking
            agent_models = {}
            for i, url in enumerate(agent_urls):
                model = model_assignment[i]
                agent_models[url] = model
            
            try:
                start_result = await send_jsonrpc(
                    client,
                    green_url,
                    "start_game",
                    {
                        "agent_urls": agent_urls,
                        "config": game_config,
                        "agent_models": agent_models  # Pass model mapping
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
            
            # 5. Monitor game progress
            print("\n" + "=" * 70)
            print("Game Progress")
            print("=" * 70)
            
            completed = False
            last_status = None
            start_time = time.time()
            
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
                winner = status_result.get("winner")
                
                # Only print when status changes
                current_status = f"{status}:{phase}:{round_number}"
                if current_status != last_status:
                    elapsed = time.time() - start_time
                    print(
                        f"[Round {round_number}] Status: {status} | "
                        f"Phase: {phase} | Alive: {len(alive)} | "
                        f"Elapsed: {elapsed:.1f}s"
                    )
                    last_status = current_status
                
                if status == "completed":
                    completed = True
                    elapsed = time.time() - start_time
                    print(f"\n🎉 Game Completed!")
                    print(f"   Winner: {winner if winner else 'None (max rounds reached)'}")
                    print(f"   Total Rounds: {round_number}")
                    print(f"   Surviving Agents: {len(alive)}")
                    print(f"   Total Time: {elapsed:.1f}s")
                    
                    # 6. Extract and save metrics
                    print("\n" + "=" * 70)
                    print("Extracting Metrics")
                    print("=" * 70)
                    
                    # Use custom name if provided, otherwise use game_id
                    log_name = args.name if args.name else game_id
                    log_file = Path(f"game_logs/baseline/game_{log_name}.jsonl")
                    if log_file.exists():
                        print(f"📋 Game log: {log_file}")
                        
                        try:
                            from extract_game_metrics import extract_game_metrics
                            metrics = extract_game_metrics(str(log_file))
                            
                            # Save metrics to file (use custom name if provided)
                            metrics_name = args.name if args.name else game_id
                            metrics_file = save_metrics(metrics_name, metrics, args.metrics_dir)
                            
                            # Print summary
                            print("\n" + "=" * 70)
                            print("Metrics Summary")
                            print("=" * 70)
                            print(f"Winner: {metrics.get('winner', 'N/A')}")
                            print(f"Total Rounds: {metrics.get('total_rounds', 'N/A')}")
                            print(f"Final Alive: {len(metrics.get('final_alive', []))}")
                            print(f"Final Eliminated: {len(metrics.get('final_eliminated', []))}")
                            print(f"\nAction Counts:")
                            for action_type, count in metrics.get('action_counts', {}).items():
                                print(f"  {action_type}: {count}")
                            print(f"\nDiscussion Actions: {metrics.get('discussion_actions_count', 0)}")
                            print(f"Investigation Actions: {metrics.get('investigation_actions_count', 0)}")
                            print(f"\nRule Compliance: {metrics.get('rule_compliance_percentage', 0):.1f}%")
                            print(f"  Valid Actions: {metrics.get('valid_actions', 0)}/{metrics.get('total_actions', 0)}")
                            
                            # Show White Agent logs if not already shown
                            # Note: We skip reading output here since processes are still running
                            # Output will be lost, but prevents blocking. Use --show-agent-output for real-time logs.
                            if not args.show_agent_output:
                                print("\n" + "=" * 70)
                                print("White Agent Logs")
                                print("=" * 70)
                                print("(Output not captured - processes still running)")
                                print("(Run with --show-agent-output to see logs in real-time)")
                                print("(Check individual agent logs in their respective log files)")
                            
                        except Exception as e:
                            print(f"\n⚠️  Failed to extract metrics: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print(f"\n⚠️  Game log not found: {log_file}")
                    
                    break
                
                await asyncio.sleep(args.poll_interval)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    finally:
        # Cleanup: Stop all processes
        print("\n" + "=" * 70)
        print("Cleaning Up")
        print("=" * 70)
        for process in reversed(processes):
            process.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Run a full Werewolf game with all real LLM-powered agents"
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="[DEPRECATED] Model assignment is now fixed: all agents use Gemini 2.5 Flash"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Interval between status checks in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--show-agent-output",
        action="store_true",
        help="Show White Agent output in terminal (verbose)"
    )
    parser.add_argument(
        "--show-green-output",
        action="store_true",
        help="Show Green Agent output in terminal (verbose)"
    )
    parser.add_argument(
        "--metrics-dir",
        type=str,
        default="metrics",
        help="Base directory to save metrics JSON files (default: metrics, saves to metrics/baseline/)"
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Custom name for log and metrics files (e.g., 'test1' creates game_test1.jsonl and game_test1_metrics.json)"
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["flashonly", "flashlite", "mixed"],
        default=None,
        help="Model assignment: 'flashonly' (all use gemini-2.0-flash), 'flashlite' (all use gemini-2.0-flash-lite), 'mixed' (agents 1-4 use flash, 5-9 use flashlite). If not specified, uses LLM_MODEL env var or defaults to gemini-2.5-flash."
    )
    
    args = parser.parse_args()
    
    # Run the game
    asyncio.run(run_full_game(args))


if __name__ == "__main__":
    main()

