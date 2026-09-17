import os
import json
import hashlib
import time

CACHE_DIR = ".voyagr_cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def get_cache_key(prefix, *args, **kwargs):
    """
    Generates a unique MD5 hash for the given arguments.
    """
    data = str(args) + str(kwargs)
    return f"{prefix}_{hashlib.md5(data.encode()).hexdigest()}.json"

def get_cached_data(prefix, *args, **kwargs):
    """
    Retrieves data from cache if it exists and is not expired (default 24h).
    """
    key = get_cache_key(prefix, *args, **kwargs)
    path = os.path.join(CACHE_DIR, key)
    
    if os.path.exists(path):
        # Cache for 24 hours
        if time.time() - os.path.getmtime(path) < 86400:
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except:
                return None
    return None

def set_cached_data(prefix, data, *args, **kwargs):
    """
    Saves data to a persistent cache file.
    """
    key = get_cache_key(prefix, *args, **kwargs)
    path = os.path.join(CACHE_DIR, key)
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Cache Write Error: {e}")
