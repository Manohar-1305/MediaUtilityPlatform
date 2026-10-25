from flask import request, Response
from redis_cache import cache_key, cache_get, cache_set

MAX_CACHE_BYTES = 100 * 1024 * 1024


def init_redis_cache(app, service_name):
    @app.before_request
    def _redis_cache_before_request():
        if request.method != "POST":
            return None
        if request.path not in {"/inspect", "/preview", "/convert"}:
            return None
        if not request.content_type or not request.content_type.startswith("multipart/form-data"):
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
                app.logger.info("Redis cache HIT: service=%s path=%s", service_name, request.path)
                return Response(
                    cached,
                    status=200,
                    content_type="application/octet-stream",
                    headers={"X-Redis-Cache": "HIT"},
                )

            request.environ["redis_cache_key"] = key
            app.logger.info("Redis cache MISS: service=%s path=%s", service_name, request.path)
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
                        app.logger.info("Redis cache STORE: service=%s path=%s bytes=%s", service_name, request.path, len(data))
                    else:
                        app.logger.warning("Redis cache STORE skipped or failed: service=%s path=%s bytes=%s", service_name, request.path, len(data))
            except Exception:
                app.logger.exception("Redis cache write failed")
        return response
