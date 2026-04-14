def parse_request(request_data):
    request_text = request_data.decode(errors="replace")
    lines = request_text.split("\r\n") #line separator of http

    if not lines or lines[0] == "": #check if empty
        return None
    
    request_line = lines[0]
    parts = request_line.split()

    if (len(parts) != 3): #invalid request
        return None
    
    method = parts[0]
    path = parts[1]
    http_version = parts[2]

    headers = {}

    for line in lines[1:]:
        if line == "":
            break

        if ":" in line:
            header_name, header_value = line.split(":", 1)
            headers[header_name.strip().lower()] = header_value.strip()

    host = None
    port = 80

    if "host" in headers:
        host_value = headers["host"]

        if ":" in host_value:
            host_parts = host_value.split(":", 1)
            host = host_parts[0]
            port = int(host_parts[1])
        else:
            host = host_value

    return {
        "method": method,
        "path": path,
        "http_version": http_version,
        "host": host,
        "port": port,
        "headers": headers
    }
