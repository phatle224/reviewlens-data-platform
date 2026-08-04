"""Provider adapters for managed ReviewLens dependencies."""

from reviewlens.providers.r2 import R2Client, R2ObjectMetadata
from reviewlens.providers.snowflake import SnowflakeClient, SnowflakeProviderError

__all__ = ["R2Client", "R2ObjectMetadata", "SnowflakeClient", "SnowflakeProviderError"]
