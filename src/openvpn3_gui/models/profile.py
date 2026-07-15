"""Data models representing an imported OpenVPN 3 configuration profile."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum


class AuthMethod(StrEnum):
    """Authentication mechanism a profile is expected to use."""

    NONE = "none"
    USERNAME_PASSWORD = "username_password"  # noqa: S105 - auth method name, not a secret
    CERTIFICATE = "certificate"
    PKCS11 = "pkcs11"
    USERNAME_PASSWORD_MFA = "username_password_mfa"  # noqa: S105 - auth method name, not a secret
    UNKNOWN = "unknown"


@dataclasses.dataclass
class CertificateInfo:
    """Metadata about an embedded or referenced client certificate."""

    subject: str | None = None
    issuer: str | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None

    @property
    def is_expiring_soon(self) -> bool:
        if self.not_after is None:
            return False
        return (self.not_after - datetime.now(self.not_after.tzinfo)).days < 30

    @property
    def is_expired(self) -> bool:
        if self.not_after is None:
            return False
        return self.not_after < datetime.now(self.not_after.tzinfo)


@dataclasses.dataclass
class ProfileACL:
    """Access-control list entry as reported by ``openvpn3 config-acl``."""

    owner: str | None = None
    public: bool = False
    granted_users: list[str] = dataclasses.field(default_factory=list)
    locked_down: bool = False
    sealed: bool = False


@dataclasses.dataclass
class Profile:
    """A single imported ``.ovpn`` configuration, as tracked by openvpn3-linux."""

    config_path: str  # D-Bus object path, e.g. /net/openvpn/v3/configuration/<uuid>
    name: str
    source_file: str | None = None
    imported_at: datetime | None = None
    last_used: datetime | None = None
    persistent: bool = True
    auth_method: AuthMethod = AuthMethod.UNKNOWN
    remote_host: str | None = None
    remote_port: int | None = None
    protocol: str | None = None
    cipher: str | None = None
    compression: str | None = None
    certificate: CertificateInfo | None = None
    acl: ProfileACL | None = None
    tags: list[str] = dataclasses.field(default_factory=list)
    favorite: bool = False
    notes: str = ""
    raw_config_text: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.source_file or self.config_path

    def matches_query(self, query: str) -> bool:
        """Used by Profile Manager's search/filter box."""

        query = query.lower().strip()
        if not query:
            return True
        haystack = " ".join(
            filter(
                None,
                [
                    self.name,
                    self.remote_host,
                    self.notes,
                    " ".join(self.tags),
                ],
            )
        ).lower()
        return query in haystack


@dataclasses.dataclass
class ProfileGroup:
    """A user-defined grouping of profiles (bonus feature: Profile Groups)."""

    name: str
    profile_names: list[str] = dataclasses.field(default_factory=list)
    color: str | None = None
