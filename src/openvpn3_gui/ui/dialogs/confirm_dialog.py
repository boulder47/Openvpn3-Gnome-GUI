"""Reusable confirmation dialog for destructive/privileged actions.

Per the security requirements, any destructive action (remove profile,
disconnect all sessions, revoke ACL access, etc.) must ask for explicit
confirmation before proceeding.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


def confirm(
    parent: Gtk.Widget,
    heading: str,
    body: str,
    confirm_label: str = "Confirm",
    destructive: bool = True,
    on_confirmed: Callable[[], None] | None = None,
) -> None:
    """Show a standard Adw.AlertDialog and invoke ``on_confirmed`` if accepted."""

    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("confirm", confirm_label)
    dialog.set_response_appearance(
        "confirm",
        Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED,
    )
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    def _on_response(_dialog: Adw.AlertDialog, response: str) -> None:
        if response == "confirm" and on_confirmed is not None:
            on_confirmed()

    dialog.connect("response", _on_response)
    dialog.present(parent)
