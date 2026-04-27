import socket
import ssl


def forward_request(host, port, request_data):
    new_request_data = prepare_request_for_origin(request_data, normalize_absolute_uri=True)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.settimeout(5)

    try:
        server_socket.connect((host, port))
        server_socket.sendall(new_request_data)

        response_chunks = []

        while True:
            try:
                chunk = server_socket.recv(4096)

                if not chunk:
                    break

                response_chunks.append(chunk)

            except socket.timeout:
                break

        response_data = b"".join(response_chunks)
        return response_data

    except socket.gaierror:
        return (
            b"HTTP/1.1 502 Bad Gateway\r\n"
            b"Connection: close\r\n"
            b"Content-Length: 17\r\n\r\n"
            b"DNS lookup failed"
        )

    except socket.timeout:
        return (
            b"HTTP/1.1 504 Gateway Timeout\r\n"
            b"Connection: close\r\n"
            b"Content-Length: 15\r\n\r\n"
            b"Gateway Timeout"
        )

    except OSError:
        return (
            b"HTTP/1.1 502 Bad Gateway\r\n"
            b"Connection: close\r\n"
            b"Content-Length: 11\r\n\r\n"
            b"Bad Gateway"
        )

    finally:
        server_socket.close()


def prepare_request_for_origin(request_data, normalize_absolute_uri=False):
    request_text = request_data.decode(errors="replace")
    lines = request_text.split("\r\n")
    method = ""

    if lines:
        request_line_parts = lines[0].split()

        if len(request_line_parts) == 3:
            method = request_line_parts[0]
            path = request_line_parts[1]
            version = request_line_parts[2]

            if normalize_absolute_uri and path.startswith("http://"):
                path_without_http = path[7:]
                first_slash_index = path_without_http.find("/")

                if first_slash_index != -1:
                    path = path_without_http[first_slash_index:]
                else:
                    path = "/"

            lines[0] = f"{method} {path} {version}"

    filtered_lines = lines[:1]

    for i in range(1, len(lines)):
        header_name = lines[i].split(":", 1)[0].strip().lower()

        if method == "GET" and header_name in ("if-modified-since", "if-none-match"):
            continue

        if header_name == "connection":
            filtered_lines.append("Connection: close")
            continue

        if header_name == "proxy-connection":
            continue

        filtered_lines.append(lines[i])

    return "\r\n".join(filtered_lines).encode()


def forward_https_request(host, port, request_data):
    raw_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_server_socket.settimeout(5)
    ssl_context = ssl.create_default_context()

    try:
        raw_server_socket.connect((host, port))

        with ssl_context.wrap_socket(raw_server_socket, server_hostname=host) as server_socket:
            new_request_data = prepare_request_for_origin(request_data)
            server_socket.sendall(new_request_data)

            response_chunks = []

            while True:
                try:
                    chunk = server_socket.recv(4096)

                    if not chunk:
                        break

                    response_chunks.append(chunk)

                except socket.timeout:
                    break

            response_data = b"".join(response_chunks)
            return response_data

    except socket.gaierror:
        return (
            b"HTTP/1.1 502 Bad Gateway\r\n"
            b"Connection: close\r\n"
            b"Content-Length: 17\r\n\r\n"
            b"DNS lookup failed"
        )

    except socket.timeout:
        return (
            b"HTTP/1.1 504 Gateway Timeout\r\n"
            b"Connection: close\r\n"
            b"Content-Length: 15\r\n\r\n"
            b"Gateway Timeout"
        )

    except OSError:
        return (
            b"HTTP/1.1 502 Bad Gateway\r\n"
            b"Connection: close\r\n"
            b"Content-Length: 11\r\n\r\n"
            b"Bad Gateway"
        )

    finally:
        try:
            raw_server_socket.close()
        except OSError:
            pass
