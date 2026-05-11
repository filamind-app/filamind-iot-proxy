"""Redis-backed TTL store for pairing codes.

Postgres is the source of truth (PairingCode rows live forever once
written). Redis is a fast lookup cache: `pair:<code> -> box_id` with
TTL = pairing_code_ttl_seconds. The polling endpoint hits Redis first
and falls back to Postgres if the key has expired.
"""
from __future__ import annotations

import redis.asyncio as redis

from api.config import get_settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        s = get_settings()
        _client = redis.Redis(
            host=s.redis_host,
            port=s.redis_port,
            db=s.redis_db,
            decode_responses=True,
        )
    return _client


def reset_redis_for_tests(client: redis.Redis) -> None:
    """Replace the module-level client with a fake (e.g. fakeredis)."""
    global _client
    _client = client


def _key(code: str) -> str:
    return f"pair:{code}"


async def cache_pairing_code(code: str, box_id: str, ttl_seconds: int) -> None:
    await get_redis().set(_key(code), box_id, ex=ttl_seconds)


async def lookup_pairing_code(code: str) -> str | None:
    return await get_redis().get(_key(code))


async def invalidate_pairing_code(code: str) -> None:
    await get_redis().delete(_key(code))
