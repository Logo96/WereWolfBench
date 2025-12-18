"""LLM Handler using LiteLLM for White Agent responses."""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# LiteLLM import with fallback
try:
    import litellm
    from litellm import acompletion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.warning("LiteLLM not available, using fallback responses")


class LLMHandler:
    """Handles LLM interactions for the White Agent using LiteLLM."""
    
    # System prompt - keep it generic, let the Green Agent's prompt specify exact format
    SYSTEM_PROMPT = """You are an AI playing a game of Werewolf. 

IMPORTANT: Follow the response format specified in the user's prompt exactly. 
The user prompt will tell you the exact format to use (ACTION, TARGET, REASONING, etc.).

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
            logger.info(f"✅ LLM Handler initialized with model: {model}")
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
            logger.error("❌ Running in fallback mode - LiteLLM NOT AVAILABLE")
            logger.error("   Install with: pip install litellm")
            logger.error("   Python path: Check which Python is being used")

    async def get_response(self, prompt: str) -> str:
        """
        Get a response from the LLM with retry logic for rate limits.
        
        Args:
            prompt: The prompt from the Green Agent
            
        Returns:
            The LLM response string (with metadata prefix if fallback)
        """
        if not LITELLM_AVAILABLE:
            logger.error("❌ LiteLLM not available - using fallback response")
            logger.error("   Install with: pip install litellm")
            fallback_resp = self._fallback_response(prompt)
            # Add marker to identify fallback responses
            return f"[FALLBACK]{fallback_resp}"
        
        # Check API key based on model provider
        if self.is_gemini:
            # Check GEMINI_API_KEY first, then GOOGLE_API_KEY
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("❌ GEMINI_API_KEY or GOOGLE_API_KEY not set - using fallback response")
                logger.error("   Set with: export GEMINI_API_KEY='your-key'")
                logger.error("   Or: export GOOGLE_API_KEY='your-key'")
                logger.error("   Get your key from: https://aistudio.google.com/app/apikey")
                fallback_resp = self._fallback_response(prompt)
                return f"[FALLBACK]{fallback_resp}"
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("❌ OPENAI_API_KEY not set - using fallback response")
                logger.error("   Set with: export OPENAI_API_KEY='your-key'")
                fallback_resp = self._fallback_response(prompt)
                return f"[FALLBACK]{fallback_resp}"
        
        # Retry logic for rate limit errors
        max_retries = 29
        retry_delay = 30  # seconds
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"🤖 CALLING LLM: model={self.model}, prompt_length={len(prompt)} (attempt {attempt + 1}/{max_retries + 1})")
                logger.info(f"   API Key present: {bool(api_key)}")
                
                # Prepare API key for LiteLLM
                # For Gemini, LiteLLM reads from GOOGLE_API_KEY env var automatically
                # For OpenAI, we pass it via api_key parameter
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens
                }
                
                # Only set api_key explicitly for non-Gemini models
                if not self.is_gemini:
                    kwargs["api_key"] = api_key
                
                response = await acompletion(**kwargs)
                
                # Extract the response text
                response_text = response.choices[0].message.content
                logger.info(f"✅ LLM RESPONSE RECEIVED (length: {len(response_text)}):")
                logger.info(f"   {response_text[:500]}...")  # Print first 500 chars
                if len(response_text) > 500:
                    logger.info(f"   ... (truncated, total length: {len(response_text)})")
                
                return response_text
                
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
                    logger.warning(f"⚠️  Rate limit error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    logger.warning(f"   Waiting {retry_delay} seconds before retry...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    # Not a rate limit error, or max retries reached
                    if is_rate_limit:
                        logger.error(f"❌ Rate limit error persisted after {max_retries + 1} attempts. Using fallback response.")
                    else:
                        logger.error(f"LLM call failed: {e}", exc_info=True)
                        logger.error(f"Model: {self.model}, API Key present: {bool(api_key)}")
                    fallback_resp = self._fallback_response(prompt)
                    return f"[FALLBACK]{fallback_resp}"
        
        # Should never reach here, but just in case
        logger.error("❌ Max retries exceeded. Using fallback response.")
        fallback_resp = self._fallback_response(prompt)
        return f"[FALLBACK]{fallback_resp}"

    def _fallback_response(self, prompt: str) -> str:
        """
        Generate a fallback response when LLM is unavailable.
        
        This extracts key information from the prompt and generates
        a basic strategic response.
        """
        prompt_lower = prompt.lower()
        
        # Detect phase from prompt
        if "voting" in prompt_lower or "vote" in prompt_lower:
            return "ACTION: vote\nTARGET: agent_0\nREASONING: Voting for agent_0 based on suspicion."
        elif "discussion" in prompt_lower:
            return "ACTION: discuss\nTARGET: none\nREASONING: Observing and gathering information."
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
    
    async def get_response(self, prompt: str) -> str:
        """Return mock responses for testing."""
        self.call_count += 1
        self.last_prompt = prompt
        
        # Generate deterministic responses based on prompt content
        return self._fallback_response(prompt)


