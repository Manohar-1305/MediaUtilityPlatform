import os

from flask import request
from redis_cache import cache_key, cache_get, cache_set

MAX_CACHE_BYTES = int(os.getenv("REDIS_CACHE_MAX_BYTES", str(100 * 1024 * 1024)))


def init_redis_cache(app, service_name):
    @app.before_request
    def _redis_cache_before_request():
        if request.method != "POST" or request.path != "/convert":
            return None
        return None

    @app.after_request
    def _redis_cache_after_request(response):
        return response
