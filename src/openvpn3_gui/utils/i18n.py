"""Localization via gettext. UI modules import ``_`` from here.

Translations live in ``po/`` and are compiled into
``/usr/share/locale/<lang>/LC_MESSAGES/openvpn3-gui.mo`` (or the equivalent
inside the Flatpak). The "Language" setting overrides the environment
locale when set to anything other than "system".
"""

from __future__ import annotations

import gettext
import locale
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DOMAIN = "openvpn3-gui"

_LOCALE_DIR_CANDIDATES = [
    Path("/app/share/locale"),  # Flatpak
    Path("/usr/share/locale"),
    Path(__file__).resolve().parents[3] / "po" / "build",  # dev tree
]

_translation = gettext.NullTranslations()


def init_i18n(language: str = "system") -> None:
    """Initialise gettext. Called once at startup, before any UI is built."""

    global _translation
    locale_dir = next((d for d in _LOCALE_DIR_CANDIDATES if d.exists()), None)

    languages: list[str] | None = None
    if language and language != "system":
        languages = [language]
    else:
        try:
            locale.setlocale(locale.LC_ALL, "")
        except locale.Error:
            logger.debug("Could not set locale from environment")

    try:
        _translation = gettext.translation(
            DOMAIN,
            localedir=str(locale_dir) if locale_dir else None,
            languages=languages,
            fallback=True,
        )
    except OSError:
        _translation = gettext.NullTranslations()


def _(message: str) -> str:
    """Translate ``message`` in the openvpn3-gui domain."""

    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)
