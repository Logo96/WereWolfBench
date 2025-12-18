"""LLM Handler using direct Gemini API calls for White Agent responses with tool calling support.

This module uses direct httpx calls to Gemini API instead of litellm to avoid slow import times.
Litellm takes 15-20 minutes to import on Cloud Run, which causes subprocess timeouts.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

# Gemini API endpoint
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class ToolCallTracker:
    """Tracks tool calls made during an LLM interaction for logging purposes."""

    def __init__(self):
        self.tool_calls: List[Dict[str, Any]] = []
        self.total_iterations = 0

    def record_tool_call(self, tool_name: str, tool_args: Dict[str, Any], tool_result: str, iteration: int):
        """Record a tool call and its result."""
        self.tool_calls.append({
            "timestamp": datetime.utcnow().isoformat(),
            "iteration": iteration,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_result_length": len(tool_result),
            "tool_result_preview": tool_result[:500] if len(tool_result) > 500 else tool_result
        })

    def to_dict(self) -> Dict[str, Any]:
        """Return tracking data as dictionary for logging."""
        return {
            "tool_calls_count": len(self.tool_calls),
            "total_iterations": self.total_iterations,
            "tool_calls": self.tool_calls
        }


# Tool definition for Gemini API format
MEMORY_TOOL_GEMINI = {
    "function_declarations": [{
        "name": "get_game_memory",
        "description": "Retrieve the game history including all discussions, votes, and eliminations from previous rounds. Call this to review what happened earlier in the game before making important decisions.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_rounds": {
                    "type": "integer",
                    "description": "Optional: Limit to last N rounds. If not provided, returns full history."
                }
            },
            "required": []
        }
    }]
}


class LLMHandler:
    """Handles LLM interactions for the White Agent using direct Gemini API calls."""

    # System prompt
    SYSTEM_PROMPT = """You are an AI playing a game of Werewolf.

IMPORTANT: Follow the response format specified in the user's prompt exactly.
The user prompt will tell you the exact format to use (ACTION, TARGET, REASONING, etc.).

CRITICAL - TOOL CALLING BEHAVIOR:
When you have access to tools (like get_game_memory):
1. You may request a tool call to gather information
2. The system will execute the tool and return results to you in the conversation
3. After receiving tool results, you MUST provide your final action response
4. The tool call is for information gathering, NOT your final answer
5. Your final response must include ACTION, targets, content, and reasoning as specified

Example correct flow:
  You → Request get_game_memory tool
  System → Executes tool → Returns game history to you
  You → Review history → Provide complete ACTION response with reasoning

NEVER stop after just calling a tool. ALWAYS provide your complete action response after reviewing tool results.

Keep your responses concise (under 100 words) and strategic."""

    def __init__(
        self,
        model: str = "gemini/gemini-2.5-flash",
        temperature: float = 1,
        max_tokens: int = 4000
    ):
        """
        Initialize the LLM handler.

        Args:
            model: Model name (e.g., "gemini/gemini-2.5-flash" or "gemini-2.5-flash")
            temperature: Response temperature (0.0-2.0 for Gemini)
            max_tokens: Maximum tokens in response
        """
        # Extract model name (remove "gemini/" prefix if present)
        if model.startswith("gemini/"):
            self.model = model[7:]  # Remove "gemini/" prefix
        else:
            self.model = model

        self.temperature = temperature
        self.max_tokens = max_tokens

        # Get API key
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

        logger.info(f"LLM Handler initialized with model: {self.model}")
        logger.info(f"   Using direct Gemini API (no litellm)")
        logger.info(f"   API Key present: {bool(self.api_key)}")
        if self.api_key:
            logger.info(f"   API Key length: {len(self.api_key)}")

    async def get_response(
        self,
        prompt: str,
        memory_data: Optional[Dict[str, Any]] = None
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """
        Get a response from the LLM with tool calling support and retry logic.

        Args:
            prompt: The prompt from the Green Agent
            memory_data: Serialized game memory data for tool access (optional)

        Returns:
            Tuple of (response_text, tool_call_info)
        """
        tool_tracker = ToolCallTracker()

        if not self.api_key:
            logger.error("GEMINI_API_KEY or GOOGLE_API_KEY not set - using fallback response")
            fallback_resp = self._fallback_response(prompt)
            return f"[FALLBACK]{fallback_resp}", None

        # Build conversation contents
        contents = [
            {"role": "user", "parts": [{"text": self.SYSTEM_PROMPT + "\n\n" + prompt}]}
        ]

        # Prepare tools if memory data is available
        tools = [MEMORY_TOOL_GEMINI] if memory_data else None

        logger.info(f"CONVERSATION INITIALIZED:")
        logger.info(f"   System prompt: {len(self.SYSTEM_PROMPT)} chars")
        logger.info(f"   User prompt: {len(prompt)} chars")
        logger.info(f"   Tools available: {bool(tools)}")

        # Retry logic
        max_retries = 29
        retry_delay = 30
        max_tool_iterations = 3

        for attempt in range(max_retries + 1):
            try:
                tool_iteration = 0
                while tool_iteration < max_tool_iterations:
                    tool_iteration += 1

                    logger.info(f"CALLING LLM (iteration {tool_iteration}):")
                    logger.info(f"   Model: {self.model}")
                    logger.info(f"   Tools: {'enabled' if tools else 'disabled'}")
                    logger.info(f"   Conversation history: {len(contents)} messages")

                    # Make API call
                    response_data = await self._call_gemini_api(contents, tools)

                    if "error" in response_data:
                        error = response_data["error"]
                        error_code = error.get("code", 0)
                        error_message = error.get("message", "Unknown error")

                        if error_code == 429:
                            raise Exception(f"Rate limit error: {error_message}")
                        else:
                            raise Exception(f"API error {error_code}: {error_message}")

                    # Extract response
                    candidates = response_data.get("candidates", [])
                    if not candidates:
                        logger.warning("No candidates in response")
                        fallback_resp = self._fallback_response(prompt)
                        return f"[FALLBACK]{fallback_resp}", None

                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])

                    # Check for function calls
                    function_calls = [p for p in parts if "functionCall" in p]

                    if function_calls:
                        logger.info(f"STEP 2: LLM REQUESTED TOOL CALLS - {len(function_calls)} tool(s)")

                        # Add assistant response to conversation
                        contents.append({"role": "model", "parts": parts})

                        # Process each function call
                        function_responses = []
                        for fc in function_calls:
                            fc_data = fc["functionCall"]
                            tool_name = fc_data.get("name", "")
                            tool_args = fc_data.get("args", {})

                            logger.info(f"   Tool: {tool_name}")
                            logger.info(f"   Arguments: {tool_args}")

                            if tool_name == "get_game_memory":
                                tool_result = self._execute_memory_tool(memory_data, tool_args)
                                logger.info(f"   Tool result length: {len(tool_result)} chars")

                                tool_tracker.record_tool_call(
                                    tool_name=tool_name,
                                    tool_args=tool_args,
                                    tool_result=tool_result,
                                    iteration=tool_iteration
                                )
                            else:
                                tool_result = f"Unknown tool: {tool_name}"

                            function_responses.append({
                                "functionResponse": {
                                    "name": tool_name,
                                    "response": {"result": tool_result}
                                }
                            })

                        # Add function responses to conversation
                        contents.append({"role": "user", "parts": function_responses})
                        logger.info(f"STEP 5: CONTINUING LOOP TO GET FINAL RESPONSE")
                        continue

                    # No function calls - extract text response
                    text_parts = [p.get("text", "") for p in parts if "text" in p]
                    response_text = "".join(text_parts)

                    tool_tracker.total_iterations = tool_iteration

                    logger.info(f"STEP 6: LLM PROVIDED FINAL RESPONSE")
                    logger.info(f"   Response length: {len(response_text)} chars")

                    # Handle empty response
                    if not response_text:
                        if tool_tracker.tool_calls:
                            logger.warning("WARNING: LLM returned empty content after tool calls")
                            response_text = self._generate_fallback_after_tool_calls(prompt, tool_tracker.tool_calls)
                        else:
                            logger.warning("WARNING: LLM returned empty content")
                            response_text = self._fallback_response(prompt)

                    # Log tool usage summary
                    if tool_tracker.tool_calls:
                        logger.info(f"TOOL CALLS SUMMARY: {len(tool_tracker.tool_calls)} tool call(s) made")
                        tool_usage_verified = self._verify_tool_usage(response_text, tool_tracker.tool_calls)
                        if tool_usage_verified:
                            logger.info(f"VERIFIED: LLM response shows evidence of using tool results")
                        else:
                            logger.warning(f"WARNING: LLM made tool calls but response doesn't clearly reference tool results")

                    logger.info(f"LLM RESPONSE RECEIVED (length: {len(response_text)}):")
                    logger.info(f"   {response_text[:500]}...")

                    tool_info = tool_tracker.to_dict() if tool_tracker.tool_calls else None
                    if tool_info:
                        tool_info["tool_usage_verified"] = self._verify_tool_usage(response_text, tool_tracker.tool_calls)
                    return response_text, tool_info

                # Max tool iterations reached
                logger.warning(f"WARNING: Max tool iterations ({max_tool_iterations}) reached")
                fallback_resp = self._fallback_response(prompt)
                return fallback_resp, tool_tracker.to_dict() if tool_tracker.tool_calls else None

            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "429" in error_str or "rate limit" in error_str or "quota" in error_str

                if is_rate_limit and attempt < max_retries:
                    logger.warning(f"Rate limit error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    logger.warning(f"   Waiting {retry_delay} seconds before retry...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"LLM call failed: {e}")
                    fallback_resp = self._fallback_response(prompt)
                    return f"[FALLBACK]{fallback_resp}", tool_tracker.to_dict() if tool_tracker.tool_calls else None

        # Should never reach here
        logger.error("Max retries exceeded")
        fallback_resp = self._fallback_response(prompt)
        return f"[FALLBACK]{fallback_resp}", None

    async def _call_gemini_api(
        self,
        contents: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Make a direct call to the Gemini API."""
        url = f"{GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            }
        }

        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            return response.json()

    def _execute_memory_tool(self, memory_data: Optional[Dict[str, Any]], args: Dict[str, Any]) -> str:
        """Execute the get_game_memory tool."""
        if not memory_data:
            return "No game history available yet."

        max_rounds = args.get("max_rounds")

        lines = [f"═══ GAME MEMORY (ID: {memory_data.get('memory_id', 'unknown')}) ═══"]

        discussions = memory_data.get("discussions", [])
        votes = memory_data.get("votes", [])
        eliminations = memory_data.get("eliminations", [])

        all_rounds = set()
        for d in discussions:
            all_rounds.add(d.get("round", 1))
        for v in votes:
            all_rounds.add(v.get("round", 1))

        if not all_rounds:
            lines.append("No game history yet.")
            return "\n".join(lines)

        rounds = sorted(all_rounds)
        if max_rounds and len(rounds) > max_rounds:
            rounds = rounds[-max_rounds:]
            lines.append(f"[Showing last {max_rounds} rounds of {len(all_rounds)}]")

        for round_num in rounds:
            lines.append(f"\nROUND {round_num}:")

            round_discussions = [d for d in discussions if d.get("round") == round_num]
            if round_discussions:
                lines.append("  Discussions:")
                for d in round_discussions:
                    agent = d.get("agent_id", "unknown")
                    content = d.get("content", "")[:300]
                    targets = d.get("targets", [])
                    target_str = f" (targets: {','.join(targets)})" if targets else ""
                    lines.append(f"    {agent}{target_str}: \"{content}\"")

            round_votes = [v for v in votes if v.get("round") == round_num]
            if round_votes:
                lines.append("  Votes:")
                vote_counts = {}
                for v in round_votes:
                    voter = v.get("voter_id", "unknown")
                    target = v.get("target_id", "unknown")
                    vote_counts[target] = vote_counts.get(target, 0) + 1
                    lines.append(f"    {voter} -> {target}")
                vote_summary = ", ".join([f"{t}:{c}" for t, c in sorted(vote_counts.items(), key=lambda x: -x[1])])
                lines.append(f"    Summary: {vote_summary}")

            round_elims = [e for e in eliminations if e.get("round") == round_num]
            if round_elims:
                lines.append("  Eliminated:")
                for e in round_elims:
                    agent = e.get("agent_id", "unknown")
                    method = e.get("method", "unknown")
                    public_method = method if method in ["vote", "hunter_shot"] else "eliminated"
                    lines.append(f"    {agent} ({public_method})")

        alive_by_round = memory_data.get("alive_by_round", {})
        if alive_by_round:
            latest_round = max(int(k) for k in alive_by_round.keys())
            alive_count = len(alive_by_round[str(latest_round)])
            lines.append(f"\nCurrent: {alive_count} alive, {len(eliminations)} eliminated")

        lines.append("═══════════════════════════════")
        return "\n".join(lines)

    def _verify_tool_usage(self, response_text: str, tool_calls: List[Dict[str, Any]]) -> bool:
        """Verify that the LLM response shows evidence of using tool call results."""
        if not tool_calls:
            return False

        response_lower = response_text.lower()

        memory_indicators = [
            "round", "previous round", "last round", "earlier round", "past round",
            "voted", "voting", "vote", "voter", "voting pattern", "who voted",
            "eliminated", "elimination", "killed", "died", "was killed", "eliminated in",
            "history", "historical", "past", "earlier", "before", "previously",
            "pattern", "behavior", "consistent", "contradiction", "suspicious", "based on",
            "game history", "past discussions", "previous discussions", "earlier accusations"
        ]

        indicator_count = sum(1 for indicator in memory_indicators if indicator in response_lower)

        import re
        round_mentions = len(re.findall(r'round\s+\d+', response_lower))

        return (
            indicator_count >= 2 or
            round_mentions >= 1 or
            (indicator_count >= 1 and len(response_text) > 200)
        )

    def _generate_fallback_after_tool_calls(self, prompt: str, tool_calls: List[Dict[str, Any]]) -> str:
        """Generate a fallback response when LLM returns empty content after tool calls."""
        prompt_lower = prompt.lower()

        if "day_discussion" in prompt_lower or "discussion phase" in prompt_lower:
            reasoning = "Reviewed game history via tool call. Contributing to discussion based on past events."
            return f"ACTION: discuss\nDISCUSSION_SUBACTIONS: [general_discussion]\nDISCUSSION_TARGETS: []\nCONTENT: Based on the game history I reviewed, I'm analyzing the situation.\nREASONING: {reasoning}"
        elif "day_voting" in prompt_lower or "voting phase" in prompt_lower:
            reasoning = "Reviewed game history via tool call. Voting based on patterns observed."
            return f"ACTION: vote\nTARGET: agent_0\nREASONING: {reasoning}"
        elif "discussion" in prompt_lower:
            return f"ACTION: discuss\nDISCUSSION_SUBACTIONS: [general_discussion]\nDISCUSSION_TARGETS: []\nCONTENT: Based on the game history I reviewed, I'm analyzing the situation.\nREASONING: Reviewed game history via tool call."
        elif "werewolf" in prompt_lower and "kill" in prompt_lower:
            return f"ACTION: kill\nTARGET: agent_0\nREASONING: Targeting based on threat assessment."
        elif "seer" in prompt_lower and "investigate" in prompt_lower:
            return f"ACTION: investigate\nTARGET: agent_0\nREASONING: Investigating suspicious player."
        elif "doctor" in prompt_lower and "protect" in prompt_lower:
            return f"ACTION: protect\nTARGET: agent_0\nREASONING: Protecting valuable player."
        elif "witch" in prompt_lower:
            if "heal" in prompt_lower:
                return "ACTION: heal\nTARGET: none\nREASONING: Saving heal potion for now."
            return "ACTION: pass\nTARGET: none\nREASONING: Conserving potions."
        else:
            return f"ACTION: pass\nTARGET: none\nREASONING: Waiting for more information."

    def _fallback_response(self, prompt: str) -> str:
        """Generate a fallback response when LLM is unavailable."""
        prompt_lower = prompt.lower()

        if "day_discussion" in prompt_lower or "discussion phase" in prompt_lower:
            return "ACTION: discuss\nDISCUSSION_SUBACTIONS: [general_discussion]\nDISCUSSION_TARGETS: []\nCONTENT: Observing and gathering information.\nREASONING: Analyzing the situation carefully."
        elif "day_voting" in prompt_lower or "voting phase" in prompt_lower:
            return "ACTION: vote\nTARGET: agent_0\nREASONING: Voting for agent_0 based on suspicion."
        elif "discussion" in prompt_lower:
            return "ACTION: discuss\nDISCUSSION_SUBACTIONS: [general_discussion]\nDISCUSSION_TARGETS: []\nCONTENT: Observing and gathering information.\nREASONING: Analyzing the situation carefully."
        elif "voting" in prompt_lower or "vote" in prompt_lower:
            return "ACTION: vote\nTARGET: agent_0\nREASONING: Voting for agent_0 based on suspicion."
        elif "werewolf" in prompt_lower and "kill" in prompt_lower:
            return "ACTION: kill\nTARGET: agent_0\nREASONING: Targeting based on threat assessment."
        elif "seer" in prompt_lower and "investigate" in prompt_lower:
            return "ACTION: investigate\nTARGET: agent_0\nREASONING: Investigating suspicious player."
        elif "doctor" in prompt_lower and "protect" in prompt_lower:
            return "ACTION: protect\nTARGET: agent_0\nREASONING: Protecting valuable player."
        elif "witch" in prompt_lower:
            if "heal" in prompt_lower:
                return "ACTION: heal\nTARGET: none\nREASONING: Saving heal potion for now."
            return "ACTION: pass\nTARGET: none\nREASONING: Conserving potions."
        else:
            return "ACTION: pass\nTARGET: none\nREASONING: Waiting for more information."


class MockLLMHandler(LLMHandler):
    """Mock LLM Handler for testing without API calls."""

    def __init__(self, *args, **kwargs):
        # Don't call super().__init__ to avoid API key check
        self.model = "mock-model"
        self.temperature = 1
        self.max_tokens = 4000
        self.api_key = "mock-key"
        self.call_count = 0
        self.last_prompt = None
        self.last_memory_data = None

    async def get_response(
        self,
        prompt: str,
        memory_data: Optional[Dict[str, Any]] = None
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """Return mock responses for testing."""
        self.call_count += 1
        self.last_prompt = prompt
        self.last_memory_data = memory_data

        return self._fallback_response(prompt), None
