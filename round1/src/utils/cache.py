import os
import json
import time
import hashlib
import logging
from pathlib import Path
from functools import wraps
from ..config.config import CACHE_DIR, CACHE_EXPIRY, ENABLE_CACHING

logger = logging.getLogger(__name__)

class Cache:
    """A utility class for caching expensive operations like PDF processing and embedding generation."""
    
    @staticmethod
    def get_cache_key(func_name, *args, **kwargs):
        """Generate a unique cache key based on function name and arguments."""
        # Create a string representation of the arguments
        args_str = str(args) + str(sorted(kwargs.items()))
        # Create a hash of the arguments
        return f"{func_name}_{hashlib.md5(args_str.encode()).hexdigest()}"
    
    @staticmethod
    def get_cache_path(cache_key):
        """Get the file path for a cache key."""
        cache_dir = Path(CACHE_DIR)
        cache_dir.mkdir(exist_ok=True, parents=True)
        return cache_dir / f"{cache_key}.json"
    
    @staticmethod
    def is_cache_valid(cache_path):
        """Check if cache exists and is not expired."""
        if not cache_path.exists():
            return False
        
        # Check if cache is expired
        modified_time = os.path.getmtime(cache_path)
        current_time = time.time()
        return (current_time - modified_time) < CACHE_EXPIRY
    
    @staticmethod
    def read_cache(cache_path):
        """Read data from cache file."""
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading cache: {e}")
            return None
    
    @staticmethod
    def write_cache(cache_path, data):
        """Write data to cache file."""
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")

def cached(func):
    """Decorator to cache function results."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not ENABLE_CACHING:
            return func(*args, **kwargs)
        
        cache_key = Cache.get_cache_key(func.__name__, *args, **kwargs)
        cache_path = Cache.get_cache_path(cache_key)
        
        if Cache.is_cache_valid(cache_path):
            logger.debug(f"Cache hit for {func.__name__}")
            cached_result = Cache.read_cache(cache_path)
            if cached_result is not None:
                return cached_result
        
        # Cache miss or invalid cache
        logger.debug(f"Cache miss for {func.__name__}")
        result = func(*args, **kwargs)
        Cache.write_cache(cache_path, result)
        return result
    
    return wrapper