"""Modal dialog collecting credentials (username/password/OTP/PIN) mid-connect.

Instantiated by :class:`ConnectionsPage` when :meth:`OpenVpnService.connect`
raises/streams a prompt that has no saved keyring entry. Returns the typed
value via an ``asyncio.Future`` so the calling coroutine can simply
``await`` it, and optionally stores the value in the GNOME Keyring if the
user checks "Remember this".
"""

from __future__ import annotations

import asyncio

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


class AuthPromptDialog(Adw.AlertDialog):
    """Prompts for a single credential value in response to a CLI challenge."""

    def __init__(self, prompt_text: str, is_secret: bool, allow_remember: bool = True) -> None:
        super().__init__(heading="Authentication required", body=prompt_text)
        self._future: asyncio.Future = asyncio.get_event_loop().create_future()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._entry = Gtk.PasswordEntry() if is_secret else Gtk.Entry()
        if is_secret:
            self._entry.set_show_peek_icon(True)
        self._entry.set_activates_default(True)
        box.append(self._entry)

        self._remember_check = Gtk.CheckButton(label="Save in GNOME Keyring")
        self._remember_check.set_active(False)
        if allow_remember:
            box.append(self._remember_check)

        self.set_extra_child(box)
        self.add_response("cancel", "Cancel")
        self.add_response("submit", "Submit")
        self.set_response_appearance("submit", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("submit")
        self.set_close_response("cancel")
        self.connect("response", self._on_response)

    def _on_response(self, _dialog, response: str) -> None:
        if response == "submit":
            self._future.set_result((self._entry.get_text(), self._remember_check.get_active()))
        else:
            self._future.set_result((None, False))

    async def run(self, parent: Gtk.Widget) -> tuple[str | None, bool]:
        self.present(parent)
        return await self._future
