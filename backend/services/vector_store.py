"""
Vector store implementations: Qdrant and pgvector.

Both support:
- Async operations
- Document filtering
- Page metadata storage
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from dataclasses import dataclass

import numpy as np
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from core.config import get_settings
from models.schemas import Chunk


@dataclass
class SearchResult:
    """Result from vector search."""
    chunk_id: str
    document_id: UUID
    chunk_index: int
    text: str
    start_page: int
    end_page: int
    score: float
    token_count: int


class VectorStore(ABC):
    """Abstract vector store interface."""
    
    @abstractmethod
    async def upsert(
        self,
        document_id: UUID,
        chunks: List[Chunk],
        embeddings: np.ndarray
    ) -> List[str]:
        """Store chunks with embeddings. Returns point IDs."""
        pass
    
    @abstractmethod
    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        document_filter: Optional[UUID] = None
    ) -> List[SearchResult]:
        """Search for similar chunks."""
        pass
    
    @abstractmethod
    async def delete_document(self, document_id: UUID) -> bool:
        """Delete all chunks for a document."""
        pass
    
    @abstractmethod
    async def get_chunk(self, chunk_id: str) -> Optional[SearchResult]:
        """Get a specific chunk by ID."""
        pass


class QdrantStore(VectorStore):
    """
    Qdrant vector store implementation.
    Fast, scalable, easy to deploy.
    """
    
    def __init__(self, url: str = None, collection: str = None, dimension: int = None):
        settings = get_settings()
        self.url = url or settings.QDRANT_URL
        self.collection = collection or settings.QDRANT_COLLECTION
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self._client: Optional[AsyncQdrantClient] = None
    
    @property
    def client(self) -> AsyncQdrantClient:
        """Lazy initialization of Qdrant client."""
        if self._client is None:
            self._client = AsyncQdrantClient(url=self.url, timeout=30.0)
        return self._client
    
    async def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        collections = await self.client.get_collections()
        collection_names = [c.name for c in collections.collections]
        
        if self.collection not in collection_names:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.dimension,
                    distance=Distance.COSINE
                )
            )
    
    async def upsert(
        self,
        document_id: UUID,
        chunks: List[Chunk],
        embeddings: np.ndarray
    ) -> List[str]:
        """Store chunks in Qdrant."""
        await self._ensure_collection()
        
        points = []
        point_ids = []
        
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Globally unique ID: hash of document_id + chunk index
            # prevents overwrites when multiple documents are indexed
            import hashlib
            unique_seed = f"{document_id}_{i}".encode()
            point_id = str(UUID(bytes=hashlib.md5(unique_seed).digest()))
            point_ids.append(point_id)
            
            points.append(PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload={
                    "document_id": str(document_id),
                    "chunk_index": chunk.index,
                    "start_page": chunk.start_page,
                    "end_page": chunk.end_page,
                    "text": chunk.text,
                    "token_count": chunk.token_count,
                    "section_title": getattr(chunk, "section_title", None),
                    "chunk_strategy": getattr(chunk, "chunk_strategy", None),
                }
            ))
        
        await self.client.upsert(
            collection_name=self.collection,
            points=points
        )
        
        return point_ids
    
    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        document_filter: Optional[UUID] = None
    ) -> List[SearchResult]:
        """Search for similar chunks."""
        query_filter = None
        if document_filter:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=str(document_filter))
                    )
                ]
            )
        
        results = await self.client.search(
            collection_name=self.collection,
            query_vector=query_embedding.tolist(),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True
        )
        
        return [
            SearchResult(
                chunk_id=str(r.id),
                document_id=UUID(r.payload["document_id"]),
                chunk_index=r.payload["chunk_index"],
                text=r.payload["text"],
                start_page=r.payload["start_page"],
                end_page=r.payload["end_page"],
                score=r.score,
                token_count=r.payload.get("token_count", 0)
            )
            for r in results
        ]
    
    async def delete_document(self, document_id: UUID) -> bool:
        """Delete all chunks for a document."""
        await self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=str(document_id))
                    )
                ]
            )
        )
        return True
    
    async def get_chunk(self, chunk_id: str) -> Optional[SearchResult]:
        """Get a specific chunk by ID."""
        points = await self.client.retrieve(
            collection_name=self.collection,
            ids=[chunk_id],
            with_payload=True
        )
        
        if not points:
            return None
        
        point = points[0]
        return SearchResult(
            chunk_id=str(point.id),
            document_id=UUID(point.payload["document_id"]),
            chunk_index=point.payload["chunk_index"],
            text=point.payload["text"],
            start_page=point.payload["start_page"],
            end_page=point.payload["end_page"],
            score=1.0,
            token_count=point.payload.get("token_count", 0)
        )


class PGVectorStore(VectorStore):
    """
    PostgreSQL + pgvector implementation.
    Good for existing Postgres infrastructure.
    """
    
    def __init__(self, session: AsyncSession, dimension: int = None):
        self.session = session
        self.dimension = dimension or get_settings().EMBEDDING_DIMENSION
    
    async def upsert(
        self,
        document_id: UUID,
        chunks: List[Chunk],
        embeddings: np.ndarray
    ) -> List[str]:
        """Store chunks in pgvector."""
        point_ids = []
        
        for chunk, embedding in zip(chunks, embeddings):
            point_id = str(UUID(int=chunk.index))
            point_ids.append(point_id)
            
            await self.session.execute(
                text("""
                    INSERT INTO document_embeddings 
                    (id, document_id, chunk_index, start_page, end_page, 
                     text_content, embedding, token_count)
                    VALUES (:id, :doc_id, :idx, :start_p, :end_p, :text, :embedding, :tokens)
                    ON CONFLICT (id) DO UPDATE SET
                        text_content = EXCLUDED.text_content,
                        embedding = EXCLUDED.embedding
                """),
                {
                    "id": point_id,
                    "doc_id": str(document_id),
                    "idx": chunk.index,
                    "start_p": chunk.start_page,
                    "end_p": chunk.end_page,
                    "text": chunk.text,
                    "embedding": embedding.tolist(),
                    "tokens": chunk.token_count
                }
            )
        
        await self.session.commit()
        return point_ids
    
    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        document_filter: Optional[UUID] = None
    ) -> List[SearchResult]:
        """Search using cosine similarity."""
        query = """
            SELECT id, document_id, chunk_index, start_page, end_page,
                   text_content, token_count,
                   1 - (embedding <=> :query_embedding) as score
            FROM document_embeddings
            WHERE 1=1
        """
        params = {
            "query_embedding": str(query_embedding.tolist()),
            "top_k": top_k
        }
        
        if document_filter:
            query += " AND document_id = :doc_id"
            params["doc_id"] = str(document_filter)
        
        query += """
            ORDER BY embedding <=> :query_embedding
            LIMIT :top_k
        """
        
        result = await self.session.execute(text(query), params)
        rows = result.fetchall()
        
        return [
            SearchResult(
                chunk_id=row.id,
                document_id=UUID(row.document_id),
                chunk_index=row.chunk_index,
                text=row.text_content,
                start_page=row.start_page,
                end_page=row.end_page,
                score=float(row.score),
                token_count=row.token_count
            )
            for row in rows
        ]
    
    async def delete_document(self, document_id: UUID) -> bool:
        """Delete all chunks for a document."""
        await self.session.execute(
            text("DELETE FROM document_embeddings WHERE document_id = :doc_id"),
            {"doc_id": str(document_id)}
        )
        await self.session.commit()
        return True
    
    async def get_chunk(self, chunk_id: str) -> Optional[SearchResult]:
        """Get a specific chunk by ID."""
        result = await self.session.execute(
            text("""
                SELECT id, document_id, chunk_index, start_page, end_page,
                       text_content, token_count
                FROM document_embeddings
                WHERE id = :chunk_id
            """),
            {"chunk_id": chunk_id}
        )
        row = result.fetchone()
        
        if not row:
            return None
        
        return SearchResult(
            chunk_id=row.id,
            document_id=UUID(row.document_id),
            chunk_index=row.chunk_index,
            text=row.text_content,
            start_page=row.start_page,
            end_page=row.end_page,
            score=1.0,
            token_count=row.token_count
        )


class Neo4jVectorStore(VectorStore):
    """
    Neo4j native vector index implementation.

    Stores chunk embeddings alongside the knowledge graph so a single
    Cypher query can do vector search + graph traversal.  Set
    VECTOR_STORE_TYPE=neo4j to use instead of Qdrant.

    Requires Neo4j >= 5.11 with a vector index created on (:Chunk {embedding}).
    The graphrag_service.ensure_indexes() call on startup handles index creation.
    """

    def __init__(self):
        from neo4j import GraphDatabase

        settings = get_settings()
        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
        )
        self._index_name = settings.NEO4J_VECTOR_INDEX
        # text-embedding-3-small = 1536; local MiniLM = 384
        self._dimension = settings.EMBEDDING_DIMENSION

    async def upsert(
        self,
        document_id: UUID,
        chunks: List[Chunk],
        embeddings: np.ndarray,
    ) -> List[str]:
        """Store chunks as :Chunk nodes with embedding property."""
        import hashlib

        point_ids: List[str] = []
        with self._driver.session() as session:
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                unique_seed = f"{document_id}_{i}".encode()
                point_id = str(UUID(bytes=hashlib.md5(unique_seed).digest()))
                point_ids.append(point_id)

                session.run(
                    """
                    MERGE (c:Chunk {id: $id})
                    SET c.document_id = $doc_id,
                        c.chunk_index = $idx,
                        c.start_page  = $start_p,
                        c.end_page    = $end_p,
                        c.text        = $text,
                        c.token_count = $tokens,
                        c.embedding   = $embedding
                    """,
                    id=point_id,
                    doc_id=str(document_id),
                    idx=chunk.index,
                    start_p=chunk.start_page,
                    end_p=chunk.end_page,
                    text=chunk.text,
                    tokens=chunk.token_count,
                    embedding=embedding.tolist(),
                )

        return point_ids

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        document_filter: Optional[UUID] = None,
    ) -> List[SearchResult]:
        """Approximate nearest-neighbour search via Neo4j vector index."""
        with self._driver.session() as session:
            # Vector index query — returns nodes + similarity score
            cypher = """
            CALL db.index.vector.queryNodes($index, $k, $vec)
            YIELD node, score
            """
            if document_filter:
                cypher += " WHERE node.document_id = $doc_id"
            cypher += """
            RETURN node.id         AS id,
                   node.document_id AS document_id,
                   node.chunk_index AS chunk_index,
                   node.text        AS text,
                   node.start_page  AS start_page,
                   node.end_page    AS end_page,
                   node.token_count AS token_count,
                   score
            ORDER BY score DESC
            LIMIT $k
            """

            params = {
                "index": self._index_name,
                "k": top_k,
                "vec": query_embedding.tolist(),
            }
            if document_filter:
                params["doc_id"] = str(document_filter)

            result = session.run(cypher, **params)
            return [
                SearchResult(
                    chunk_id=r["id"],
                    document_id=UUID(r["document_id"]),
                    chunk_index=r["chunk_index"],
                    text=r["text"],
                    start_page=r["start_page"],
                    end_page=r["end_page"],
                    score=float(r["score"]),
                    token_count=r.get("token_count", 0),
                )
                for r in result
            ]

    async def delete_document(self, document_id: UUID) -> bool:
        """Delete all chunk nodes for a document."""
        with self._driver.session() as session:
            session.run(
                "MATCH (c:Chunk {document_id: $doc_id}) DETACH DELETE c",
                doc_id=str(document_id),
            )
        return True

    async def get_chunk(self, chunk_id: str) -> Optional[SearchResult]:
        """Get a specific chunk by its ID property."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (c:Chunk {id: $id})
                RETURN c.id AS id, c.document_id AS document_id,
                       c.chunk_index AS chunk_index, c.text AS text,
                       c.start_page AS start_page, c.end_page AS end_page,
                       c.token_count AS token_count
                """,
                id=chunk_id,
            )
            record = result.single()
            if not record:
                return None
            return SearchResult(
                chunk_id=record["id"],
                document_id=UUID(record["document_id"]),
                chunk_index=record["chunk_index"],
                text=record["text"],
                start_page=record["start_page"],
                end_page=record["end_page"],
                score=1.0,
                token_count=record.get("token_count", 0),
            )


def create_vector_store(
    store_type: str = None,
    session: AsyncSession = None
) -> VectorStore:
    """
    Factory function to create appropriate vector store.

    Args:
        store_type: "qdrant", "pgvector", or "neo4j"
        session: Required for pgvector
    """
    settings = get_settings()
    store_type = store_type or settings.VECTOR_STORE_TYPE

    if store_type == "qdrant":
        return QdrantStore()
    elif store_type == "pgvector":
        if session is None:
            raise ValueError("AsyncSession required for pgvector")
        return PGVectorStore(session)
    elif store_type == "neo4j":
        return Neo4jVectorStore()
    else:
        raise ValueError(f"Unknown vector store type: {store_type}")
