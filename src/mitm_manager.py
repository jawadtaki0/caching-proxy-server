import os

from config import MITM_DOMAINS


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MITM_DOMAINS_FILE = os.path.join(DATA_DIR, "mitm_domains.txt")


def ensure_mitm_domains_file():
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(MITM_DOMAINS_FILE):
        return

    with open(MITM_DOMAINS_FILE, "w", encoding="utf-8") as file:
        for domain in MITM_DOMAINS:
            file.write(f"{domain.lower()}\n")


def read_mitm_domains():
    ensure_mitm_domains_file()

    with open(MITM_DOMAINS_FILE, "r", encoding="utf-8") as file:
        return [line.strip().lower() for line in file if line.strip()]


def write_mitm_domains(domains):
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(MITM_DOMAINS_FILE, "w", encoding="utf-8") as file:
        for domain in domains:
            file.write(f"{domain}\n")


def add_mitm_domain(domain):
    domain = domain.strip().lower()

    if not domain:
        return

    domains = read_mitm_domains()

    if domain not in domains:
        domains.append(domain)
        write_mitm_domains(domains)


def remove_mitm_domain(domain):
    domain = domain.strip().lower()
    domains = [current for current in read_mitm_domains() if current != domain]
    write_mitm_domains(domains)


def is_mitm_host(host):
    host = host.lower().split(":", 1)[0]

    for domain in read_mitm_domains():
        if host == domain or host.endswith(f".{domain}"):
            return True

    return False
