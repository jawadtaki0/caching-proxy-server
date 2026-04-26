import socket
import threading
import ssl
import select
from cache_manager import get_cached_response, save_response_to_cache
from cert_manager import ensure_ca_certificate, ensure_host_certificate
from config import HOST, PORT
from request_parser import parse_request
from forwarder import forward_https_request, forward_request
from filter_manager import is_host_allowed
from logger_setup import setup_logger
from tracking_manager import add_tracked_log, get_tracked_domain, is_tracked_host, save_tracked_details


class ProxyServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.logger = setup_logger()
        self.running = False

    def start(self):
        print(f"Starting proxy server on {self.host}:{self.port}")

        #Socket creation
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5) #up to 5 clients
        self.running = True
        print("Proxy server is listening...")
        tracked_domain = get_tracked_domain() or "None"
        print(f"Tracked domain: {tracked_domain}")

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
            self.logger.info("Proxy server stopped by user")
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

    def handle_connect_tunnel(self, client_socket, host, port):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.settimeout(5)

        try:
            server_socket.connect((host, port))

            if not self.safe_send(client_socket, b"HTTP/1.1 200 Connection Established\r\n\r\n"):
                return

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

        except OSError:
            pass
        finally:
            server_socket.close()

    def process_request(self, client_socket, client_address, parsed, request_data, is_https=False, should_record=False):
        if not is_host_allowed(parsed["host"]):
            if should_record:
                message = (
                    f"Blocked request from {client_address[0]}:{client_address[1]} "
                    f"to {parsed['host']}:{parsed['port']} - "
                    f"{parsed['method']} {parsed['path']}"
                )
                self.logger.warning(message)
                add_tracked_log(message)

            self.safe_send(
                client_socket,
                b"HTTP/1.1 403 Forbidden\r\n"
                b"Connection: close\r\n"
                b"Content-Length: 9\r\n\r\n"
                b"Forbidden"
            )
            return

        if parsed["method"] == "GET":
            cached_response = get_cached_response(parsed["host"], parsed["path"])

            if cached_response:
                if should_record:
                    message = (
                        f"Cache hit for {parsed['host']}{parsed['path']} "
                        f"requested by {client_address[0]}:{client_address[1]}"
                    )
                    self.logger.info(message)
                    add_tracked_log(message)
                    save_tracked_details("HTTPS" if is_https else "HTTP", client_address, parsed, request_data, cached_response)

                self.safe_send(client_socket, cached_response)
                return

            if should_record:
                message = (
                    f"Cache miss for {parsed['host']}{parsed['path']} "
                    f"requested by {client_address[0]}:{client_address[1]}"
                )
                self.logger.info(message)
                add_tracked_log(message)

        protocol_name = "HTTPS" if is_https else "HTTP"

        if should_record:
            message = (
                f"{protocol_name} request from {client_address[0]}:{client_address[1]} "
                f"to {parsed['host']}:{parsed['port']} - "
                f"{parsed['method']} {parsed['path']}"
            )
            self.logger.info(message)
            add_tracked_log(message)

        if is_https:
            response_data = forward_https_request(parsed["host"], parsed["port"], request_data)
        else:
            response_data = forward_request(parsed["host"], parsed["port"], request_data)

        if should_record and parsed["method"] == "GET" and not response_data.startswith(b"HTTP/1.1 502") and not response_data.startswith(b"HTTP/1.1 504"):
            save_response_to_cache(parsed["host"], parsed["path"], response_data)

        if should_record:
            save_tracked_details(protocol_name, client_address, parsed, request_data, response_data)

            if response_data.startswith(b"HTTP/1.1 502") or response_data.startswith(b"HTTP/1.1 504"):
                message = (
                    f"Forwarding failed for {parsed['method']} {parsed['path']} "
                    f"to {parsed['host']}:{parsed['port']}"
                )
                self.logger.error(message)
                add_tracked_log(message)

        self.safe_send(client_socket, response_data)

    def handle_https_intercept(self, client_socket, client_address, host, port):
        try:
            ensure_ca_certificate()
            cert_path, key_path = ensure_host_certificate(host)

            if not self.safe_send(client_socket, b"HTTP/1.1 200 Connection Established\r\n\r\n"):
                return

            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
            secure_client_socket = ssl_context.wrap_socket(client_socket, server_side=True)

            request_data = self.receive_request(secure_client_socket)

            if not request_data:
                secure_client_socket.close()
                return

            print("---- HTTPS Raw ----")
            print(request_data.decode(errors="replace"))

            parsed = parse_request(request_data)

            if parsed:
                if not parsed["host"]:
                    parsed["host"] = host

                parsed["port"] = port

            print("---- HTTPS Parsed ----")
            print(parsed)

            if parsed and parsed["host"]:
                self.process_request(secure_client_socket, client_address, parsed, request_data, is_https=True, should_record=True)
            else:
                self.logger.error(f"Bad HTTPS request from {client_address[0]}:{client_address[1]}")
                self.safe_send(
                    secure_client_socket,
                    b"HTTP/1.1 400 Bad Request\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: 11\r\n\r\n"
                    b"Bad Request"
                )

            secure_client_socket.close()

        except ssl.SSLError as error:
            if is_tracked_host(host):
                message = f"TLS handshake failed for {host}:{port}: {error}"
                self.logger.error(message)
                add_tracked_log(message)
        except Exception as error:
            if is_tracked_host(host):
                message = f"Certificate generation failed for {host}:{port}: {error}"
                self.logger.error(message)
                add_tracked_log(message)

            self.safe_send(
                client_socket,
                b"HTTP/1.1 500 Internal Server Error\r\n"
                b"Connection: close\r\n"
                b"Content-Length: 29\r\n\r\n"
                b"Certificate generation failed"
            )
        except OSError as error:
            if is_tracked_host(host):
                message = f"HTTPS interception failed for {host}:{port}: {error}"
                self.logger.error(message)
                add_tracked_log(message)

    def handle_client(self, client_socket, client_address):
        parsed = None
        request_data = self.receive_request(client_socket)

        if request_data:
            parsed = parse_request(request_data)

        if parsed and parsed["host"]:
            should_record = is_tracked_host(parsed["host"])

            if should_record:
                print(f"Handling client {client_address}")
                print("---- Raw ----")
                print(request_data.decode(errors="replace"))
                print("---- Parsed ----")
                print(parsed)
                self.logger.info(f"Client connected: {client_address[0]}:{client_address[1]}")
                add_tracked_log(f"Client connected: {client_address[0]}:{client_address[1]}")

            if parsed["method"] == "CONNECT":
                if not is_host_allowed(parsed["host"]):
                    if should_record:
                        message = (
                            f"Blocked request from {client_address[0]}:{client_address[1]} "
                            f"to {parsed['host']}:{parsed['port']} - "
                            f"{parsed['method']} {parsed['path']}"
                        )
                        self.logger.warning(message)
                        add_tracked_log(message)

                    self.safe_send(
                        client_socket,
                        b"HTTP/1.1 403 Forbidden\r\n"
                        b"Connection: close\r\n"
                        b"Content-Length: 9\r\n\r\n"
                        b"Forbidden"
                    )
                    client_socket.close()
                    return

                if should_record:
                    message = (
                        f"HTTPS interception from {client_address[0]}:{client_address[1]} "
                        f"to {parsed['host']}:{parsed['port']}"
                    )
                    self.logger.info(message)
                    add_tracked_log(message)
                    save_tracked_details("HTTPS", client_address, parsed, request_data, b"")
                    self.handle_https_intercept(client_socket, client_address, parsed["host"], parsed["port"])
                else:
                    self.handle_connect_tunnel(client_socket, parsed["host"], parsed["port"])

                client_socket.close()
                return

            self.process_request(client_socket, client_address, parsed, request_data, is_https=False, should_record=should_record)
        else:
            self.safe_send(
                client_socket,
                b"HTTP/1.1 400 Bad Request\r\n"
                b"Connection: close\r\n"
                b"Content-Length: 11\r\n\r\n"
                b"Bad Request"
            )

        client_socket.close()
