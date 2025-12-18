"""LLM Handler using LiteLLM for White Agent responses with tool calling support."""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


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

# LiteLLM import with fallback
try:
    import litellm
    from litellm import acompletion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.warning("LiteLLM not available, using fallback responses")


# Tool definition for game memory access
MEMORY_TOOL = {
    "type": "function",
    "function": {
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
    }
}


class LLMHandler:
    """Handles LLM interactions for the White Agent using LiteLLM."""
    
    # System prompt - keep it generic, let the Green Agent's prompt specify exact format
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
        model: str = "gemini/gemini-2.5-flash",  # Default to Gemini 2.5 Flash (cost-effective)
        temperature: float = 1,
        max_tokens: int = 4000  # Enforce concise responses
    ):
        """
        Initialize the LLM handler.
        
        Args:
            model: The LiteLLM model to use (default: gemini/gemini-2.5-flash)
            temperature: Response temperature (0.0-1.0)
            max_tokens: Maximum tokens in response (kept low for cost savings)
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Detect provider based on model name
        self.is_gemini = model.startswith("gemini/") or "gemini" in model.lower()
        
        # Configure LiteLLM if available
        if LITELLM_AVAILABLE:
            if self.is_gemini:
                # For Gemini models, check GEMINI_API_KEY first, then GOOGLE_API_KEY
                # LiteLLM supports both, but GEMINI_API_KEY is more commonly used
                api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                # Set both environment variables for LiteLLM compatibility
                if api_key:
                    os.environ["GEMINI_API_KEY"] = api_key
                    os.environ["GOOGLE_API_KEY"] = api_key
            else:
                # For OpenAI models, use OPENAI_API_KEY
                api_key = os.getenv("OPENAI_API_KEY")
                litellm.api_key = api_key
                # Set organization ID if provided (helps with organization access)
                org_id = os.getenv("OPENAI_ORG_ID")
                if org_id:
                    litellm.organization = org_id
            
            # Enable caching for repeated similar prompts
            litellm.cache = None  # Disable for now, can enable for testing
            logger.info(f"LLM Handler initialized with model: {model}")
            logger.info(f"   LiteLLM available: True")
            logger.info(f"   Provider: {'Gemini' if self.is_gemini else 'OpenAI'}")
            if self.is_gemini:
                gemini_key = os.getenv("GEMINI_API_KEY")
                google_key = os.getenv("GOOGLE_API_KEY")
                api_key_env = "GEMINI_API_KEY" if gemini_key else "GOOGLE_API_KEY"
                logger.info(f"   API Key ({api_key_env}) present: {bool(api_key)}")
            else:
                api_key_env = "OPENAI_API_KEY"
                logger.info(f"   API Key ({api_key_env}) present: {bool(api_key)}")
            if api_key:
                logger.info(f"   API Key length: {len(api_key)}")
        else:
            logger.error("Running in fallback mode - LiteLLM NOT AVAILABLE")
            logger.error("   Install with: pip install litellm")
            logger.error("   Python path: Check which Python is being used")

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
            - response_text: The LLM response string (with metadata prefix if fallback)
            - tool_call_info: Dictionary with tool call tracking data (or None if no tools used)
        """
        # Initialize tool call tracker
        tool_tracker = ToolCallTracker()
        if not LITELLM_AVAILABLE:
            logger.error("LiteLLM not available - using fallback response")
            logger.error("   Install with: pip install litellm")
            fallback_resp = self._fallback_response(prompt)
            # Add marker to identify fallback responses
            return f"[FALLBACK]{fallback_resp}", None
        
        # Check API key based on model provider
        if self.is_gemini:
            # Check GEMINI_API_KEY first, then GOOGLE_API_KEY
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("GEMINI_API_KEY or GOOGLE_API_KEY not set - using fallback response")
                logger.error("   Set with: export GEMINI_API_KEY='your-key'")
                logger.error("   Or: export GOOGLE_API_KEY='your-key'")
                logger.error("   Get your key from: https://aistudio.google.com/app/apikey")
                fallback_resp = self._fallback_response(prompt)
                return f"[FALLBACK]{fallback_resp}", None
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY not set - using fallback response")
                logger.error("   Set with: export OPENAI_API_KEY='your-key'")
                fallback_resp = self._fallback_response(prompt)
                return f"[FALLBACK]{fallback_resp}", None
        
        # Prepare tools if memory data is available
        tools = [MEMORY_TOOL] if memory_data else None
        
        # Initialize messages for agentic loop (conversation history)
        # This follows the standard LLM tool calling pattern:
        # 1. Start with system prompt + user prompt
        # 2. LLM may request tool call → we add assistant message with tool_calls
        # 3. We execute tool → add tool result message with role "tool"
        # 4. Send full conversation back to LLM → LLM generates final response
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        logger.info(f"CONVERSATION INITIALIZED:")
        logger.info(f"   System prompt: {len(self.SYSTEM_PROMPT)} chars")
        logger.info(f"   User prompt: {len(prompt)} chars")
        logger.info(f"   Tools available: {bool(tools)}")
        
        # Retry logic for rate limit errors
        max_retries = 29
        retry_delay = 30  # seconds
        max_tool_iterations = 3  # Prevent infinite tool call loops
        
        for attempt in range(max_retries + 1):
            try:
                # Agentic loop for tool calls
                tool_iteration = 0
                while tool_iteration < max_tool_iterations:
                    tool_iteration += 1
                    
                    logger.info(f"CALLING LLM (iteration {tool_iteration}):")
                    logger.info(f"   Model: {self.model}")
                    logger.info(f"   Tools: {'enabled' if tools else 'disabled'}")
                    logger.info(f"   Conversation history: {len(messages)} messages")
                    for i, msg in enumerate(messages):
                        role = msg.get('role', 'unknown')
                        has_tool_calls = 'tool_calls' in msg
                        has_tool_call_id = 'tool_call_id' in msg
                        content_len = len(str(msg.get('content', '')))
                        logger.info(f"      [{i}] role={role}, content_len={content_len}, tool_calls={has_tool_calls}, tool_result={has_tool_call_id}")
                    logger.info(f"   Attempt: {attempt + 1}/{max_retries + 1}")
                    
                    # Prepare API call kwargs
                    kwargs = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens
                    }
                    
                    # Add tools if available
                    if tools:
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = "auto"
                    
                    # Only set api_key explicitly for non-Gemini models
                    if not self.is_gemini:
                        kwargs["api_key"] = api_key
                    
                    response = await acompletion(**kwargs)
                    message = response.choices[0].message
                    
                    # Debug: Log message structure and API response details
                    logger.debug(f"   Message type: {type(message)}")
                    logger.debug(f"   Message has content attr: {hasattr(message, 'content')}")
                    if hasattr(message, 'content'):
                        content_value = message.content
                        logger.debug(f"   Message content type: {type(content_value)}, value: {repr(content_value)}")
                        if content_value is None:
                            logger.warning(f"   WARNING: message.content is None (not empty string, but None)")
                        elif content_value == "":
                            logger.warning(f"   WARNING: message.content is empty string")
                    else:
                        logger.warning(f"   WARNING: message does not have 'content' attribute")
                    logger.debug(f"   Message has tool_calls attr: {hasattr(message, 'tool_calls')}")
                    if hasattr(message, 'tool_calls'):
                        logger.debug(f"   Message tool_calls: {message.tool_calls}")
                    # Log full response structure for debugging
                    logger.debug(f"   Full response object: {type(response)}")
                    if hasattr(response, 'choices') and len(response.choices) > 0:
                        logger.debug(f"   Response has {len(response.choices)} choice(s)")
                        if hasattr(response.choices[0], 'finish_reason'):
                            logger.debug(f"   Finish reason: {response.choices[0].finish_reason}")
                    
                    # Check for tool calls
                    # Handle both OpenAI-style (tool_calls attribute) and Gemini-style (function_calls)
                    tool_calls = None
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        tool_calls = message.tool_calls
                    elif hasattr(message, 'function_calls') and message.function_calls:
                        tool_calls = message.function_calls
                    
                    if tool_calls:
                        logger.info(f"STEP 2: LLM REQUESTED TOOL CALLS - {len(tool_calls)} tool(s)")
                        logger.info(f"   The LLM has decided to call tools before providing final response")
                        
                        # STEP 2a: Add assistant message with tool calls to conversation
                        assistant_msg = {
                            "role": "assistant",
                            "content": message.content or "",
                        }
                        
                        # Add tool_calls in OpenAI format
                        assistant_msg["tool_calls"] = [
                            {
                                "id": getattr(tc, 'id', f"call_{i}"),
                                "type": "function",
                                "function": {
                                    "name": getattr(tc.function, 'name', None) or getattr(tc, 'name', None),
                                    "arguments": getattr(tc.function, 'arguments', None) or getattr(tc, 'arguments', None) or "{}"
                                }
                            }
                            for i, tc in enumerate(tool_calls)
                        ]
                        messages.append(assistant_msg)
                        logger.info(f"   Added assistant message with tool calls to conversation")
                        
                        # STEP 3: Execute each tool call
                        logger.info(f"STEP 3: EXECUTING TOOL CALLS")
                        for tool_call in tool_calls:
                            tool_name = getattr(tool_call.function, 'name', None) or getattr(tool_call, 'name', None)
                            tool_args_str = getattr(tool_call.function, 'arguments', None) or getattr(tool_call, 'arguments', None) or "{}"
                            
                            logger.info(f"   Tool: {tool_name}")
                            logger.info(f"   Arguments: {tool_args_str}")
                            
                            if tool_name == "get_game_memory":
                                # Parse arguments
                                try:
                                    args = json.loads(tool_args_str) if tool_args_str else {}
                                except json.JSONDecodeError:
                                    args = {}
                                
                                # Execute the memory tool
                                tool_result = self._execute_memory_tool(memory_data, args)
                                logger.info(f"   Tool result length: {len(tool_result)} chars")
                                logger.info(f"   Tool result preview: {tool_result[:300]}...")
                                
                                # Track the tool call
                                tool_tracker.record_tool_call(
                                    tool_name=tool_name,
                                    tool_args=args,
                                    tool_result=tool_result,
                                    iteration=tool_iteration
                                )
                            else:
                                tool_result = f"Unknown tool: {tool_name}"
                                tool_tracker.record_tool_call(
                                    tool_name=tool_name,
                                    tool_args={"raw": tool_args_str},
                                    tool_result=tool_result,
                                    iteration=tool_iteration
                                )
                            
                            # STEP 4: Add tool result to messages (conversation history)
                            tool_call_id = getattr(tool_call, 'id', f"call_{tool_iteration}")
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": tool_result
                            })
                            
                            logger.info(f"   STEP 4: Tool result added to conversation")
                            logger.info(f"   Result length: {len(tool_result)} chars")
                            logger.info(f"   Result preview: {tool_result[:300]}...")
                            if len(tool_result) > 300:
                                logger.info(f"   ... (truncated, full: {len(tool_result)} chars)")
                        
                        # STEP 5: Continue loop to get final response after tool execution
                        # The conversation now contains: system + user + assistant(tool_calls) + tool(results)
                        # Next iteration will send this full conversation to LLM
                        # LLM will see the tool results and generate a final response using that information
                        logger.info(f"STEP 5: CONTINUING LOOP TO GET FINAL RESPONSE")
                        logger.info(f"   Conversation now has {len(messages)} messages (including tool results)")
                        logger.info(f"   Next LLM call will see: original prompt + tool calls + tool results")
                        logger.info(f"   LLM should now generate final response using the memory data")
                        continue
                    
                    # STEP 6: No tool calls - we have the final response
                    logger.info(f"STEP 6: LLM PROVIDED FINAL RESPONSE (no more tool calls)")
                    
                    # Extract content safely (handle different response formats)
                    response_text = ""
                    if hasattr(message, 'content'):
                        response_text = message.content or ""
                    elif hasattr(message, 'text'):
                        response_text = message.text or ""
                    elif isinstance(message, dict):
                        response_text = message.get('content', message.get('text', '')) or ""
                    
                    tool_tracker.total_iterations = tool_iteration
                    
                    logger.info(f"   Response length: {len(response_text)} chars")
                    
                    # Log warning if empty response without tool calls (especially in day_discussion)
                    if not response_text and not tool_tracker.tool_calls:
                        prompt_lower = prompt.lower()
                        if "day_discussion" in prompt_lower or "discussion phase" in prompt_lower:
                            logger.warning(f"   WARNING: Empty response in day_discussion phase without tool calls!")
                            logger.warning(f"   This may indicate:")
                            logger.warning(f"   1. Gemini API returned empty content (possible API issue)")
                            logger.warning(f"   2. Response was truncated or lost")
                            logger.warning(f"   3. Model chose not to respond (unlikely but possible)")
                            logger.warning(f"   Prompt length: {len(prompt)} chars")
                            logger.warning(f"   Will use fallback response")
                    
                    if tool_tracker.tool_calls:
                        logger.info(f"   This response came AFTER reviewing tool results")
                        logger.info(f"   LLM had access to: {len(tool_tracker.tool_calls)} tool call result(s)")
                    else:
                        logger.info(f"   This response came without using tools (may be first round or LLM chose not to call)")
                    
                    # Handle empty response after tool calls
                    if not response_text and tool_tracker.tool_calls:
                        logger.warning(f"WARNING: LLM returned empty content after {len(tool_tracker.tool_calls)} tool call(s)")
                        logger.warning(f"   Tool calls were made successfully, but LLM did not provide text response.")
                        logger.warning(f"   This suggests the LLM may think the tool call itself is sufficient.")
                        logger.warning(f"   The LLM MUST provide an ACTION response AFTER receiving tool results.")
                        logger.warning(f"   Generating fallback response based on phase and role.")
                        # Generate a fallback response since LLM didn't provide text after tool calls
                        response_text = self._generate_fallback_after_tool_calls(prompt, tool_tracker.tool_calls)
                    elif not response_text:
                        logger.warning(f"WARNING: LLM returned empty content with no tool calls")
                        logger.warning(f"   This may indicate an API issue or model error.")
                        logger.warning(f"   Using fallback response.")
                        response_text = self._fallback_response(prompt)
                    
                    # Log tool usage summary
                    if tool_tracker.tool_calls:
                        logger.info(f"TOOL CALLS SUMMARY: {len(tool_tracker.tool_calls)} tool call(s) made")
                        for i, tc in enumerate(tool_tracker.tool_calls):
                            logger.info(f"   [{i+1}] {tc['tool_name']}: args={tc['tool_args']}, result_length={tc['tool_result_length']}")
                        
                        # Verify that LLM actually used the tool results
                        tool_usage_verified = self._verify_tool_usage(response_text, tool_tracker.tool_calls)
                        if tool_usage_verified:
                            logger.info(f"VERIFIED: LLM response shows evidence of using tool results")
                        else:
                            logger.warning(f"WARNING: LLM made tool calls but response doesn't clearly reference tool results")
                            logger.warning(f"   This may indicate the LLM ignored the memory data.")
                            logger.warning(f"   Response may not be informed by game history.")
                    else:
                        logger.info(f"No tool calls made (LLM did not request memory)")
                    
                    logger.info(f"LLM RESPONSE RECEIVED (length: {len(response_text)}):")
                    logger.info(f"   {response_text[:500]}...")  # Print first 500 chars
                    if len(response_text) > 500:
                        logger.info(f"   ... (truncated, total length: {len(response_text)})")
                    
                    # Return response with tool call tracking info
                    tool_info = tool_tracker.to_dict() if tool_tracker.tool_calls else None
                    if tool_info and tool_tracker.tool_calls:
                        # Add verification status to tool info
                        tool_info["tool_usage_verified"] = self._verify_tool_usage(response_text, tool_tracker.tool_calls)
                    return response_text, tool_info
                
                # Max tool iterations reached
                tool_tracker.total_iterations = max_tool_iterations
                logger.warning(f"WARNING: Max tool iterations ({max_tool_iterations}) reached, returning last response")
                
                # Extract content safely
                last_response = ""
                if hasattr(message, 'content'):
                    last_response = message.content or ""
                elif hasattr(message, 'text'):
                    last_response = message.text or ""
                elif isinstance(message, dict):
                    last_response = message.get('content', message.get('text', '')) or ""
                
                # If still empty and we had tool calls, generate fallback
                if not last_response and tool_tracker.tool_calls:
                    last_response = self._generate_fallback_after_tool_calls(prompt, tool_tracker.tool_calls)
                elif not last_response:
                    last_response = self._fallback_response(prompt)
                
                tool_info = tool_tracker.to_dict() if tool_tracker.tool_calls else None
                return last_response, tool_info
                
            except Exception as e:
                # Check if this is a rate limit error
                is_rate_limit = False
                error_str = str(e).lower()
                
                # Check for rate limit indicators
                if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
                    is_rate_limit = True
                elif LITELLM_AVAILABLE:
                    # Check if it's a litellm RateLimitError
                    try:
                        from litellm import RateLimitError
                        if isinstance(e, RateLimitError):
                            is_rate_limit = True
                    except ImportError:
                        pass
                
                if is_rate_limit and attempt < max_retries:
                    logger.warning(f"WARNING: Rate limit error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    logger.warning(f"   Waiting {retry_delay} seconds before retry...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    # Not a rate limit error, or max retries reached
                    if is_rate_limit:
                        logger.error(f"ERROR: Rate limit error persisted after {max_retries + 1} attempts. Using fallback response.")
                    else:
                        logger.error(f"LLM call failed: {e}", exc_info=True)
                        logger.error(f"Model: {self.model}, API Key present: {bool(api_key)}")
                    fallback_resp = self._fallback_response(prompt)
                    tool_info = tool_tracker.to_dict() if tool_tracker.tool_calls else None
                    return f"[FALLBACK]{fallback_resp}", tool_info
        
        # Should never reach here, but just in case
        logger.error("ERROR: Max retries exceeded. Using fallback response.")
        fallback_resp = self._fallback_response(prompt)
        tool_info = tool_tracker.to_dict() if tool_tracker.tool_calls else None
        return f"[FALLBACK]{fallback_resp}", tool_info
    
    def _execute_memory_tool(self, memory_data: Optional[Dict[str, Any]], args: Dict[str, Any]) -> str:
        """
        Execute the get_game_memory tool.
        
        Args:
            memory_data: Serialized memory data from Green Agent
            args: Tool arguments (may include max_rounds)
            
        Returns:
            Formatted game history string
        """
        if not memory_data:
            return "No game history available yet."
        
        max_rounds = args.get("max_rounds")
        
        # Build memory summary from serialized data
        lines = [f"═══ GAME MEMORY (ID: {memory_data.get('memory_id', 'unknown')}) ═══"]
        
        # Get discussions by round
        discussions = memory_data.get("discussions", [])
        votes = memory_data.get("votes", [])
        eliminations = memory_data.get("eliminations", [])
        
        # Group by round
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
            
            # Discussions for this round
            round_discussions = [d for d in discussions if d.get("round") == round_num]
            if round_discussions:
                lines.append("  Discussions:")
                for d in round_discussions:
                    agent = d.get("agent_id", "unknown")
                    content = d.get("content", "")[:300]
                    targets = d.get("targets", [])
                    target_str = f" (targets: {','.join(targets)})" if targets else ""
                    lines.append(f"    {agent}{target_str}: \"{content}\"")
            
            # Votes for this round
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
            
            # Eliminations in this round
            round_elims = [e for e in eliminations if e.get("round") == round_num]
            if round_elims:
                lines.append("  Eliminated:")
                for e in round_elims:
                    agent = e.get("agent_id", "unknown")
                    method = e.get("method", "unknown")
                    # Only show public methods
                    public_method = method if method in ["vote", "hunter_shot"] else "eliminated"
                    lines.append(f"    {agent} ({public_method})")
        
        # Current status
        alive_by_round = memory_data.get("alive_by_round", {})
        if alive_by_round:
            latest_round = max(int(k) for k in alive_by_round.keys())
            alive_count = len(alive_by_round[str(latest_round)])
            lines.append(f"\nCurrent: {alive_count} alive, {len(eliminations)} eliminated")
        
        lines.append("═══════════════════════════════")
        return "\n".join(lines)

    def _verify_tool_usage(self, response_text: str, tool_calls: List[Dict[str, Any]]) -> bool:
        """
        Verify that the LLM response shows evidence of using tool call results.
        
        Checks if the response references things that would be in game memory:
        - Past rounds (e.g., "round 1", "previous round", "last round")
        - Voting patterns (e.g., "voted for", "voting pattern", "who voted")
        - Eliminations (e.g., "eliminated", "was killed", "died")
        - Historical references (e.g., "earlier", "before", "past", "history")
        - Specific analysis of past events
        
        Returns True if evidence of tool usage is found, False otherwise.
        """
        if not tool_calls:
            return False
        
        response_lower = response_text.lower()
        
        # Check for memory-related keywords that suggest the LLM reviewed history
        memory_indicators = [
            # Round references
            "round", "previous round", "last round", "earlier round", "past round",
            # Voting references
            "voted", "voting", "vote", "voter", "voting pattern", "who voted",
            # Elimination references
            "eliminated", "elimination", "killed", "died", "was killed", "eliminated in",
            # Historical references
            "history", "historical", "past", "earlier", "before", "previously", "earlier discussion",
            # Analysis keywords
            "pattern", "behavior", "consistent", "contradiction", "suspicious", "based on",
            # Memory-specific phrases
            "game history", "past discussions", "previous discussions", "earlier accusations"
        ]
        
        # Count how many indicators are present
        indicator_count = sum(1 for indicator in memory_indicators if indicator in response_lower)
        
        # Also check if response mentions specific round numbers (strong indicator)
        import re
        round_mentions = len(re.findall(r'round\s+\d+|round\s+\d+', response_lower))
        
        # Consider verified if:
        # 1. Multiple memory indicators present, OR
        # 2. Specific round numbers mentioned, OR
        # 3. Response is long and contains analysis keywords (suggests thoughtful use of memory)
        is_verified = (
            indicator_count >= 2 or  # At least 2 memory-related terms
            round_mentions >= 1 or   # Mentions specific rounds
            (indicator_count >= 1 and len(response_text) > 200)  # One indicator + substantial response
        )
        
        return is_verified

    def _generate_fallback_after_tool_calls(
        self, 
        prompt: str, 
        tool_calls: List[Dict[str, Any]]
    ) -> str:
        """
        Generate a fallback response when LLM returns empty content after tool calls.
        
        This happens when the LLM makes tool calls but then doesn't provide text content.
        We generate a response based on the phase and acknowledge that memory was reviewed.
        """
        prompt_lower = prompt.lower()
        
        # Check what tool was called
        memory_tool_called = any(tc.get("tool_name") == "get_game_memory" for tc in tool_calls)
        
        # Detect phase from prompt - check more specific patterns first
        if "day_discussion" in prompt_lower or "discussion phase" in prompt_lower:
            reasoning = "Reviewed game history via tool call. Contributing to discussion based on past events."
            return f"ACTION: discuss\nDISCUSSION_SUBACTIONS: [general_discussion]\nDISCUSSION_TARGETS: []\nCONTENT: Based on the game history I reviewed, I'm analyzing the situation.\nREASONING: {reasoning}"
        elif "day_voting" in prompt_lower or "voting phase" in prompt_lower:
            reasoning = "Reviewed game history via tool call. Voting based on patterns observed."
            return f"ACTION: vote\nTARGET: agent_0\nREASONING: {reasoning}"
        elif "discussion" in prompt_lower:
            reasoning = "Reviewed game history via tool call. Contributing to discussion based on past events."
            return f"ACTION: discuss\nDISCUSSION_SUBACTIONS: [general_discussion]\nDISCUSSION_TARGETS: []\nCONTENT: Based on the game history I reviewed, I'm analyzing the situation.\nREASONING: {reasoning}"
        elif "werewolf" in prompt_lower and "kill" in prompt_lower:
            reasoning = "Reviewed game history via tool call. Targeting based on threat assessment."
            return f"ACTION: kill\nTARGET: agent_0\nREASONING: {reasoning}"
        elif "seer" in prompt_lower and "investigate" in prompt_lower:
            reasoning = "Reviewed game history via tool call. Investigating based on voting patterns."
            return f"ACTION: investigate\nTARGET: agent_0\nREASONING: {reasoning}"
        elif "doctor" in prompt_lower and "protect" in prompt_lower:
            reasoning = "Reviewed game history via tool call. Protecting based on past events."
            return f"ACTION: protect\nTARGET: agent_0\nREASONING: {reasoning}"
        elif "witch" in prompt_lower:
            if "heal" in prompt_lower:
                return "ACTION: heal\nTARGET: none\nREASONING: Reviewed game history. Deciding on potion use."
            return "ACTION: pass\nTARGET: none\nREASONING: Reviewed game history. Conserving potions."
        else:
            reasoning = "Reviewed game history via tool call. Making decision based on information gathered."
            return f"ACTION: pass\nTARGET: none\nREASONING: {reasoning}"
    
    def _fallback_response(self, prompt: str) -> str:
        """
        Generate a fallback response when LLM is unavailable.
        
        This extracts key information from the prompt and generates
        a basic strategic response.
        """
        prompt_lower = prompt.lower()
        
        # Detect phase from prompt - check more specific patterns first
        # Check for explicit phase markers first
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
        super().__init__(*args, **kwargs)
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
        
        # Generate deterministic responses based on prompt content
        return self._fallback_response(prompt), None


