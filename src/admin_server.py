import html
import os
import socket
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from cache_manager import read_cache_index, request_cache_clear
from config import ADMIN_HOST, ADMIN_PORT, HOST, PORT
from tracking_manager import get_tracked_details


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "proxy.log")
BLACKLIST_FILE = os.path.join(PROJECT_ROOT, "data", "blacklist.txt")
WHITELIST_FILE = os.path.join(PROJECT_ROOT, "data", "whitelist.txt")


def read_lines(file_path):
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as file:
        return [line.rstrip() for line in file if line.strip()]


def write_lines(file_path, lines):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as file:
        for line in lines:
            file.write(f"{line}\n")


def read_filter_entries(file_path):
    return [line.strip().lower() for line in read_lines(file_path)]


def add_filter_entry(file_path, entry):
    entry = entry.strip().lower()

    if not entry:
        return

    entries = read_filter_entries(file_path)

    if entry not in entries:
        entries.append(entry)
        write_lines(file_path, entries)


def remove_filter_entry(file_path, entry):
    entry = entry.strip().lower()
    entries = [current for current in read_filter_entries(file_path) if current != entry]
    write_lines(file_path, entries)


def get_log_lines(limit=100):
    lines = read_lines(LOG_FILE)
    return lines[-limit:]


def clear_logs():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    with open(LOG_FILE, "w", encoding="utf-8") as file:
        file.write("")


def filter_log_lines(lines, query):
    query = query.strip().lower()

    if not query:
        return lines

    return [line for line in lines if query in line.lower()]


def get_stats():
    lines = read_lines(LOG_FILE)

    return {
        "total_requests": sum("REQUEST " in line for line in lines),
        "blocked": sum("BLOCKED " in line for line in lines),
        "errors": sum(" - ERROR - " in line or "ERROR " in line for line in lines),
        "cache_hits": sum("cache=HIT" in line for line in lines),
        "cache_misses": sum("cache=MISS" in line for line in lines),
    }


def format_timestamp(timestamp):
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return "unknown"


class AdminHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)

        if parsed_url.path == "/":
            self.send_dashboard()
        elif parsed_url.path == "/logs":
            query = parse_qs(parsed_url.query).get("q", [""])[0]
            self.send_logs(query)
        elif parsed_url.path == "/cache":
            self.send_cache()
        elif parsed_url.path == "/filter":
            self.send_filter()
        else:
            self.send_error(404, "Page not found")

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        form_data = parse_qs(body)
        action = form_data.get("action", [""])[0]
        entry = form_data.get("entry", [""])[0]

        if action == "clear_logs":
            clear_logs()
            self.redirect("/logs")
        elif action == "clear_cache":
            request_cache_clear()
            self.redirect("/cache")
        elif action == "add_blacklist":
            add_filter_entry(BLACKLIST_FILE, entry)
            self.redirect("/filter")
        elif action == "remove_blacklist":
            remove_filter_entry(BLACKLIST_FILE, entry)
            self.redirect("/filter")
        elif action == "add_whitelist":
            add_filter_entry(WHITELIST_FILE, entry)
            self.redirect("/filter")
        elif action == "remove_whitelist":
            remove_filter_entry(WHITELIST_FILE, entry)
            self.redirect("/filter")
        else:
            self.redirect("/")

    def log_message(self, format, *args):
        return

    def redirect(self, path):
        self.send_response(303)
        self.send_header("Location", path)
        self.end_headers()

    def send_html(self, page):
        encoded_page = page.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded_page)))
        self.end_headers()

        try:
            self.wfile.write(encoded_page)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, socket.error):
            pass

    def send_dashboard(self):
        blacklist = read_filter_entries(BLACKLIST_FILE)
        whitelist = read_filter_entries(WHITELIST_FILE)
        cache_index = read_cache_index()
        stats = get_stats()

        content = f"""
        <section>
            <h2>Dashboard</h2>
            <p class="muted">Refresh this page manually after sending demo requests.</p>
            <div class="stats">
                {self.stat_card("Proxy", f"{HOST}:{PORT}")}
                {self.stat_card("Total requests", stats["total_requests"])}
                {self.stat_card("Cache entries", len(cache_index))}
                {self.stat_card("Cache hit/miss", f'{stats["cache_hits"]}/{stats["cache_misses"]}')}
                {self.stat_card("Blocked", stats["blocked"])}
                {self.stat_card("Errors", stats["errors"])}
                {self.stat_card("Blacklist entries", len(blacklist))}
                {self.stat_card("Whitelist entries", len(whitelist))}
            </div>
        </section>
        <section>
            <h2>Recent Logs</h2>
            <pre>{self.format_logs(get_log_lines(25))}</pre>
        </section>
        {self.details_section(get_tracked_details())}
        """
        self.send_html(self.layout("Dashboard", content))

    def send_logs(self, query=""):
        lines = filter_log_lines(get_log_lines(300), query)
        content = f"""
        <section>
            <h2>Logs</h2>
            <p class="muted">Search by domain, port, method, status, or cache value.</p>
            <form method="get" action="/logs" autocomplete="off">
                <input name="q" value="{html.escape(query)}" placeholder="example.com, :443, GET, HIT, 200" autocomplete="new-password" spellcheck="false">
                <button>Search</button>
                <a class="button-link" href="/logs">Clear Search</a>
            </form>
            <form method="post">
                <button class="danger" name="action" value="clear_logs">Clear Logs</button>
            </form>
            <pre>{self.format_logs(lines[-100:])}</pre>
        </section>
        """
        self.send_html(self.layout("Logs", content))

    def send_cache(self):
        cache_index = read_cache_index()

        if cache_index:
            rows = ""

            for cache_key, entry in cache_index.items():
                rows += f"""
                <tr>
                    <td>{html.escape(cache_key)}</td>
                    <td>{html.escape(str(entry.get("host", "")))}</td>
                    <td>{html.escape(str(entry.get("path", "")))}</td>
                    <td>{html.escape(str(entry.get("size", 0)))}</td>
                    <td>{html.escape(format_timestamp(entry.get("timestamp")))}</td>
                </tr>
                """
        else:
            rows = '<tr><td colspan="5" class="muted">No cache entries</td></tr>'

        content = f"""
        <section>
            <h2>Cache</h2>
            <form method="post">
                <button class="danger" name="action" value="clear_cache">Clear Cache</button>
            </form>
            <table>
                <thead>
                    <tr>
                        <th>Cache Key</th>
                        <th>Host</th>
                        <th>Path</th>
                        <th>Size</th>
                        <th>Cached At</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </section>
        """
        self.send_html(self.layout("Cache", content))

    def send_filter(self):
        blacklist = read_filter_entries(BLACKLIST_FILE)
        whitelist = read_filter_entries(WHITELIST_FILE)

        content = f"""
        <section class="split">
            <div>
                <h2>Blacklist</h2>
                {self.add_form("add_blacklist", "Add blocked host", "example.com")}
                {self.entry_list(blacklist, "remove_blacklist", "No blacklist entries")}
            </div>
            <div>
                <h2>Whitelist</h2>
                {self.add_form("add_whitelist", "Add allowed host", "iana.org")}
                {self.entry_list(whitelist, "remove_whitelist", "No whitelist entries")}
            </div>
        </section>
        """
        self.send_html(self.layout("Filter", content))

    def stat_card(self, label, value):
        return f"""
        <div class="stat">
            <div class="label">{html.escape(str(label))}</div>
            <div class="value">{html.escape(str(value))}</div>
        </div>
        """

    def details_section(self, details):
        if not details:
            return """
            <section>
                <h2>Latest Request Details</h2>
                <div class="muted">No request details captured yet.</div>
            </section>
            """

        headers = "\n".join(
            f"{key}: {value}" for key, value in details.get("headers", {}).items()
        )
        parsed_request = html.escape(str(details.get("parsed_request", {})))

        return f"""
        <section>
            <h2>Latest Request Details</h2>
            <div class="stats">
                {self.stat_card("Protocol", details.get("protocol", ""))}
                {self.stat_card("Method", details.get("method", ""))}
                {self.stat_card("Host", details.get("host", ""))}
                {self.stat_card("Port", details.get("port", ""))}
                {self.stat_card("Path", details.get("path", ""))}
                {self.stat_card("Captured", details.get("timestamp", ""))}
            </div>
            <h3>Headers</h3>
            <pre>{html.escape(headers or "No headers")}</pre>
            <h3>Parsed Request</h3>
            <pre>{parsed_request}</pre>
            <h3>Raw Request</h3>
            <pre>{html.escape(details.get("raw_request", "") or "No raw request")}</pre>
            <h3>Response Headers</h3>
            <pre>{html.escape(details.get("response_headers", "") or "No response headers")}</pre>
            <h3>Body Preview</h3>
            <pre>{html.escape(details.get("body_preview", "") or "No body preview")}</pre>
        </section>
        """

    def format_logs(self, lines):
        if not lines:
            return "No log entries yet"

        return "\n".join(html.escape(line) for line in lines)

    def add_form(self, action, button_text, placeholder):
        return f"""
        <form method="post" autocomplete="off">
            <input name="entry" placeholder="{html.escape(placeholder)}" autocomplete="new-password" spellcheck="false" required>
            <button name="action" value="{html.escape(action)}">{html.escape(button_text)}</button>
        </form>
        """

    def entry_list(self, entries, remove_action, empty_text):
        if not entries:
            return f'<div class="muted">{html.escape(empty_text)}</div>'

        items = ""

        for entry in entries:
            escaped_entry = html.escape(entry)
            items += f"""
            <li>
                <span>{escaped_entry}</span>
                <form method="post">
                    <input type="hidden" name="entry" value="{escaped_entry}">
                    <button class="danger" name="action" value="{html.escape(remove_action)}">Remove</button>
                </form>
            </li>
            """

        return f"<ul>{items}</ul>"

    def layout(self, title, content):
        return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Proxy Admin - {html.escape(title)}</title>
    <style>
        :root {{
            --bg: #eef1f4;
            --panel: #ffffff;
            --text: #18202a;
            --muted: #667085;
            --line: #d7dde5;
            --accent: #176b5b;
            --danger: #b42318;
            --code: #101828;
        }}

        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            background: var(--bg);
            color: var(--text);
            font-family: "Segoe UI", Tahoma, sans-serif;
        }}

        header {{
            padding: 22px 28px;
            background: #17202a;
            color: white;
        }}

        h1 {{
            margin: 0;
            font-size: 28px;
        }}

        nav {{
            display: flex;
            gap: 10px;
            margin-top: 14px;
            flex-wrap: wrap;
        }}

        nav a {{
            color: white;
            text-decoration: none;
            border: 1px solid #506070;
            border-radius: 6px;
            padding: 7px 10px;
        }}

        .button-link {{
            display: inline-flex;
            align-items: center;
            padding: 9px 12px;
            border-radius: 6px;
            background: #475467;
            color: white;
            text-decoration: none;
            font-weight: 600;
        }}

        main {{
            display: grid;
            gap: 18px;
            padding: 24px 28px;
        }}

        section {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 18px;
        }}

        h2 {{
            margin: 0 0 14px;
            font-size: 18px;
        }}

        .stats {{
            display: grid;
            grid-template-columns: repeat(4, minmax(160px, 1fr));
            gap: 14px;
        }}

        .stat {{
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 14px;
            background: #f8fafc;
        }}

        .label {{
            color: var(--muted);
            font-size: 13px;
        }}

        .value {{
            margin-top: 6px;
            font-size: 20px;
            font-weight: 650;
            overflow-wrap: anywhere;
        }}

        .split {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 22px;
        }}

        form {{
            display: flex;
            gap: 8px;
            margin: 0 0 12px;
        }}

        h3 {{
            margin: 18px 0 10px;
            font-size: 15px;
        }}

        input {{
            flex: 1;
            min-width: 0;
            padding: 9px 10px;
            border: 1px solid var(--line);
            border-radius: 6px;
            font-size: 14px;
        }}

        button {{
            padding: 9px 12px;
            border: 0;
            border-radius: 6px;
            background: var(--accent);
            color: white;
            font-weight: 600;
            cursor: pointer;
        }}

        button.danger {{
            background: var(--danger);
        }}

        ul {{
            margin: 0;
            padding: 0;
            list-style: none;
        }}

        li {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            border-bottom: 1px solid var(--line);
            padding: 9px 0;
        }}

        li form {{
            margin: 0;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
        }}

        th, td {{
            border-bottom: 1px solid var(--line);
            padding: 10px;
            text-align: left;
            overflow-wrap: anywhere;
        }}

        th {{
            background: #f8fafc;
        }}

        pre {{
            margin: 0;
            padding: 14px;
            min-height: 320px;
            max-height: 620px;
            overflow: auto;
            border-radius: 6px;
            background: var(--code);
            color: #e4e7ec;
            line-height: 1.45;
            white-space: pre-wrap;
            font-size: 13px;
        }}

        .muted {{
            color: var(--muted);
        }}

        @media (max-width: 900px) {{
            .stats, .split {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>Proxy Admin</h1>
        <nav>
            <a href="/">Dashboard</a>
            <a href="/logs">Logs</a>
            <a href="/cache">Cache</a>
            <a href="/filter">Filter</a>
        </nav>
    </header>
    <main>{content}</main>
</body>
</html>"""


def run_admin_server():
    server = HTTPServer((ADMIN_HOST, ADMIN_PORT), AdminHandler)
    print(f"Admin interface running on http://{ADMIN_HOST}:{ADMIN_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run_admin_server()
