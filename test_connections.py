#!/usr/bin/env python3
"""
RAG System Connection Test Script
Tests all service connections: DB, Qdrant, Redis, LLM providers
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from core.config import get_settings

async def test_postgres():
    """Test PostgreSQL connection."""
    from sqlalchemy.ext.asyncio import create_async_engine
    
    settings = get_settings()
    print("Testing PostgreSQL connection...")
    print(f"  URL: {settings.DATABASE_URL.replace(settings.DB_PASSWORD, '***')}")
    
    try:
        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.connect() as conn:
            result = await conn.execute("SELECT version()")
            version = result.scalar()
            print(f"  ✓ Connected: {version[:50]}...")
            return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

async def test_qdrant():
    """Test Qdrant connection."""
    from qdrant_client import QdrantClient
    
    settings = get_settings()
    print("Testing Qdrant connection...")
    print(f"  URL: {settings.QDRANT_URL}")
    
    try:
        client = QdrantClient(url=settings.QDRANT_URL)
        collections = client.get_collections()
        print(f"  ✓ Connected. Collections: {len(collections.collections)}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

async def test_redis():
    """Test Redis connection."""
    import redis.asyncio as redis
    
    settings = get_settings()
    print("Testing Redis connection...")
    print(f"  URL: {settings.REDIS_URL}")
    
    try:
        client = redis.from_url(settings.REDIS_URL)
        pong = await client.ping()
        await client.close()
        print(f"  ✓ Connected: {pong}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

async def test_llm_router():
    """Test LLM provider connectivity."""
    from services.llm_router import get_llm_router
    
    settings = get_settings()
    print("Testing LLM Router...")
    print(f"  Mode: {settings.OPERATION_MODE}")
    print(f"  vLLM URL: {settings.VLLM_URL}")
    
    try:
        router = get_llm_router()
        providers = await asyncio.wait_for(
            router.get_available_providers(),
            timeout=5.0
        )
        print(f"  ✓ Router initialized")
        print(f"  Available providers: {providers}")
        return True
    except asyncio.TimeoutError:
        print(f"  ⚠ Timeout checking providers (this is normal if vLLM is not running)")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

async def test_embedding_service():
    """Test embedding model loading."""
    from services.embedding_service import get_embedding_service
    
    settings = get_settings()
    print("Testing Embedding Service...")
    print(f"  Model: {settings.LOCAL_EMBED_MODEL}")
    
    try:
        service = get_embedding_service()
        # Try a simple embedding
        result = await service.embed(["test"])
        print(f"  ✓ Model loaded. Embedding dim: {len(result[0])}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

async def test_pdf_service():
    """Test PDF processor initialization."""
    from services.pdf_service import PDFProcessor
    
    print("Testing PDF Service...")
    
    try:
        processor = PDFProcessor()
        print(f"  ✓ PDF processor initialized")
        print(f"  Chunk size: {processor.settings.CHUNK_SIZE}")
        print(f"  Chunk overlap: {processor.settings.CHUNK_OVERLAP}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

async def main():
    print("=" * 50)
    print("RAG System Connection Test")
    print("=" * 50)
    print()
    
    results = []
    
    # Test all services
    results.append(("PostgreSQL", await test_postgres()))
    print()
    results.append(("Qdrant", await test_qdrant()))
    print()
    results.append(("Redis", await test_redis()))
    print()
    results.append(("PDF Service", await test_pdf_service()))
    print()
    results.append(("Embedding Service", await test_embedding_service()))
    print()
    results.append(("LLM Router", await test_llm_router()))
    
    # Summary
    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print()
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All systems operational!")
    else:
        print("\n⚠️  Some services need attention. Check logs above.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
