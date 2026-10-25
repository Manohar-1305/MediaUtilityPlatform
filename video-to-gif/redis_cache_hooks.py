from flask import request, Response
from redis_cache import cache_key, cache_get, cache_set

MAX_CACHE_BYTES = int(
    __import__("os").getenv(
        "REDIS_CACHE_MAX_BYTES", str(100 * 1024 * 1024)
    )
)


def init_redis_cache(app, service_name):
    @app.before_request
    def _redis_cache_before_request():
        if request.method != "POST":
            return None
        if request.path != "/convert":
            return None
        if not request.content_type or not request.content_type.startswith(
            "multipart/form-data"
        ):
            return None

        try:
            body = request.get_data(cache=True)
            settings = {
                "path": request.path,
                "query": request.query_string.decode("latin1"),
                "content_type": request.content_type,
            }
            key = cache_key(service_name, body, settings)
            cached = cache_get(key)

            if cached is not None:
                app.logger.info(
                    "Redis cache HIT: service=%s", service_name
                )
                return Response(
                    cached,
                    status=200,
                    content_type="application/octet-stream",
                    headers={"X-Redis-Cache": "HIT"},
                )

            request.environ["redis_cache_key"] = key
            app.logger.info(
                "Redis cache MISS: service=%s", service_name
            )
        except Exception:
            app.logger.exception("Redis cache lookup failed")

        return None

    @app.after_request
    def _redis_cache_after_request(response):
        key = request.environ.pop("redis_cache_key", None)

        if key and request.method == "POST" and response.status_code == 200:
            try:
                response.direct_passthrough = False
                data = response.get_data()

                if data and len(data) <= MAX_CACHE_BYTES:
                    if cache_set(key, data):
                        response.headers["X-Redis-Cache"] = "MISS"
                        app.logger.info(
                            "Redis cache STORE: service=%s bytes=%s",
                            service_name,
                            len(data),
                        )
                    else:
                        app.logger.warning(
                            "Redis cache STORE skipped or failed: service=%s bytes=%s",
                            service_name,
                            len(data),
                        )
            except Exception:
                app.logger.exception("Redis cache write failed")

        return response
