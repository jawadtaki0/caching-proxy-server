import socket
import threading
from config import HOST, PORT
from request_parser import parse_request
from forwarder import forward_request
from logger_setup import setup_logger

class ProxyServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.logger = setup_logger()

    def start(self):
        print(f"Starting proxy server on {self.host}:{self.port}")

        #Socket creation
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5) #up to 5 clients
        print("Proxy server is listening...")

        while True:
            client_socket, client_address = self.server_socket.accept()
            print(f"New connection from {client_address}")
            self.logger.info(f"Client connected: {client_address[0]}:{client_address[1]}")
            client_thread = threading.Thread(
                target=self.handle_client,
                args=(client_socket, client_address),
                daemon=True
            )
            client_thread.start()

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

        return b"".join(chunks)

    def handle_client(self, client_socket, client_address):
        print(f"Handling client {client_address}")

        parsed = None
        request_data = self.receive_request(client_socket)

        if request_data:
            print("---- Raw ----")
            print(request_data.decode(errors="replace"))

            parsed = parse_request(request_data)
            print("---- Parsed ----")
            print(parsed)
        
        if parsed and parsed["host"]:
            self.logger.info(
                f"Request from {client_address[0]}:{client_address[1]} "
                f"to {parsed['host']}:{parsed['port']} - "
                f"{parsed['method']} {parsed['path']}"
            )
            response_data = forward_request(parsed["host"], parsed["port"], request_data)
            if response_data.startswith(b"HTTP/1.1 502") or response_data.startswith(b"HTTP/1.1 504"):
                self.logger.error(
                    f"Forwarding failed for {parsed['method']} {parsed['path']} "
                    f"to {parsed['host']}:{parsed['port']}"
                )
            client_socket.sendall(response_data)
        else:
            self.logger.error(f"Bad request from {client_address[0]}:{client_address[1]}")
        client_socket.close()
