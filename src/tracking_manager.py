import json
import os
import zlib
from datetime import datetime


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TRACKED_DOMAIN_FILE = os.path.join(DATA_DIR, "tracked_domain.txt")
TRACKED_DETAILS_FILE = os.path.join(DATA_DIR, "tracked_details.json")
REQUEST_HISTORY_FILE = os.path.join(DATA_DIR, "request_history.json")
TRACKED_LOG_FILE = os.path.join(DATA_DIR, "tracked_logs.txt")
MAX_REQUEST_HISTORY = 50


def get_tracked_domain():
    if not os.path.exists(TRACKED_DOMAIN_FILE):
        return ""

    with open(TRACKED_DOMAIN_FILE, "r", encoding="utf-8") as file:
        return file.read().strip().lower()


def set_tracked_domain(domain):
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(TRACKED_DOMAIN_FILE, "w", encoding="utf-8") as file:
        file.write(domain.strip().lower())

    clear_tracked_details()


def clear_tracked_domain():
    set_tracked_domain("")


def is_tracked_host(host):
    tracked = get_tracked_domain()

    if not tracked:
        return False

    # normalize both
    host = host.lower()
    tracked = tracked.lower()

    return host == tracked or host.endswith("." + tracked)


def add_tracked_log(message):
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(TRACKED_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(f"{timestamp} - {message}\n")


def get_tracked_logs(limit=100):
    if not os.path.exists(TRACKED_LOG_FILE):
        return []

    with open(TRACKED_LOG_FILE, "r", encoding="utf-8") as file:
        lines = file.readlines()

    return [line.rstrip() for line in lines[-limit:]]


def clear_tracked_details():
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(TRACKED_DETAILS_FILE, "w", encoding="utf-8") as file:
        json.dump({}, file)

    with open(REQUEST_HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump([], file)

    with open(TRACKED_LOG_FILE, "w", encoding="utf-8") as file:
        file.write("")


def split_response(response_data):
    header_bytes, separator, body_bytes = response_data.partition(b"\r\n\r\n")
    headers = header_bytes.decode(errors="replace")

    if not separator:
        body_bytes = b""

    header_map = parse_response_headers(headers)
    body_preview = build_body_preview(header_map, body_bytes)
    return headers, body_preview


def parse_response_headers(headers):
    header_map = {}

    for line in headers.splitlines()[1:]:
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        header_map[key.strip().lower()] = value.strip().lower()

    return header_map


def build_body_preview(headers, body_bytes):
    if not body_bytes:
        return ""

    body_bytes = decode_chunked_body(headers, body_bytes)
    content_encoding = headers.get("content-encoding", "")
    content_type = headers.get("content-type", "")

    if "br" in content_encoding:
        return "Compressed response body uses Brotli (br); preview unavailable."

    if "zstd" in content_encoding:
        return "Compressed response body uses Zstandard (zstd); preview unavailable."

    try:
        if "gzip" in content_encoding or body_bytes.startswith(b"\x1f\x8b"):
            body_bytes = zlib.decompress(body_bytes, 16 + zlib.MAX_WBITS)
        elif "deflate" in content_encoding:
            body_bytes = zlib.decompress(body_bytes)
    except zlib.error:
        return f"Compressed response body could not be decoded ({content_encoding})."

    if is_binary_content(content_type, body_bytes):
        return f"Binary response body ({content_type or 'unknown content type'}); preview unavailable."

    return body_bytes[:5000].decode("utf-8", errors="replace")


def decode_chunked_body(headers, body_bytes):
    transfer_encoding = headers.get("transfer-encoding", "")

    if "chunked" not in transfer_encoding:
        return body_bytes

    decoded = bytearray()
    remaining = body_bytes

    while remaining:
        size_line, separator, remaining = remaining.partition(b"\r\n")

        if not separator:
            return body_bytes

        try:
            chunk_size = int(size_line.split(b";", 1)[0], 16)
        except ValueError:
            return body_bytes

        if chunk_size == 0:
            return bytes(decoded)

        decoded.extend(remaining[:chunk_size])
        remaining = remaining[chunk_size + 2:]

    return bytes(decoded)


def is_binary_content(content_type, body_bytes):
    binary_prefixes = (
        "image/",
        "audio/",
        "video/",
        "font/",
        "application/octet-stream",
        "application/pdf",
        "application/zip",
    )

    if any(content_type.startswith(current) for current in binary_prefixes):
        return True

    if content_type.startswith("text/"):
        return False

    textual_types = (
        "application/json",
        "application/javascript",
        "application/xml",
        "application/xhtml+xml",
        "image/svg+xml",
    )

    if any(content_type.startswith(current) for current in textual_types):
        return False

    sample = body_bytes[:512]

    if b"\x00" in sample:
        return True

    if not content_type:
        return not looks_like_text(sample)

    return False


def looks_like_text(sample):
    if not sample:
        return True

    printable = sum(
        byte in b"\r\n\t" or 32 <= byte <= 126
        for byte in sample
    )

    return printable / len(sample) > 0.85


def save_tracked_details(protocol, client_address, parsed, request_data, response_data):
    response_headers, body_preview = split_response(response_data)
    request_text = request_data.decode(errors="replace")

    details = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "protocol": protocol,
        "client": f"{client_address[0]}:{client_address[1]}",
        "method": parsed["method"],
        "path": parsed["path"],
        "host": parsed["host"],
        "port": parsed["port"],
        "headers": parsed["headers"],
        "parsed_request": parsed,
        "raw_request": request_text,
        "response_headers": response_headers,
        "body_preview": body_preview,
    }

    os.makedirs(DATA_DIR, exist_ok=True)

    with open(TRACKED_DETAILS_FILE, "w", encoding="utf-8") as file:
        json.dump(details, file, indent=2)

    append_request_history(details)


def get_tracked_details():
    if not os.path.exists(TRACKED_DETAILS_FILE):
        return {}

    try:
        with open(TRACKED_DETAILS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def append_request_history(details):
    history = get_request_history(MAX_REQUEST_HISTORY)
    history.append(details)
    history = history[-MAX_REQUEST_HISTORY:]

    with open(REQUEST_HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=2)


def get_request_history(limit=10):
    if not os.path.exists(REQUEST_HISTORY_FILE):
        return []

    try:
        with open(REQUEST_HISTORY_FILE, "r", encoding="utf-8") as file:
            history = json.load(file)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(history, list):
        return []

    return history[-limit:]
