"""Fieldora internal mutual-TLS trust primitives.

Service identity is durable and independent of process/container lifetime. Certificates
are short-lived authentication material for that identity and may be renewed in place
without changing the service ID. Revocation remains an operator-registry decision in
addition to ordinary certificate expiry.

The installation root CA is deliberately separated from the online service issuer.
Long-lived processes need only the constrained issuer key/certificate, never the root
private key.
"""

from __future__ import annotations

import ipaddress
import os
import ssl
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@dataclass(frozen=True, slots=True)
class ServiceCertificate:
    service_id: str
    organization_id: str
    serial_number: str
    not_before_utc: str
    not_after_utc: str
    certificate_path: Path
    private_key_path: Path
    ca_certificate_path: Path


class ServiceTrustAuthority:
    """Installation-local root plus constrained issuer for Fieldora service trust."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.ca_key_path = root / "ca-private.pem"
        self.ca_certificate_path = root / "ca-certificate.pem"
        self.issuer_key_path = root / "issuer-private.pem"
        self.issuer_certificate_path = root / "issuer-certificate.pem"

    def initialize(self, common_name: str = "Fieldora Internal Service CA") -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.ca_key_path.exists() or self.ca_certificate_path.exists():
            if not self.ca_key_path.is_file() or not self.ca_certificate_path.is_file():
                raise FileExistsError("incomplete Fieldora service root CA already exists")
            self._ensure_issuer(common_name)
            return self.ca_certificate_path

        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        now = datetime.now(UTC)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
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
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        _atomic_private_key(self.ca_key_path, key)
        _atomic_bytes(
            self.ca_certificate_path,
            certificate.public_bytes(serialization.Encoding.PEM),
            0o644,
        )
        self._ensure_issuer(common_name)
        return self.ca_certificate_path

    def issue(
        self,
        *,
        service_id: str,
        organization_id: str,
        common_name: str,
        certificate_path: Path,
        private_key_path: Path,
        dns_names: tuple[str, ...] = (),
        ip_addresses: tuple[str, ...] = (),
        lifetime_hours: int = 168,
        reuse_private_key: bool = True,
    ) -> ServiceCertificate:
        if not 1 <= lifetime_hours <= 24 * 30:
            raise ValueError("service certificate lifetime must be 1 hour to 30 days")
        if not all(value.strip() for value in (service_id, organization_id, common_name)):
            raise ValueError("service identity fields are required")
        issuer_key, issuer_certificate = self._load_issuer()
        key = (
            _load_private_key(private_key_path)
            if reuse_private_key and private_key_path.is_file()
            else rsa.generate_private_key(public_exponent=65537, key_size=3072)
        )
        now = datetime.now(UTC)
        uri = x509.UniformResourceIdentifier(
            "spiffe://fieldora/"
            + organization_id.strip().replace("/", "_")
            + "/service/"
            + service_id.strip().replace("/", "_")
        )
        names: list[x509.GeneralName] = [uri]
        names.extend(x509.DNSName(item) for item in dns_names if item.strip())
        names.extend(
            x509.IPAddress(ipaddress.ip_address(item))
            for item in ip_addresses
            if item.strip()
        )
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization_id.strip()),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name.strip()),
            ]
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer_certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(hours=lifetime_hours))
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.ExtendedKeyUsage(
                    [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
                ),
                critical=False,
            )
            .sign(issuer_key, hashes.SHA256())
        )
        _atomic_private_key(private_key_path, key)
        _atomic_bytes(
            certificate_path,
            certificate.public_bytes(serialization.Encoding.PEM)
            + issuer_certificate.public_bytes(serialization.Encoding.PEM),
            0o644,
        )
        return ServiceCertificate(
            service_id=service_id,
            organization_id=organization_id,
            serial_number=format(certificate.serial_number, "x"),
            not_before_utc=certificate.not_valid_before_utc.isoformat(),
            not_after_utc=certificate.not_valid_after_utc.isoformat(),
            certificate_path=certificate_path,
            private_key_path=private_key_path,
            ca_certificate_path=self.ca_certificate_path,
        )

    def inspect(self, certificate_path: Path) -> ServiceCertificate:
        certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
        organization = certificate.subject.get_attributes_for_oid(
            NameOID.ORGANIZATION_NAME
        )
        sans = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        service_id = ""
        organization_id = organization[0].value if organization else ""
        for uri in sans.get_values_for_type(x509.UniformResourceIdentifier):
            marker = "/service/"
            if uri.startswith("spiffe://fieldora/") and marker in uri:
                service_id = uri.split(marker, 1)[1]
                break
        return ServiceCertificate(
            service_id=service_id,
            organization_id=organization_id,
            serial_number=format(certificate.serial_number, "x"),
            not_before_utc=certificate.not_valid_before_utc.isoformat(),
            not_after_utc=certificate.not_valid_after_utc.isoformat(),
            certificate_path=certificate_path,
            private_key_path=Path(""),
            ca_certificate_path=self.ca_certificate_path,
        )

    def export_issuer(self, destination: Path) -> None:
        """Export only material needed by a constrained online renewal service."""
        self._load_issuer()
        destination.mkdir(parents=True, exist_ok=True)
        _atomic_bytes(
            destination / self.ca_certificate_path.name,
            self.ca_certificate_path.read_bytes(),
            0o644,
        )
        _atomic_bytes(
            destination / self.issuer_certificate_path.name,
            self.issuer_certificate_path.read_bytes(),
            0o644,
        )
        _atomic_bytes(
            destination / self.issuer_key_path.name,
            self.issuer_key_path.read_bytes(),
            0o600,
        )

    def _ensure_issuer(self, common_name: str) -> None:
        if self.issuer_key_path.exists() or self.issuer_certificate_path.exists():
            if self.issuer_key_path.is_file() and self.issuer_certificate_path.is_file():
                return
            raise FileExistsError("incomplete Fieldora service issuer already exists")
        root_key, root_certificate = self._load_root()
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        now = datetime.now(UTC)
        subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, f"{common_name} Service Issuer")]
        )
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(root_certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
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
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(root_key, hashes.SHA256())
        )
        _atomic_private_key(self.issuer_key_path, key)
        _atomic_bytes(
            self.issuer_certificate_path,
            certificate.public_bytes(serialization.Encoding.PEM),
            0o644,
        )

    def _load_root(self):
        if not self.ca_key_path.is_file() or not self.ca_certificate_path.is_file():
            raise FileNotFoundError("Fieldora service root CA has not been initialized")
        return (
            _load_private_key(self.ca_key_path),
            x509.load_pem_x509_certificate(self.ca_certificate_path.read_bytes()),
        )

    def _load_issuer(self):
        if not self.issuer_key_path.is_file() or not self.issuer_certificate_path.is_file():
            raise FileNotFoundError("Fieldora service issuer has not been initialized")
        return (
            _load_private_key(self.issuer_key_path),
            x509.load_pem_x509_certificate(self.issuer_certificate_path.read_bytes()),
        )


def server_mtls_context(
    certificate: Path,
    private_key: Path,
    ca_certificate: Path,
) -> ssl.SSLContext:
    """Return a server context that always requires a trusted client certificate."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(str(certificate), str(private_key))
    context.load_verify_locations(cafile=str(ca_certificate))
    return context


def client_mtls_context(
    certificate: Path,
    private_key: Path,
    ca_certificate: Path,
) -> ssl.SSLContext:
    """Return a client context requiring trusted server identity and hostname checks."""
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca_certificate))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.load_cert_chain(str(certificate), str(private_key))
    return context


def _load_private_key(path: Path):
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _atomic_private_key(path: Path, key) -> None:
    _atomic_bytes(
        path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        0o600,
    )


def _atomic_bytes(path: Path, value: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
