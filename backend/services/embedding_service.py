"""
Hybrid embedding service supporting both local and cloud providers.

Automatically switches between modes for privacy flexibility:
- Local: sentence-transformers (fully offline)
- Cloud: OpenAI API (higher quality, requires API key)
"""

import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional

import numpy as np
from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer

from core.config import Settings, get_settings


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""
    
    @abstractmethod
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a list of texts."""
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimension of embeddings."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider using sentence-transformers.
    Fully offline - no API calls required.
    """
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._dimension: Optional[int] = None
    
    def _load_model(self) -> SentenceTransformer:
        """Lazy load the model."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()
        return self._model
    
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using local model."""
        # Load model + encode entirely in a worker thread — SentenceTransformer()
        # and first encode can take minutes on cold start; if run on the event loop,
        # /health and other requests time out (verify_system.py, browsers).
        loop = asyncio.get_running_loop()
        batch_size = min(128, max(1, len(texts)))

        def _encode() -> np.ndarray:
            model = self._load_model()
            return model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

        return await loop.run_in_executor(None, _encode)
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._dimension is None:
            self._load_model()
        return self._dimension
    
    def is_available(self) -> bool:
        """Local embeddings are always available."""
        return True


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    Cloud embedding provider using OpenAI API.
    Requires API key.
    """
    
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self._dimension = self._get_dimension_for_model(model)
    
    def _get_dimension_for_model(self, model: str) -> int:
        """Get dimension for known models."""
        dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dimensions.get(model, 1536)
    
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using OpenAI API."""
        all_embeddings = []
        
        # Process in batches of 100 (OpenAI limit)
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            response = await self.client.embeddings.create(
                model=self.model,
                input=batch
            )
            
            batch_embeddings = [
                item.embedding for item in response.data
            ]
            all_embeddings.extend(batch_embeddings)
        
        return np.array(all_embeddings)
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.client.api_key)


class HybridEmbeddingService:
    """
    Hybrid embedding service that switches between local and cloud providers.
    
    Modes:
    - "local": Always use local embeddings (private mode)
    - "cloud": Always use cloud embeddings if available
    - "auto": Prefer local, fallback to cloud if configured
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._providers: dict[str, EmbeddingProvider] = {}
        self._active_mode: str = "local"
        
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize available providers."""
        # Local provider is always available
        self._providers["local"] = LocalEmbeddingProvider(
            self.settings.LOCAL_EMBED_MODEL
        )
        
        # Cloud provider if API key available
        if self.settings.OPENAI_API_KEY:
            self._providers["cloud"] = OpenAIEmbeddingProvider(
                self.settings.OPENAI_API_KEY,
                self.settings.CLOUD_EMBED_MODEL
            )
        
        # Set initial mode based on settings
        mode = self.settings.OPERATION_MODE
        if mode == "private":
            self._active_mode = "local"
        elif mode == "cloud":
            self._active_mode = "cloud" if "cloud" in self._providers else "local"
        else:  # hybrid
            self._active_mode = "local"  # Default to local for privacy
    
    async def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using active provider."""
        provider = self._providers.get(self._active_mode)
        if provider is None:
            raise RuntimeError(f"No embedding provider available for mode: {self._active_mode}")
        
        return await provider.embed(texts)
    
    async def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query."""
        embeddings = await self.embed([query])
        return embeddings[0]
    
    def switch_mode(self, mode: str):
        """
        Switch embedding mode.
        
        Args:
            mode: "local" or "cloud"
        """
        if mode not in self._providers:
            available = list(self._providers.keys())
            raise ValueError(f"Mode '{mode}' not available. Available: {available}")
        
        self._active_mode = mode
    
    def get_available_modes(self) -> List[str]:
        """Return list of available embedding modes."""
        return list(self._providers.keys())
    
    @property
    def current_mode(self) -> str:
        """Return current active mode."""
        return self._active_mode
    
    @property
    def dimension(self) -> int:
        """Return embedding dimension for active provider."""
        return self._providers[self._active_mode].dimension
    
    def get_provider_info(self) -> dict:
        """Get information about available providers."""
        return {
            "current_mode": self._active_mode,
            "available_modes": self.get_available_modes(),
            "dimension": self.dimension,
            "local_model": self.settings.LOCAL_EMBED_MODEL,
            "cloud_model": self.settings.CLOUD_EMBED_MODEL if "cloud" in self._providers else None
        }


# Singleton instance
_embedding_service: Optional[HybridEmbeddingService] = None


def get_embedding_service() -> HybridEmbeddingService:
    """Get or create embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = HybridEmbeddingService()
    return _embedding_service


def reset_embedding_service():
    """Reset singleton (useful for testing)."""
    global _embedding_service
    _embedding_service = None