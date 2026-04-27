# Caching Proxy Server

CSC 430 Computer Networks project.

This project is a Python caching proxy server built with sockets. It accepts browser traffic, parses requests, forwards them to the target server, returns responses to the client, logs activity, caches successful responses, and provides a simple web admin interface.

## Features

- HTTP proxy forwarding
- HTTPS `CONNECT` tunneling
- Optional HTTPS MITM inspection for selected domains
- Request parsing for method, host, port, path, and headers
- Multithreaded client handling
- Response caching with timeout
- Blacklist and whitelist filtering
- Terminal request summaries
- File logging to `logs/proxy.log`
- Admin dashboard using Python `http.server`
- Admin pages for logs, cache, filtering, MITM domains, and recent request details

## Project Structure

```text
src/
  main.py              Starts the proxy server
  proxy_server.py      Core socket proxy logic
  request_parser.py    Parses HTTP and CONNECT requests
  forwarder.py         Forwards HTTP and HTTPS requests
  cache_manager.py     Stores and clears cached responses
  filter_manager.py    Handles blacklist and whitelist checks
  admin_server.py      Web admin interface
  cert_manager.py      Creates the local CA and MITM certificates
  mitm_manager.py      Stores HTTPS MITM domains

data/
  blacklist.txt
  whitelist.txt
  mitm_domains.txt

logs/
  proxy.log

certs/
  Generated certificates are stored here
```

The `certs/` folder is intentionally ignored by Git. A fresh clone will not contain certificate files. When HTTPS MITM is used, the proxy automatically creates the folder and generates:

```text
certs/ca_cert.pem
certs/ca_key.pem
certs/<domain>_cert.pem
certs/<domain>_key.pem
```

Each machine gets its own local CA and per-domain certificates. These files should not be pushed to GitHub because they include private keys.

## Requirements

- Python 3.10 or newer
- Firefox or another browser that can be configured to use a manual proxy
- `cryptography` Python package

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Running The Proxy

Start the proxy server:

```powershell
python src/main.py
```

Default proxy address:

```text
127.0.0.1:8888
```

Start the admin interface in a second terminal:

```powershell
python src/admin_server.py
```

Open the admin panel:

```text
http://127.0.0.1:5000
```

## Browser Setup

Using a separate Firefox profile is recommended so normal browser traffic does not pollute the logs.

Create or open Firefox profiles:

```powershell
firefox.exe -P
```

In Firefox, go to:

```text
Settings > Network Settings > Manual proxy configuration
```

Use:

```text
HTTP Proxy: 127.0.0.1
Port: 8888
Also use this proxy for HTTPS: enabled
```

## HTTPS MITM Setup

By default, HTTPS traffic is tunneled with `CONNECT`. The proxy can only inspect HTTPS traffic for domains added to the MITM list.

Open:

```text
http://127.0.0.1:5000/mitm
```

Add a domain, for example:

```text
wikipedia.org
```

The proxy generates a local CA certificate:

```text
certs/ca_cert.pem
```

If the file does not exist yet, start the proxy and open a domain that is listed in `/mitm`. The proxy will generate the CA certificate, CA private key, and the needed domain certificate automatically.

To let Firefox trust MITM certificates:

1. Open Firefox settings.
2. Go to `Privacy & Security`.
3. Scroll to `Certificates`.
4. Click `View Certificates`.
5. Go to `Authorities`.
6. Import `certs/ca_cert.pem`.
7. Check `Trust this CA to identify websites`.
8. Restart Firefox.

Only use MITM for testing or educational purposes.

## Admin Interface

The admin panel includes:

- Dashboard stats
- Recent logs
- Request details with arrow navigation
- Cache entries and clear-cache button
- Log search and clear-logs button
- Blacklist and whitelist management
- MITM domain management

Useful pages:

```text
http://127.0.0.1:5000/
http://127.0.0.1:5000/logs
http://127.0.0.1:5000/cache
http://127.0.0.1:5000/filter
http://127.0.0.1:5000/mitm
```

## Basic Tests

### HTTP Forwarding And Cache

Open in the proxied browser:

```text
http://example.com
```

Expected first request:

```text
method=GET status=200 cache=MISS
```

Refresh within 60 seconds.

Expected repeated request:

```text
method=GET status=200 cache=HIT
```

### HTTPS Tunnel

Make sure the domain is not in the MITM list, then open:

```text
https://www.python.org
```

Expected:

```text
method=CONNECT status=200 cache=NONE
```

### HTTPS MITM

Add this domain in `/mitm`:

```text
wikipedia.org
```

Open:

```text
https://www.wikipedia.org/
```

Expected:

```text
protocol=HTTPS MITM method=GET status=200 cache=MISS
```

Refresh within 60 seconds.

Expected:

```text
cache=HIT
```

### Blacklist

Add this in `/filter` blacklist:

```text
example.com
```

Open:

```text
http://example.com
```

Expected:

```text
403 Forbidden
```

Remove it from the blacklist to allow the site again.

## Notes

- The cache timeout is configured in `src/config.py`.
- Only `200 OK` GET responses are cached.
- Redirects such as `301` and validation responses such as `304` are not cached.
- Browser background requests may appear in logs. A clean Firefox profile reduces noise.
- Generated certificates, logs, runtime cache files, and local dependency folders are ignored by Git.
