"""Background health monitoring: openvpn3 D-Bus service, connectivity, tunnel health.

Runs a periodic asyncio loop (driven by the shared GLib-integrated loop —
see :mod:`openvpn3_gui.utils.async_utils`) and publishes a
:class:`HealthSnapshot` to subscribers such as the Dashboard page and the
tray status icon.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Callable

from openvpn3_gui.dbus.session_manager import DBusAvailability, check_dbus_service
from openvpn3_gui.services.network_service import NetworkService
from openvpn3_gui.services.openvpn_service import OpenVpnService

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class HealthSnapshot:
    openvpn3_service_ok: bool
    dbus_ok: bool
    internet_ok: bool
    tunnel_ok: bool
    active_session_count: int


class MonitorService:
    def __init__(
        self,
        openvpn_service: OpenVpnService,
        network_service: NetworkService,
        interval_seconds: float = 10.0,
    ) -> None:
        self._openvpn = openvpn_service
        self._network = network_service
        self._interval = interval_seconds
        self._listeners: list[Callable[[HealthSnapshot], None]] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def subscribe(self, callback: Callable[[HealthSnapshot], None]) -> None:
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[HealthSnapshot], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._run_loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _run_loop(self) -> None:
        while self._running:
            try:
                snapshot = await self._collect_once()
                for cb in list(self._listeners):
                    try:
                        cb(snapshot)
                    except Exception:  # pragma: no cover
                        logger.exception("Monitor listener failed")
            except Exception:  # noqa: BLE001
                logger.exception("Health monitor iteration failed")
            await asyncio.sleep(self._interval)

    async def _collect_once(self) -> HealthSnapshot:
        service_ok = await self._openvpn.check_service_available()
        dbus_status: DBusAvailability = await check_dbus_service()
        internet_ok = (await self._network.public_ip()) is not None
        sessions = await self._openvpn.list_sessions()
        active = [s for s in sessions if s.is_active]
        tunnel_ok = bool(active) and internet_ok
        return HealthSnapshot(
            openvpn3_service_ok=service_ok,
            dbus_ok=dbus_status.available,
            internet_ok=internet_ok,
            tunnel_ok=tunnel_ok,
            active_session_count=len(active),
        )
