import hashlib
import logging

from redis_cache import cache_get, cache_set

logger = logging.getLogger(__name__)


def build_merge_cache_key(files_data):
    """
    Generate a deterministic cache key from the ordered PDF uploads.
    Includes filenames and contents so different upload combinations
    produce different cache keys.
    """
    digest = hashlib.sha256()

    for filename, data in files_data:
        filename_bytes = filename.encode("utf-8", errors="replace")
        digest.update(len(filename_bytes).to_bytes(8, "big"))
        digest.update(filename_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)

    return f"pdf-combiner:merge:{digest.hexdigest()}"


def get_cached_pdf(key):
    return cache_get(key)


def store_cached_pdf(key, pdf_bytes):
    return cache_set(key, pdf_bytes)

