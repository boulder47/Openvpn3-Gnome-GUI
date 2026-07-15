"""Certificate inspection: parse embedded client certs and warn before expiry.

Uses the ``cryptography`` package when available (it is listed as a
dependency and bundled in all three package formats); degrades to a no-op
with a logged warning if the import fails, so the rest of the app keeps
working.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from openvpn3_gui.models.profile import CertificateInfo, Profile

logger = logging.getLogger(__name__)

try:
    from cryptography import x509

    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False

_PEM_CERT_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL
)


class CertificateService:
    """Extracts and inspects the first client certificate embedded in a profile."""

    @property
    def available(self) -> bool:
        return _CRYPTO_AVAILABLE

    def extract_certificate(self, profile: Profile) -> CertificateInfo | None:
        if not _CRYPTO_AVAILABLE:
            logger.debug("cryptography package unavailable; skipping cert inspection")
            return None
        if not profile.raw_config_text:
            return None
        match = _PEM_CERT_RE.search(profile.raw_config_text)
        if not match:
            return None
        try:
            cert = x509.load_pem_x509_certificate(match.group(0).encode())
        except ValueError as exc:
            logger.warning("Could not parse certificate in %s: %s", profile.name, exc)
            return None
        return CertificateInfo(
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            not_before=cert.not_valid_before_utc,
            not_after=cert.not_valid_after_utc,
        )

    def days_until_expiry(self, info: CertificateInfo) -> int | None:
        if info.not_after is None:
            return None
        delta = info.not_after - datetime.now(UTC)
        return delta.days

    def profiles_expiring_within(
        self, profiles: list[Profile], days: int
    ) -> list[tuple[Profile, int]]:
        """Return (profile, days_left) pairs for certs expiring within ``days``."""

        expiring: list[tuple[Profile, int]] = []
        for profile in profiles:
            info = profile.certificate or self.extract_certificate(profile)
            if info is None:
                continue
            days_left = self.days_until_expiry(info)
            if days_left is not None and days_left <= days:
                expiring.append((profile, days_left))
        return expiring
