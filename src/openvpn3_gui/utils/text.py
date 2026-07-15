"""Text helpers, primarily Pango-markup escaping for GTK/Libadwaita widgets.

Several Adw widget properties are parsed as Pango markup rather than
treated as plain text: ``Adw.PreferencesRow``/``ActionRow``/``ExpanderRow``/
``SwitchRow`` title & subtitle, ``Adw.PreferencesGroup`` title, ``Adw.Toast``
title, and ``Adw.AlertDialog`` heading & body. Any unescaped ``&``, ``<``,
or ``>`` in that text raises a GLib markup parse error — and for
``ActionRow``/``PreferencesRow`` specifically, that error is fatal and
crashes the whole application (confirmed: ``TypeError: ... unknown signal
name`` and ``Failed to set text ... from markup`` reports both trace back
to this).

Any string that ultimately reaches one of those properties and originates
outside a fixed string literal — profile names, tags, hostnames, CLI
output, exception messages, usernames — must be passed through
:func:`escape_markup` first.
"""

from __future__ import annotations

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402


def escape_markup(text: str | None) -> str:
    """Escape ``text`` for safe use in a Pango-markup-parsed widget property.

    Safe to call on text that's already plain (no-op for ordinary strings)
    and on ``None`` (returns an empty string), so it can be applied
    defensively without needing to know in advance whether the input
    contains special characters.
    """

    if not text:
        return ""
    return GLib.markup_escape_text(text)
