"""
LLM Router for hybrid local/cloud operation.

Supports:
- vLLM for local/private inference
- OpenRouter for cloud access to multiple providers
- Automatic fallback and mode switching
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from openai import AsyncOpenAI

from core.config import Settings, get_settings


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    text: str
    model_used: str
    provider: str  # "vllm" or "openrouter"
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw_response: Optional[Any] = None


class LLMProvider(ABC):
    """Abstract base for LLM providers."""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000
    ) -> LLMResponse:
        """Generate completion."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is healthy."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get provider name."""
        pass


class VLLMProvider(LLMProvider):
    """
    Local vLLM inference.
    Requires vLLM server to be running.
    """
    
    def __init__(self, base_url: str = None, model: str = None):
        settings = get_settings()
        self.base_url = base_url or settings.VLLM_URL
        self.model = model or settings.VLLM_MODEL
        self._detected_model: Optional[str] = None
        
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key="not-needed",  # vLLM doesn't require auth locally
            timeout=30.0
        )
    
    async def _detect_model(self) -> str:
        """Auto-detect which model vLLM is serving."""
        if self._detected_model is None:
            try:
                models = await self.client.models.list()
                if models.data:
                    self._detected_model = models.data[0].id
                else:
                    self._detected_model = self.model or "unknown"
            except Exception:
                # vLLM not available - use configured model name
                self._detected_model = self.model or "unknown"
        return self._detected_model
    
    async def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000
    ) -> LLMResponse:
        """Generate using vLLM."""
        model = await self._detect_model()
        
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        start_time = time.time()
        
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return LLMResponse(
            text=response.choices[0].message.content,
            model_used=f"vllm/{model}",
            provider="vllm",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            latency_ms=latency_ms,
            raw_response=response
        )
    
    async def is_available(self) -> bool:
        """Check if vLLM server is responsive."""
        try:
            # Use a short timeout to avoid hanging
            import asyncio
            await asyncio.wait_for(
                self.client.models.list(),
                timeout=1.0
            )
            return True
        except (asyncio.TimeoutError, Exception):
            # vLLM not available - this is expected when vLLM isn't running
            # Suppress logging to avoid noise in logs
            return False
    
    def get_name(self) -> str:
        return "vLLM (Local)"


class OpenRouterProvider(LLMProvider):
    """
    Cloud inference via OpenRouter.
    Provides access to multiple LLM providers.
    """
    
    # Shared across Entity Extractor, RAG DocuMind, Extract Entities modal
    AVAILABLE_MODELS = {
        "openai/gpt-4o-mini": "GPT-4o mini (fast / draft)",
        "moonshotai/kimi-k2.5": "Kimi",
        "minimax/minimax-m2.5": "Minimax",
        "anthropic/claude-3.5-sonnet": "Sonnet",
    }
    
    def __init__(self, api_key: str = None, model: str = None):
        settings = get_settings()
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.model = model or settings.DEFAULT_CLOUD_MODEL
        
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            timeout=60.0
        )
    
    async def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000
    ) -> LLMResponse:
        """Generate using OpenRouter."""
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        start_time = time.time()
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_headers={
                "HTTP-Referer": "https://docu-mind.local",
                "X-Title": "FIND Tools",
            }
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return LLMResponse(
            text=response.choices[0].message.content,
            model_used=response.model,
            provider="openrouter",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            latency_ms=latency_ms,
            raw_response=response
        )
    
    async def is_available(self) -> bool:
        """Check if API key is valid. Short timeout to avoid blocking health checks."""
        if not self.api_key:
            return False
        try:
            import asyncio
            await asyncio.wait_for(
                self.client.models.list(),
                timeout=2.0  # Match vLLM-style quick check; health wraps in 3s
            )
            return True
        except (asyncio.TimeoutError, Exception):
            return False
    
    def get_name(self) -> str:
        model_name = self.AVAILABLE_MODELS.get(self.model, self.model)
        return f"OpenRouter: {model_name}"
    
    def list_available_models(self) -> Dict[str, str]:
        """Return dict of model IDs to display names."""
        return self.AVAILABLE_MODELS.copy()


class LLMRouter:
    """
    Routes to available LLM providers with automatic fallback.
    
    Priority order based on operation mode:
    - "private": vLLM only (fails if unavailable)
    - "hybrid": vLLM -> OpenRouter (fallback)
    - "cloud": OpenRouter only
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._providers: Dict[str, LLMProvider] = {}
        self._active_provider: Optional[str] = None
        
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize providers based on settings."""
        mode = self.settings.OPERATION_MODE
        
        # vLLM is opt-in (ENABLE_VLLM) so cloud deploys stay OpenRouter-only
        if mode in ("private", "hybrid") and self.settings.ENABLE_VLLM:
            vllm = VLLMProvider()
            self._providers["vllm"] = vllm
        
        # Initialize OpenRouter for cloud/hybrid modes
        if mode in ("cloud", "hybrid"):
            if self.settings.OPENROUTER_API_KEY:
                openrouter = OpenRouterProvider()
                self._providers["openrouter"] = openrouter
        
        # Set default provider
        if mode == "private":
            self._active_provider = "vllm" if "vllm" in self._providers else "openrouter"
        elif mode == "cloud":
            self._active_provider = "openrouter"
        else:  # hybrid — prefer local only when vLLM is registered
            self._active_provider = "vllm" if "vllm" in self._providers else "openrouter"
    
    def _get_provider_for_model(self, model: Optional[str] = None) -> tuple[LLMProvider, Optional[str]]:
        """
        Get the appropriate provider and model for a request.
        
        Args:
            model: Optional model override (e.g., "openai/gpt-4o", "anthropic/claude-3.5-sonnet")
        
        Returns:
            Tuple of (provider, model_name) where model_name may be None for default
        """
        if not model:
            # When frontend hasn't loaded models yet (refresh), use cloud default so OpenRouter
            # gets traffic instead of vLLM. Otherwise use active provider.
            if "openrouter" in self._providers:
                return self._providers["openrouter"], self.settings.DEFAULT_CLOUD_MODEL
            return self._providers[self._active_provider], None
        
        # Check if it's an OpenRouter model
        if "/" in model and "openrouter" in self._providers:
            return self._providers["openrouter"], model
        
        # Check if it's a vLLM model reference
        if "vllm" in self._providers:
            return self._providers["vllm"], model
        
        # Fallback to default provider
        return self._providers[self._active_provider], None
    
    def list_available_models(self) -> List[Dict[str, str]]:
        """List all available models from all providers."""
        models = []
        
        # Add OpenRouter models
        if "openrouter" in self._providers:
            openrouter = self._providers["openrouter"]
            if isinstance(openrouter, OpenRouterProvider):
                for model_id, display_name in openrouter.list_available_models().items():
                    models.append({
                        "id": model_id,
                        "name": display_name,
                        "provider": "openrouter"
                    })
        
        # Add vLLM option
        if "vllm" in self._providers:
            models.append({
                "id": "vllm/local",
                "name": "vLLM (Local)",
                "provider": "vllm"
            })
        
        return models
    
    async def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> LLMResponse:
        """
        Generate completion using active provider.
        Falls back to alternative in hybrid mode if primary fails.

        Args:
            prompt: The prompt to generate from
            system_message: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            model: Optional model override (e.g., "openai/gpt-4o")
        """
        temp = temperature or self.settings.LLM_TEMPERATURE
        max_tok = max_tokens or self.settings.LLM_MAX_TOKENS

        # Get the appropriate provider and model
        provider, model_override = self._get_provider_for_model(model)

        # If we have a model override, create a temporary provider instance
        if model_override and model_override != "vllm/local":
            if isinstance(provider, OpenRouterProvider):
                provider = OpenRouterProvider(model=model_override)

        try:
            if await provider.is_available():
                return await provider.generate(
                    prompt, system_message, temp, max_tok
                )
        except Exception as e:
            # Provider failed - try fallback if hybrid
            if self.settings.OPERATION_MODE == "hybrid":
                fallback = self._get_fallback_provider()
                if fallback and await fallback.is_available():
                    return await fallback.generate(
                        prompt, system_message, temp, max_tok
                    )
            raise

        # Provider is not available - try fallback in hybrid mode
        if self.settings.OPERATION_MODE == "hybrid":
            fallback = self._get_fallback_provider()
            if fallback and await fallback.is_available():
                return await fallback.generate(
                    prompt, system_message, temp, max_tok
                )

        raise RuntimeError("No LLM provider available")
    
    def _get_fallback_provider(self) -> Optional[LLMProvider]:
        """Get fallback provider for hybrid mode."""
        for name, provider in self._providers.items():
            if name != self._active_provider:
                return provider
        return None
    
    async def get_available_providers(self) -> Dict[str, dict]:
        """Get status of all providers."""
        result = {}
        for name, provider in self._providers.items():
            result[name] = {
                "name": provider.get_name(),
                "available": await provider.is_available(),
                "active": name == self._active_provider
            }
        return result
    
    def switch_provider(self, provider_name: str):
        """Manually switch active provider."""
        if provider_name not in self._providers:
            available = list(self._providers.keys())
            raise ValueError(
                f"Provider '{provider_name}' not available. "
                f"Available: {available}"
            )
        self._active_provider = provider_name
    
    @property
    def active_provider_name(self) -> Optional[str]:
        """Get name of currently active provider."""
        return self._active_provider
    
    @property
    def operation_mode(self) -> str:
        """Get current operation mode."""
        return self.settings.OPERATION_MODE


# Singleton instance
_llm_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Get or create LLM router singleton."""
    global _llm_router
    if _llm_router is None:
        _llm_router = LLMRouter()
    return _llm_router


def reset_llm_router():
    """Reset singleton (useful for testing)."""
    global _llm_router
    _llm_router = None