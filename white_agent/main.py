"""White Agent - A2A Server for Werewolf Players using LiteLLM"""

import os
import logging
import json
import tomllib
import time
from typing import Optional, Dict, Any
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCard
from a2a.utils import new_agent_text_message

from white_agent.llm_handler import LLMHandler
from white_agent.prompt_parser import PromptParser
from white_agent.response_formatter import ResponseFormatter

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global LLM handler
llm_handler: Optional[LLMHandler] = None


def init_globals():
    """Initialize global LLM handler."""
    global llm_handler
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_handler = LLMHandler(model=model)
    logger.info(f"Initialized White Agent with LLM model: {model}")


class WerewolfWhiteAgentExecutor(AgentExecutor):
    """Executor for Werewolf White Agent - receives prompts and returns actions."""

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute a task based on the incoming message from Green Agent."""
        global llm_handler

        # Parse the incoming message
        user_message = context.message
        task_data = None

        for part in user_message.parts:
            if hasattr(part, 'root') and hasattr(part.root, 'text'):
                text = part.root.text
            elif hasattr(part, 'text'):
                text = part.text
            else:
                continue

            try:
                task_data = json.loads(text)
                break
            except json.JSONDecodeError:
                continue

        if not task_data:
            error_response = {"error": "Failed to parse task data from Green Agent"}
            response_message = new_agent_text_message(json.dumps(error_response))
            await event_queue.enqueue_event(response_message)
            return

        try:
            task_name = task_data.get("task")
            
            if task_name == "werewolf_action":
                result = await self._handle_werewolf_action(task_data)
            else:
                result = {"error": f"Unknown task: {task_name}"}

            # Send response
            response_message = new_agent_text_message(json.dumps(result))
            await event_queue.enqueue_event(response_message)

        except Exception as e:
            logger.error(f"Error executing task: {e}", exc_info=True)
            error_message = new_agent_text_message(json.dumps({"error": str(e)}))
            await event_queue.enqueue_event(error_message)

    async def _handle_werewolf_action(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle werewolf_action task.
        
        The White Agent is a REACTOR - it only responds to prompts from the Green Agent.
        All context and instructions come from the Green Agent's prompt.
        """
        global llm_handler
        
        # Extract data from task
        game_id = task_data.get("game_id")
        game_state = task_data.get("game_state", {})
        your_role = task_data.get("your_role")
        phase = task_data.get("phase")
        round_number = task_data.get("round", 1)
        alive_agents = task_data.get("alive_agents", [])
        eliminated_agents = task_data.get("eliminated_agents", [])
        prompt = task_data.get("prompt", "")  # Full prompt from Green Agent
        
        # Log input for debugging
        logger.info(f"Received task for game {game_id}, phase {phase}, role {your_role}")
        logger.debug(f"Full prompt: {prompt[:500]}...")
        
        # Use the prompt directly if provided, otherwise construct minimal response
        if not prompt:
            # Fallback: Green Agent should always provide a prompt
            logger.warning("No prompt provided by Green Agent, using fallback")
            prompt = self._create_fallback_prompt(task_data)
        
        # Call LLM with the prompt
        start_time = time.time()
        llm_response = await llm_handler.get_response(prompt)
        response_time = (time.time() - start_time) * 1000
        
        # Store raw LLM text BEFORE formatting (for logging)
        raw_llm_text = llm_response
        
        # Check if fallback was used
        is_fallback = llm_response.startswith("[FALLBACK]")
        if is_fallback:
            logger.warning(f"⚠️  FALLBACK response used (LLM unavailable) - response time: {response_time:.2f}ms")
            logger.warning("   Check: 1) LiteLLM installed? 2) OPENAI_API_KEY set? 3) Model name valid?")
            logger.warning(f"   Fallback response: {llm_response[:300]}...")
        else:
            logger.info(f"✅ REAL LLM response received in {response_time:.2f}ms")
            logger.info(f"   Raw LLM response (first 500 chars): {llm_response[:500]}...")
            if len(llm_response) > 500:
                logger.info(f"   ... (full response length: {len(llm_response)} chars)")
        
        # Parse LLM response into action format
        action_response = ResponseFormatter.format_action_response(
            llm_response=llm_response,
            phase=phase,
            your_role=your_role,
            alive_agents=alive_agents,
            game_state=game_state
        )
        
        # Store raw LLM text in action_response metadata for logging
        # This will be logged by the Green Agent
        if "metadata" not in action_response.get("action", {}):
            action_response["action"]["metadata"] = {}
        action_response["action"]["metadata"]["raw_llm_text"] = raw_llm_text[:1000]  # Store first 1000 chars
        
        return action_response

    def _create_fallback_prompt(self, task_data: Dict[str, Any]) -> str:
        """Create a fallback prompt if Green Agent doesn't provide one."""
        phase = task_data.get("phase", "unknown")
        your_role = task_data.get("your_role", "unknown")
        alive_agents = task_data.get("alive_agents", [])
        
        return f"""You are playing Werewolf. Your role is {your_role}.
Current phase: {phase}
Alive players: {', '.join(alive_agents)}

What action do you take? Respond briefly with your action and reasoning."""

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel a running task."""
        pass


def load_agent_card_toml(agent_name: str = "white_agent_card") -> dict:
    """Load agent card configuration from TOML file."""
    # Look for TOML file in project root
    toml_path = Path(__file__).parent.parent / f"{agent_name}.toml"
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def start_white_agent(agent_name: str = "white_agent_card", host: str = "localhost", port: int = 9002):
    """Start the white agent server."""
    logger.info("Starting Werewolf White Agent...")

    # Initialize globals
    init_globals()

    # Load agent card from TOML
    agent_card_dict = load_agent_card_toml(agent_name)

    # Set URL from AGENT_URL environment variable (set by AgentBeats platform)
    agent_url = os.getenv("AGENT_URL") or os.getenv("BASE_URL") or f"http://{host}:{port}"
    agent_card_dict["url"] = agent_url

    logger.info(f"White Agent URL: {agent_card_dict['url']}")

    # Create request handler with executor
    request_handler = DefaultRequestHandler(
        agent_executor=WerewolfWhiteAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    # Create A2A application
    agent_card = AgentCard(**agent_card_dict)
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # Run the server
    uvicorn.run(a2a_app.build(), host=host, port=port)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "9002"))
    start_white_agent(host=host, port=port)

