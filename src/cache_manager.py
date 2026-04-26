import time
import json
import os
from config import CACHE_TIMEOUT


cache_store = {}
last_clear_time = 0

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
CACHE_INDEX_FILE = os.path.join(CACHE_DIR, "cache_index.json")
CACHE_CLEAR_FILE = os.path.join(CACHE_DIR, "cache_clear.txt")


def build_cache_key(host, path):
    return f"{host}{path}"


def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def read_cache_index():
    if not os.path.exists(CACHE_INDEX_FILE):
        return {}

    try:
        with open(CACHE_INDEX_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def write_cache_index(cache_index):
    ensure_cache_dir()

    with open(CACHE_INDEX_FILE, "w", encoding="utf-8") as file:
        json.dump(cache_index, file, indent=2)


def remove_cache_index_entry(cache_key):
    cache_index = read_cache_index()

    if cache_key in cache_index:
        del cache_index[cache_key]
        write_cache_index(cache_index)


def get_clear_request_time():
    if not os.path.exists(CACHE_CLEAR_FILE):
        return 0

    try:
        with open(CACHE_CLEAR_FILE, "r", encoding="utf-8") as file:
            return float(file.read().strip() or "0")
    except (ValueError, OSError):
        return 0


def clear_cache():
    cache_store.clear()
    write_cache_index({})


def request_cache_clear():
    ensure_cache_dir()
    clear_cache()

    with open(CACHE_CLEAR_FILE, "w", encoding="utf-8") as file:
        file.write(str(time.time()))


def apply_pending_cache_clear():
    global last_clear_time

    clear_request_time = get_clear_request_time()

    if clear_request_time > last_clear_time:
        cache_store.clear()
        last_clear_time = clear_request_time


def get_cached_response(host, path):
    apply_pending_cache_clear()

    cache_key = build_cache_key(host, path)
    cached_entry = cache_store.get(cache_key)

    if not cached_entry:
        return None

    if time.time() - cached_entry["timestamp"] > CACHE_TIMEOUT:
        del cache_store[cache_key]
        remove_cache_index_entry(cache_key)
        return None

    return cached_entry["response"]


def save_response_to_cache(host, path, response_data):
    apply_pending_cache_clear()

    cache_key = build_cache_key(host, path)
    timestamp = time.time()

    cache_store[cache_key] = {
        "response": response_data,
        "timestamp": timestamp
    }

    cache_index = read_cache_index()
    cache_index[cache_key] = {
        "host": host,
        "path": path,
        "size": len(response_data),
        "timestamp": timestamp
    }
    write_cache_index(cache_index)
