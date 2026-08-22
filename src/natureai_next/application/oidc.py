"""Pinned OpenID Connect JWT verification and local identity mapping."""

from __future__ import annotations

import base64
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)


@dataclass(frozen=True, slots=True)
class OidcConfiguration:
    issuer: str
    audience: str
    jwks_path: Path | None = None
    clock_skew_seconds: int = 60
    discovery: bool = False
    refresh_seconds: int = 3600
    request_timeout_seconds: float = 10.0


class OidcAuthenticationService:
    def __init__(
        self, configuration: OidcConfiguration,
        repository: SqliteAccessControlRepository,
        fetch_json: Callable[[str, float, int], dict] | None = None,
    ) -> None:
        self._configuration = configuration
        self._repository = repository
        self._fetch_json = fetch_json or self._download_json
        self._lock = threading.RLock()
        self._keys: dict[str, dict] = {}
        self._jwks_uri = ""
        self._refresh_at = 0.0
        if configuration.discovery:
            if configuration.jwks_path is not None:
                raise ValueError("OIDC discovery and a local JWKS are mutually exclusive")
            if urlsplit(configuration.issuer).scheme != "https":
                raise ValueError("OIDC discovery requires an HTTPS issuer")
            if not 60 <= configuration.refresh_seconds <= 86_400:
                raise ValueError("OIDC refresh interval must be between 60 and 86400 seconds")
            self._discover()
        elif configuration.jwks_path is not None:
            document = json.loads(
                configuration.jwks_path.read_text(encoding="utf-8")
            )
            self._keys = self._validated_keys(document)
        else:
            raise ValueError("OIDC requires discovery or a local JWKS")

    def authenticate(self, token: str) -> Identity:
        try:
            encoded_header, encoded_claims, encoded_signature = token.split(".")
            header = json.loads(self._decode(encoded_header))
            claims = json.loads(self._decode(encoded_claims))
            if header.get("alg") != "RS256":
                raise ValueError
            kid = str(header["kid"])
            jwk = self._key(kid)
            if jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig":
                raise ValueError
            key = rsa.RSAPublicNumbers(
                self._integer(jwk["e"]), self._integer(jwk["n"])
            ).public_key()
            key.verify(
                self._decode(encoded_signature),
                f"{encoded_header}.{encoded_claims}".encode(),
                padding.PKCS1v15(),
                SHA256(),
            )
            now = time.time()
            skew = self._configuration.clock_skew_seconds
            if claims.get("iss") != self._configuration.issuer:
                raise ValueError
            audience = claims.get("aud", [])
            audiences = [audience] if isinstance(audience, str) else audience
            if self._configuration.audience not in audiences:
                raise ValueError
            if float(claims["exp"]) <= now - skew:
                raise ValueError
            if "nbf" in claims and float(claims["nbf"]) > now + skew:
                raise ValueError
            subject = str(claims["sub"])
        except Exception as exc:
            raise AuthenticationFailed("OIDC token is invalid") from exc
        identity = self._repository.federated_identity(
            self._configuration.issuer, subject
        )
        if (
            identity is None or not identity.enabled
            or identity.kind is not IdentityKind.USER
        ):
            raise AuthenticationFailed("Federated identity is not mapped")
        return identity

    def _key(self, kid: str) -> dict:
        with self._lock:
            refreshed = False
            if self._configuration.discovery and time.monotonic() >= self._refresh_at:
                self._refresh_keys()
                refreshed = True
            jwk = self._keys.get(kid)
            if jwk is None and self._configuration.discovery and not refreshed:
                # One immediate refresh supports normal provider key rotation.
                self._refresh_keys()
                jwk = self._keys.get(kid)
            if jwk is None:
                raise KeyError(kid)
            return jwk

    def _discover(self) -> None:
        discovery_url = (
            self._configuration.issuer.rstrip("/")
            + "/.well-known/openid-configuration"
        )
        document = self._fetch_json(
            discovery_url, self._configuration.request_timeout_seconds, 256 * 1024
        )
        if document.get("issuer") != self._configuration.issuer:
            raise ValueError("OIDC discovery issuer does not match configured issuer")
        jwks_uri = str(document.get("jwks_uri", ""))
        if urlsplit(jwks_uri).scheme != "https":
            raise ValueError("OIDC JWKS URI must use HTTPS")
        self._jwks_uri = jwks_uri
        self._refresh_keys()

    def _refresh_keys(self) -> None:
        document = self._fetch_json(
            self._jwks_uri, self._configuration.request_timeout_seconds, 1024 * 1024
        )
        self._keys = self._validated_keys(document)
        self._refresh_at = (
            time.monotonic() + self._configuration.refresh_seconds
        )

    @staticmethod
    def _validated_keys(document: dict) -> dict[str, dict]:
        keys = document.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError("OIDC JWKS has no keys")
        result = {}
        for item in keys:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("kid"), str)
                or not item["kid"]
            ):
                raise ValueError("OIDC JWKS contains an invalid key")
            if item["kid"] in result:
                raise ValueError("OIDC JWKS contains duplicate key IDs")
            result[item["kid"]] = item
        return result

    @staticmethod
    def _download_json(url: str, timeout: float, maximum_bytes: int) -> dict:
        if urlsplit(url).scheme != "https":
            raise ValueError("OIDC metadata must use HTTPS")
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 HTTPS checked
            if urlsplit(response.geturl()).scheme != "https":
                raise ValueError("OIDC metadata redirect downgraded HTTPS")
            payload = response.read(maximum_bytes + 1)
        if len(payload) > maximum_bytes:
            raise ValueError("OIDC metadata response is too large")
        document = json.loads(payload)
        if not isinstance(document, dict):
            raise ValueError("OIDC metadata must be a JSON object")
        return document

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    @classmethod
    def _integer(cls, value: str) -> int:
        return int.from_bytes(cls._decode(value), "big")
