import hashlib
import logging
import os

import redis

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "3600"))
REDIS_CACHE_MAX_BYTES = int(
    os.getenv("REDIS_CACHE_MAX_BYTES", "5242880")
)

_client = None


def get_redis():
    global _client

    if _client is None:
        _client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            socket_connect_timeout=2,
            socket_timeout=3,
            decode_responses=False,
            health_check_interval=30,
        )

    return _client


def cache_key(data):
    digest = hashlib.sha256(data).hexdigest()
    return f"pdf-combiner:merge:{digest}"


def cache_get(key):
    try:
        return get_redis().get(key)
    except redis.RedisError:
        logger.warning("Redis cache read failed.", exc_info=True)
        return None


def cache_set(key, value):
    if len(value) > REDIS_CACHE_MAX_BYTES:
        return False

    try:
        get_redis().setex(key, REDIS_CACHE_TTL, value)
        return True
    except redis.RedisError:
        logger.warning("Redis cache write failed.", exc_info=True)
        return False


def cache_delete(key):
    try:
        get_redis().delete(key)
    except redis.RedisError:
        logger.warning("Redis cache delete failed.", exc_info=True)


def cache_ping():
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        logger.warning("Redis is unavailable.", exc_info=True)
        return False
