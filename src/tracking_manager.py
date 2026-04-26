import json
import os
from datetime import datetime


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TRACKED_DOMAIN_FILE = os.path.join(DATA_DIR, "tracked_domain.txt")
TRACKED_DETAILS_FILE = os.path.join(DATA_DIR, "tracked_details.json")
TRACKED_LOG_FILE = os.path.join(DATA_DIR, "tracked_logs.txt")


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
    tracked_domain = get_tracked_domain()

    if not tracked_domain or not host:
        return False

    host = host.lower().split(":", 1)[0]
    return host == tracked_domain or host.endswith(f".{tracked_domain}")


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

    with open(TRACKED_LOG_FILE, "w", encoding="utf-8") as file:
        file.write("")


def split_response(response_data):
    header_bytes, separator, body_bytes = response_data.partition(b"\r\n\r\n")
    headers = header_bytes.decode(errors="replace")

    if not separator:
        body_bytes = b""

    body_preview = body_bytes[:5000].decode(errors="replace")
    return headers, body_preview


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


def get_tracked_details():
    if not os.path.exists(TRACKED_DETAILS_FILE):
        return {}

    try:
        with open(TRACKED_DETAILS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
