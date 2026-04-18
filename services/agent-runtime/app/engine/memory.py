"""
Long-term memory backed by pgvector.

Each agent has an isolated memory namespace. Memories are stored as vector
embeddings alongside text content and metadata. Retrieval uses cosine
similarity search.

Two storage tiers:
  1. Vector store (pgvector) — semantic similarity retrieval
  2. Relational store (asyncpg) — structured entity facts (key lookup)

The embedder is injected as a dependency so the memory service stays
provider-agnostic. Any callable that accepts a string and returns a
list[float] works as an embedder.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """
    A single memory record.

    category is used for filtering during retrieval. The categories match
    the architecture spec:
      task_summary    — what happened in a past run
      decision        — choices the agent made and why
      entity          — facts about people, projects, or systems
      conversation    — compressed conversation history
    """

    memory_id: str
    agent_id: str
    category: str
    content: str
    metadata: dict[str, Any]
    embedding: Optional[list[float]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.memory_id:
            raise ValueError("memory_id must not be empty")
        if not self.agent_id:
            raise ValueError("agent_id must not be empty")
        if not self.category:
            raise ValueError("category must not be empty")
        if not self.content:
            raise ValueError("content must not be empty")


# Embedder callable type: takes a string, returns a list of floats
EmbedderFn = Callable[[str], Any]  # async or sync

VALID_CATEGORIES = frozenset(
    {"task_summary", "decision", "entity", "conversation"}
)


class AgentMemory:
    """
    Manages an individual agent's long-term memory.

    Usage:
        memory = AgentMemory(agent_id, db_pool, vector_store, embedder)
        await memory.store("The auth service was down on Monday", {"run_id": "..."})
        results = await memory.search("authentication issues", top_k=5)
    """

    def __init__(
        self,
        agent_id: str,
        db_pool: Any,          # asyncpg Pool
        vector_store: Any,     # pgvector store, see below
        embedder: EmbedderFn,
    ) -> None:
        if not agent_id:
            raise ValueError("agent_id must not be empty")

        self._agent_id = agent_id
        self._db = db_pool
        self._vectors = vector_store
        self._embedder = embedder

    @property
    def agent_id(self) -> str:
        return self._agent_id

    async def store(
        self,
        content: str,
        metadata: dict[str, Any],
        category: str = "task_summary",
        memory_id: Optional[str] = None,
    ) -> MemoryEntry:
        """
        Embed content and persist it to the vector store.

        If memory_id is not supplied, a UUID is generated.
        Upserts: if a record with the same memory_id already exists it is
        replaced, so callers can use deterministic IDs (e.g. run_<run_id>)
        to avoid duplicate entries across retries.
        """
        if not content:
            raise ValueError("content must not be empty to store a memory")
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of: {sorted(VALID_CATEGORIES)}"
            )

        mid = memory_id or f"mem_{uuid.uuid4().hex}"
        embedding = await self._embed(content)

        entry = MemoryEntry(
            memory_id=mid,
            agent_id=self._agent_id,
            category=category,
            content=content,
            metadata=metadata,
            embedding=embedding,
        )

        await self._vectors.upsert(
            table="agent_memories",
            id=mid,
            agent_id=self._agent_id,
            category=category,
            content=content,
            embedding=embedding,
            metadata=metadata,
        )

        logger.debug(
            "Stored memory %s for agent %s (category=%s)",
            mid,
            self._agent_id,
            category,
        )
        return entry

    async def search(
        self,
        query: str,
        top_k: int = 5,
        categories: Optional[list[str]] = None,
    ) -> list[MemoryEntry]:
        """
        Retrieve memories relevant to query using cosine similarity.

        categories filters the search to a subset of memory categories.
        top_k is capped at 20 to prevent injecting overwhelming context.
        """
        if not query:
            raise ValueError("query must not be empty")
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")

        top_k = min(top_k, 20)

        if categories:
            invalid = set(categories) - VALID_CATEGORIES
            if invalid:
                raise ValueError(f"Invalid categories: {invalid}")

        query_embedding = await self._embed(query)

        rows = await self._vectors.search(
            table="agent_memories",
            agent_id=self._agent_id,
            query_embedding=query_embedding,
            top_k=top_k,
            categories=categories,
        )

        entries = [
            MemoryEntry(
                memory_id=row["id"],
                agent_id=self._agent_id,
                category=row["category"],
                content=row["content"],
                metadata=row.get("metadata", {}),
            )
            for row in rows
        ]

        logger.debug(
            "Memory search for agent %s returned %d results (top_k=%d)",
            self._agent_id,
            len(entries),
            top_k,
        )
        return entries

    async def forget(self, memory_id: str) -> bool:
        """
        Delete a specific memory by ID.

        Returns True if the record was found and deleted, False if it did not
        exist. Agents can be given tools that call this to correct bad memories.
        """
        if not memory_id:
            raise ValueError("memory_id must not be empty")

        deleted = await self._vectors.delete(
            table="agent_memories",
            id=memory_id,
            agent_id=self._agent_id,  # Enforce namespace — agents cannot delete others' memories
        )

        if deleted:
            logger.info("Deleted memory %s for agent %s", memory_id, self._agent_id)
        return deleted

    async def store_entity(
        self,
        entity_type: str,
        entity_id: str,
        facts: dict[str, Any],
    ) -> None:
        """
        Persist structured facts about an entity (person, project, system).

        Unlike vector memories, entity facts are stored in the relational DB
        and retrieved by exact (type, id) lookup — no embedding needed.
        Uses upsert semantics: repeated calls update the facts for the entity.
        """
        if not entity_type:
            raise ValueError("entity_type must not be empty")
        if not entity_id:
            raise ValueError("entity_id must not be empty")

        # Parameterized query — no string concatenation
        await self._db.execute(
            """
            INSERT INTO agent_entities (agent_id, entity_type, entity_id, facts, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, NOW())
            ON CONFLICT (agent_id, entity_type, entity_id)
            DO UPDATE SET facts = EXCLUDED.facts, updated_at = NOW()
            """,
            self._agent_id,
            entity_type,
            entity_id,
            facts,
        )

    async def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve entity facts by exact lookup. Returns None if not found."""
        if not entity_type or not entity_id:
            raise ValueError("entity_type and entity_id must not be empty")

        row = await self._db.fetchrow(
            """
            SELECT facts FROM agent_entities
            WHERE agent_id = $1 AND entity_type = $2 AND entity_id = $3
            """,
            self._agent_id,
            entity_type,
            entity_id,
        )
        return dict(row["facts"]) if row else None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> list[float]:
        """Run the embedder, handling both sync and async callables."""
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(self._embedder):
            return await self._embedder(text)
        # Sync embedder — run in thread pool to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embedder, text)
