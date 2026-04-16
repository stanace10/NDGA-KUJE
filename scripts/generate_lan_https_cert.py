from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address
from pathlib import Path


try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
except Exception as exc:  # noqa: BLE001
    raise SystemExit(
        "cryptography is required to generate the LAN HTTPS certificate. "
        "Install it in the local Python environment first."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
CERT_DIR = ROOT / "certs" / "lan"
CERT_PATH = CERT_DIR / "ndga-lan.crt"
KEY_PATH = CERT_DIR / "ndga-lan.key"
ROOT_CERT_PATH = CERT_DIR / "ndga-lan-root.crt"
ROOT_KEY_PATH = CERT_DIR / "ndga-lan-root.key"
CHAIN_PATH = CERT_DIR / "ndga-lan-chain.crt"


def _subject(common_name: str):
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "NG"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "FCT"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Abuja"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Notre Dame Girls Academy"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def _write_file(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _install_root_certificate(root_path: Path):
    try:
        subprocess.run(
            ["certutil", "-user", "-addstore", "Root", str(root_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"Installed LAN root certificate in CurrentUser Root store: {root_path}")
    except Exception as exc:  # noqa: BLE001
        print(
            "Automatic root certificate install failed. "
            f"Install {root_path} manually in Trusted Root Certification Authorities. Error: {exc}"
        )


def main():
    parser = argparse.ArgumentParser(description="Generate NDGA LAN HTTPS certificates.")
    parser.add_argument(
        "--install-root",
        action="store_true",
        help="Install the LAN root certificate into the current Windows user trust store.",
    )
    args = parser.parse_args()

    CERT_DIR.mkdir(parents=True, exist_ok=True)

    root_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_subject = _subject("NDGA LAN Root CA")
    root_certificate = (
        x509.CertificateBuilder()
        .subject_name(root_subject)
        .issuer_name(root_subject)
        .public_key(root_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=5))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(root_private_key.public_key()), critical=False)
        .sign(private_key=root_private_key, algorithm=hashes.SHA256())
    )

    server_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_subject = _subject("ndgak.local")
    san_entries = [
        x509.DNSName("ndgak.local"),
        x509.DNSName("localhost"),
        x509.IPAddress(IPv4Address("127.0.0.1")),
        x509.IPAddress(IPv4Address("192.168.10.10")),
    ]
    server_certificate = (
        x509.CertificateBuilder()
        .subject_name(server_subject)
        .issuer_name(root_subject)
        .public_key(server_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=5))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
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
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_private_key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_private_key.public_key()),
            critical=False,
        )
        .sign(private_key=root_private_key, algorithm=hashes.SHA256())
    )

    root_key_pem = root_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    root_cert_pem = root_certificate.public_bytes(serialization.Encoding.PEM)
    server_key_pem = server_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    server_cert_pem = server_certificate.public_bytes(serialization.Encoding.PEM)

    _write_file(ROOT_KEY_PATH, root_key_pem)
    _write_file(ROOT_CERT_PATH, root_cert_pem)
    _write_file(KEY_PATH, server_key_pem)
    _write_file(CERT_PATH, server_cert_pem + root_cert_pem)
    _write_file(CHAIN_PATH, root_cert_pem)

    print(f"Created LAN HTTPS certificate: {CERT_PATH}")
    print(f"Created LAN HTTPS key: {KEY_PATH}")
    print(f"Created LAN root certificate: {ROOT_CERT_PATH}")
    print(f"Created LAN certificate chain: {CHAIN_PATH}")

    if args.install_root:
        _install_root_certificate(ROOT_CERT_PATH)


if __name__ == "__main__":
    main()
