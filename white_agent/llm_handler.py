"""LLM Handler using LiteLLM for White Agent responses."""

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
    
    # System prompt to enforce concise responses (cost savings)
    SYSTEM_PROMPT = """You are an AI playing a game of Werewolf. You must respond CONCISELY to save costs.

RESPONSE FORMAT RULES:
1. Keep responses under 100 words
2. Be direct - state your action clearly
3. Provide brief reasoning (1-2 sentences max)
4. Do NOT include unnecessary explanations

Your response should follow this structure:
ACTION: [your action type]
TARGET: [target player if applicable, otherwise "none"]
REASONING: [brief 1-2 sentence explanation]

Example response:
ACTION: vote
TARGET: agent_2
REASONING: Agent_2 has been suspiciously quiet and deflecting accusations."""

    def __init__(
        self,
        # model: str = "gpt-4o-mini", 
        model: str = "gpt-5.1",
        temperature: float = 0.7,
        max_tokens: int = 1000  # Enforce concise responses
    ):
        """
        Initialize the LLM handler.
        
        Args:
            model: The LiteLLM model to use (default: gpt-4o-mini)
            temperature: Response temperature (0.0-1.0)
            max_tokens: Maximum tokens in response (kept low for cost savings)
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Configure LiteLLM if available
        if LITELLM_AVAILABLE:
            # Set API key from environment
            litellm.api_key = os.getenv("OPENAI_API_KEY")
            # Enable caching for repeated similar prompts
            litellm.cache = None  # Disable for now, can enable for testing
            logger.info(f"LLM Handler initialized with model: {model}")
        else:
            logger.warning("Running in fallback mode without LLM")

    async def get_response(self, prompt: str) -> str:
        """
        Get a response from the LLM.
        
        Args:
            prompt: The prompt from the Green Agent
            
        Returns:
            The LLM response string
        """
        if not LITELLM_AVAILABLE:
            return self._fallback_response(prompt)
        
        try:
            response = await acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            # Extract the response text
            response_text = response.choices[0].message.content
            logger.debug(f"LLM response: {response_text}")
            
            return response_text
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return self._fallback_response(prompt)

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

