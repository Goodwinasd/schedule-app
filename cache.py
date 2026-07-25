import time
import logging
from functools import wraps

logger = logging.getLogger(__name__)


class TTLCache:
    def __init__(self, ttl_seconds=300):
        self._data = {}
        self._ttl = ttl_seconds

    def get(self, key):
        entry = self._data.get(key)
        if entry is None:
            return None
        if time.time() - entry['ts'] > self._ttl:
            del self._data[key]
            return None
        return entry['value']

    def set(self, key, value):
        self._data[key] = {'value': value, 'ts': time.time()}

    def invalidate(self, key=None):
        if key:
            self._data.pop(key, None)
        else:
            self._data.clear()

    def invalidate_prefix(self, prefix):
        for k in list(self._data):
            if k.startswith(prefix):
                del self._data[k]


refs_cache = TTLCache(ttl_seconds=300)


def cached(ttl=300):
    def decorator(f):
        cache = TTLCache(ttl)
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = f.__name__ + ':' + str(args) + str(sorted(kwargs.items()))
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = f(*args, **kwargs)
            cache.set(key, result)
            return result
        wrapper.cache = cache
        return wrapper
    return decorator
