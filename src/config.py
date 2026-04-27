HOST = "127.0.0.1"
PORT = 8888

ADMIN_HOST = "127.0.0.1"
ADMIN_PORT = 5000

CACHE_TIMEOUT = 60  # seconds

# HTTPS MITM is limited to these domains so browser background traffic still uses
# the stable CONNECT tunnel.
ENABLE_MITM = True
MITM_DOMAINS = ["example.com", "iana.org"]
