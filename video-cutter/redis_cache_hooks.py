import logging
from flask import request, Response
from redis_cache import cache_key, cache_get, cache_set, CACHE_MAX_BYTES

logger = logging.getLogger(__name__)


def init_redis_cache(app, service_name):
    @app.before_request
    def _redis_cache_before_request():
        if request.method != "POST":
            return None
        if not request.mimetype or request.mimetype != "multipart/form-data":
            return None

        try:
            body = request.get_data(cache=True)
            settings = {
                "path": request.path,
                "query": request.query_string.decode("latin1"),
                "content_type": request.mimetype,
            }
            key = cache_key(service_name, body, settings)
            cached = cache_get(key)

            if cached is not None:
                logger.info("Redis cache HIT: %s", key)
                return Response(
                    cached,
                    status=200,
                    content_type="application/octet-stream",
                    headers={"X-Redis-Cache": "HIT"},
                )

            request.environ["redis_cache_key"] = key
            logger.info("Redis cache MISS: %s", key)

        except Exception:
            logger.exception("Redis cache lookup failed")

        return None

    @app.after_request
    def _redis_cache_after_request(response):
        key = request.environ.pop("redis_cache_key", None)

        if not key:
            return response

        if request.method != "POST" or response.status_code != 200:
            logger.info(
                "Redis cache skipped: status=%s",
                response.status_code,
            )
            return response

        try:
            data = response.get_data()
            if not data:
                logger.info("Redis cache skipped: empty response")
                return response

            if len(data) > CACHE_MAX_BYTES:
                logger.info(
                    "Redis cache skipped: response size %s exceeds limit %s",
                    len(data),
                    CACHE_MAX_BYTES,
                )
                return response

            if cache_set(key, data):
                response.headers["X-Redis-Cache"] = "MISS"
                logger.info("Redis cache stored: %s (%s bytes)", key, len(data))
            else:
                logger.error("Redis cache write failed: %s", key)

        except Exception:
            logger.exception("Redis cache write failed")

        return response
