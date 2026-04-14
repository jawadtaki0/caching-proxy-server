import socket


def forward_request(host, port, request_data):
    request_text = request_data.decode(errors="replace")
    lines = request_text.split("\r\n")

    if lines:
        request_line_parts = lines[0].split()

        if len(request_line_parts) == 3:
            method = request_line_parts[0]
            path = request_line_parts[1]
            version = request_line_parts[2]

            if path.startswith("http://"):
                path_without_http = path[7:]
                first_slash_index = path_without_http.find("/")

                if first_slash_index != -1:
                    path = path_without_http[first_slash_index:]
                else:
                    path = "/"

            lines[0] = f"{method} {path} {version}"

    for i in range(1, len(lines)):
        if lines[i].lower().startswith("connection:"):
            lines[i] = "Connection: close"

        if lines[i].lower().startswith("proxy-connection:"):
            lines[i] = "Proxy-Connection: close"

    new_request_data = "\r\n".join(lines).encode()

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
