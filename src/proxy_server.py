import select
import socket
import threading

from cache_manager import get_cached_response, save_response_to_cache
from config import HOST, PORT
from filter_manager import is_host_allowed
from forwarder import forward_request
from logger_setup import setup_logger
from request_parser import parse_request
from tracking_manager import save_tracked_details


class ProxyServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.logger = setup_logger()
        self.running = False

    def start(self):
        print(f"Starting proxy server on {self.host}:{self.port}")

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True

        print("Proxy server is listening...")

        try:
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
        except KeyboardInterrupt:
            print("\nStopping proxy server...")
            self.logger.info("SERVER stopped by user")
        finally:
            self.stop()

    def stop(self):
        self.running = False

        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass

            self.server_socket = None

    def receive_request(self, client_socket):
        client_socket.settimeout(3)
        chunks = []

        while True:
            try:
                chunk = client_socket.recv(4096)

                if not chunk:
                    break

                chunks.append(chunk)

                if b"\r\n\r\n" in b"".join(chunks):
                    break
            except socket.timeout:
                break
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break

        return b"".join(chunks)

    def safe_send(self, client_socket, data):
        try:
            client_socket.sendall(data)
            return True
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            return False

    def get_status_code(self, response_data):
        try:
            first_line = response_data.split(b"\r\n", 1)[0].decode(errors="replace")
            parts = first_line.split()

            if len(parts) >= 2 and parts[1].isdigit():
                return parts[1]
        except (IndexError, ValueError):
            pass

        return "unknown"

    def print_request_details(self, client_address, request_data, parsed):
        print(f"New connection from {client_address}")
        print("---- Raw request ----")
        print(request_data.decode(errors="replace"))
        print("---- Parsed request ----")
        print(f"method: {parsed['method']}")
        print(f"host: {parsed['host']}")
        print(f"port: {parsed['port']}")
        print(f"headers: {parsed['headers']}")

    def log_request(self, client_address, parsed, status_code, cache_result="NONE"):
        message = (
            f"REQUEST client={client_address[0]}:{client_address[1]} "
            f"target={parsed['host']}:{parsed['port']} "
            f"method={parsed['method']} url={parsed['path']} "
            f"status={status_code} cache={cache_result}"
        )
        self.logger.info(message)
        print("Logging confirmation")

    def send_forbidden(self, client_socket):
        self.safe_send(
            client_socket,
            b"HTTP/1.1 403 Forbidden\r\n"
            b"Connection: close\r\n"
            b"Content-Length: 9\r\n\r\n"
            b"Forbidden"
        )

    def handle_connect_tunnel(self, client_socket, client_address, parsed, request_data):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.settimeout(5)

        try:
            print("Forwarding request to server")
            server_socket.connect((parsed["host"], parsed["port"]))

            if not self.safe_send(client_socket, b"HTTP/1.1 200 Connection Established\r\n\r\n"):
                return

            print("Response received")
            print("status code: 200")
            self.log_request(client_address, parsed, "200")
            save_tracked_details("HTTPS CONNECT", client_address, parsed, request_data, b"HTTP/1.1 200 Connection Established\r\n\r\n")

            client_socket.settimeout(None)
            server_socket.settimeout(None)
            sockets = [client_socket, server_socket]

            while True:
                readable, _, _ = select.select(sockets, [], [])

                for current_socket in readable:
                    data = current_socket.recv(4096)

                    if not data:
                        return

                    if current_socket is client_socket:
                        server_socket.sendall(data)
                    elif not self.safe_send(client_socket, data):
                        return

        except OSError as error:
            self.logger.error(
                f"ERROR client={client_address[0]}:{client_address[1]} "
                f"target={parsed['host']}:{parsed['port']} method=CONNECT "
                f"url={parsed['path']} error={error}"
            )
            print("Response received")
            print("status code: 502")
            save_tracked_details("HTTPS CONNECT", client_address, parsed, request_data, b"HTTP/1.1 502 Bad Gateway\r\n\r\nBad Gateway")
            self.safe_send(
                client_socket,
                b"HTTP/1.1 502 Bad Gateway\r\n"
                b"Connection: close\r\n"
                b"Content-Length: 11\r\n\r\n"
                b"Bad Gateway"
            )
        finally:
            try:
                server_socket.close()
            except OSError:
                pass

    def handle_http_request(self, client_socket, client_address, parsed, request_data):
        cache_result = "NONE"

        if parsed["method"] == "GET":
            cached_response = get_cached_response(parsed["host"], parsed["path"])

            if cached_response:
                cache_result = "HIT"
                print("CACHE HIT")
                status_code = self.get_status_code(cached_response)
                print("Response received")
                print(f"status code: {status_code}")
                self.log_request(client_address, parsed, status_code, cache_result)
                save_tracked_details("HTTP", client_address, parsed, request_data, cached_response)
                self.safe_send(client_socket, cached_response)
                return

            cache_result = "MISS"
            print("CACHE MISS")

        print("Forwarding request to server")
        response_data = forward_request(parsed["host"], parsed["port"], request_data)
        status_code = self.get_status_code(response_data)

        print("Response received")
        print(f"status code: {status_code}")

        if parsed["method"] == "GET" and status_code not in ("502", "504", "unknown"):
            save_response_to_cache(parsed["host"], parsed["path"], response_data)

        if status_code in ("502", "504"):
            self.logger.error(
                f"ERROR client={client_address[0]}:{client_address[1]} "
                f"target={parsed['host']}:{parsed['port']} method={parsed['method']} "
                f"url={parsed['path']} status={status_code}"
            )

        self.log_request(client_address, parsed, status_code, cache_result)
        save_tracked_details("HTTP", client_address, parsed, request_data, response_data)
        self.safe_send(client_socket, response_data)

    def handle_client(self, client_socket, client_address):
        try:
            request_data = self.receive_request(client_socket)

            if not request_data:
                return

            parsed = parse_request(request_data)

            if not parsed or not parsed["host"]:
                self.safe_send(
                    client_socket,
                    b"HTTP/1.1 400 Bad Request\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: 11\r\n\r\n"
                    b"Bad Request"
                )
                return

            self.print_request_details(client_address, request_data, parsed)

            if not is_host_allowed(parsed["host"]):
                print("Request blocked by filter")
                self.logger.warning(
                    f"BLOCKED client={client_address[0]}:{client_address[1]} "
                    f"target={parsed['host']}:{parsed['port']} method={parsed['method']} "
                    f"url={parsed['path']} status=403"
                )
                self.send_forbidden(client_socket)
                print("Response received")
                print("status code: 403")
                print("Logging confirmation")
                save_tracked_details("HTTP" if parsed["method"] != "CONNECT" else "HTTPS CONNECT", client_address, parsed, request_data, b"HTTP/1.1 403 Forbidden\r\n\r\nForbidden")
                return

            if parsed["method"] == "CONNECT":
                self.handle_connect_tunnel(client_socket, client_address, parsed, request_data)
            else:
                self.handle_http_request(client_socket, client_address, parsed, request_data)
        finally:
            try:
                client_socket.close()
            except OSError:
                pass
