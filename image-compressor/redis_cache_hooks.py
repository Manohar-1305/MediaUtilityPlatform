from flask import request, Response
from redis_cache import cache_key, cache_get, cache_set

MAX_CACHE_BYTES = 5 * 1024 * 1024


def init_redis_cache(app, service_name):
    @app.before_request
    def _redis_cache_before_request():
        if request.method != "POST" or request.endpoint != "compress_image":
            return None

        uploaded = request.files.get("file")
        if not uploaded:
            return None

        try:
            file_bytes = uploaded.read()
            uploaded.stream.seek(0)

            settings = {
                "path": request.path,
                "quality": request.form.get("quality", "75"),
                "filename": uploaded.filename,
            }
            key = cache_key(service_name, file_bytes, settings)
            cached = cache_get(key)

            if cached is not None:
                return Response(
                    cached,
                    status=200,
                    content_type="application/octet-stream",
                    headers={"X-Redis-Cache": "HIT"},
                )

            request.environ["redis_cache_key"] = key
        except Exception:
            return None

        return None

    @app.after_request
    def _redis_cache_after_request(response):
        key = request.environ.pop("redis_cache_key", None)

        if key and response.status_code == 200:
            try:
                data = response.get_data()
                if data and len(data) <= MAX_CACHE_BYTES:
                    if cache_set(key, data):
                        response.headers["X-Redis-Cache"] = "MISS"
            except Exception:
                pass

        return response
