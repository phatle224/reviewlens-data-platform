"""Provider adapters for managed ReviewLens dependencies."""

from reviewlens.providers.audit import (
    AuditEvent,
    AuditOutcome,
    AuditRecorder,
    AuditSink,
    InMemoryAuditSink,
)
from reviewlens.providers.chroma import (
    AUTHORITATIVE_RAG_SOURCE,
    ChromaMatch,
    ChromaProviderError,
    ChromaVectorRecord,
    ChromaVectorStore,
    versioned_collection_name,
)
from reviewlens.providers.openrouter import (
    AIDataClass,
    ApprovedAIText,
    ChatCompletion,
    ChatMessage,
    ChatRole,
    EmbeddingBatch,
    OpenRouterClient,
    OpenRouterProviderError,
    OpenRouterTask,
    TokenUsage,
)
from reviewlens.providers.r2 import (
    R2AccessPolicyError,
    R2Client,
    R2ObjectMetadata,
    R2RuntimePurpose,
)
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeProviderError

__all__ = [
    "AUTHORITATIVE_RAG_SOURCE",
    "AIDataClass",
    "ApprovedAIText",
    "AuditEvent",
    "AuditOutcome",
    "AuditRecorder",
    "AuditSink",
    "ChatCompletion",
    "ChatMessage",
    "ChatRole",
    "ChromaMatch",
    "ChromaProviderError",
    "ChromaVectorRecord",
    "ChromaVectorStore",
    "EmbeddingBatch",
    "InMemoryAuditSink",
    "OpenRouterClient",
    "OpenRouterProviderError",
    "OpenRouterTask",
    "R2AccessPolicyError",
    "R2Client",
    "R2ObjectMetadata",
    "R2RuntimePurpose",
    "SnowflakeClient",
    "SnowflakeProviderError",
    "TokenUsage",
    "versioned_collection_name",
]
