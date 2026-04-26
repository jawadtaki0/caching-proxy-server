import ipaddress
import os
import sys
from datetime import datetime, timedelta, timezone


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VENDOR_DIR = os.path.join(PROJECT_ROOT, "vendor")

if os.path.isdir(VENDOR_DIR) and VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def get_certs_dir():
    certs_dir = os.path.join(PROJECT_ROOT, "certs")
    os.makedirs(certs_dir, exist_ok=True)
    return certs_dir


def get_host_file_name(host):
    return host.replace(".", "_").replace(":", "_")


def ensure_ca_certificate():
    certs_dir = get_certs_dir()
    ca_cert_path = os.path.join(certs_dir, "ca_cert.pem")
    ca_key_path = os.path.join(certs_dir, "ca_key.pem")

    if os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
        return ca_cert_path

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Caching Proxy MITM CA")
    ])

    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True
        )
        .sign(private_key=ca_key, algorithm=hashes.SHA256())
    )

    with open(ca_cert_path, "wb") as cert_file:
        cert_file.write(ca_cert.public_bytes(serialization.Encoding.PEM))

    with open(ca_key_path, "wb") as key_file:
        key_file.write(
            ca_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )

    return ca_cert_path


def load_ca_material():
    certs_dir = get_certs_dir()
    ca_cert_path = os.path.join(certs_dir, "ca_cert.pem")
    ca_key_path = os.path.join(certs_dir, "ca_key.pem")

    ensure_ca_certificate()

    with open(ca_cert_path, "rb") as cert_file:
        ca_cert = x509.load_pem_x509_certificate(cert_file.read())

    with open(ca_key_path, "rb") as key_file:
        ca_key = serialization.load_pem_private_key(key_file.read(), password=None)

    return ca_cert, ca_key


def build_subject_alternative_name(host):
    try:
        return x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))])
    except ValueError:
        return x509.SubjectAlternativeName([x509.DNSName(host)])


def ensure_host_certificate(host):
    certs_dir = get_certs_dir()
    file_name = get_host_file_name(host)
    host_cert_path = os.path.join(certs_dir, f"{file_name}_cert.pem")
    host_key_path = os.path.join(certs_dir, f"{file_name}_key.pem")

    if os.path.exists(host_cert_path) and os.path.exists(host_key_path):
        return host_cert_path, host_key_path

    ca_cert, ca_key = load_ca_material()
    host_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, host)
    ])

    host_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(host_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(build_subject_alternative_name(host), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False
        )
        .sign(private_key=ca_key, algorithm=hashes.SHA256())
    )

    with open(host_cert_path, "wb") as cert_file:
        cert_file.write(host_cert.public_bytes(serialization.Encoding.PEM))

    with open(host_key_path, "wb") as key_file:
        key_file.write(
            host_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )

    return host_cert_path, host_key_path
