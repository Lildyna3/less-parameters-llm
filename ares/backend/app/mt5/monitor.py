"""Persistent MT5 connection monitor.

Periodically verifies the managed connection, disables execution the moment
the link drops, attempts safe reconnection (bounded backoff, one connection —
never a new connection per request), and updates the status registry so the
UI always shows the genuine state.
"""

from __future__ import annotations

import asyncio

from ..logging_setup import get_logger
from ..status import ComponentState, status_registry
from .adapter import ConnectionState, MT5Adapter

log = get_logger("mt5.monitor")


class MT5ConnectionMonitor:
    def __init__(self, adapter: MT5Adapter, interval_seconds: float = 10.0) -> None:
        self.adapter = adapter
        self.interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._was_connected = False
        self.on_connection_lost = None   # async callables set by main
        self.on_connection_restored = None

    def _publish_status(self) -> None:
        adapter = self.adapter
        if adapter.state == ConnectionState.CONNECTED:
            status_registry.set("mt5", ComponentState.ONLINE, "Connected and verified",
                                adapter.status_payload())
        elif adapter.state == ConnectionState.CONNECTING:
            status_registry.set("mt5", ComponentState.DEGRADED, "Connecting…",
                                adapter.status_payload())
        else:
            reason = adapter.last_error or "Not connected"
            status_registry.set("mt5", ComponentState.OFFLINE, reason,
                                adapter.status_payload())

    async def start(self) -> None:
        # Initial connection attempt (truthful failure is fine).
        await self.adapter.connect()
        self._was_connected = self.adapter.connected
        self._publish_status()
        self._task = asyncio.create_task(self._loop(), name="mt5-monitor")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.adapter.disconnect()
        self._publish_status()

    async def _loop(self) -> None:
        # If MT5 can never work here (wrong OS / package missing), don't spin:
        # re-check detection occasionally in case the environment changes.
        while True:
            try:
                await asyncio.sleep(self.interval)
                if not self.adapter.detection.usable or not self.adapter.settings.credentials_configured:
                    continue

                healthy = await self.adapter.health_check()
                if self._was_connected and not healthy:
                    log.warning("MT5 connection lost: %s", self.adapter.last_error)
                    self._was_connected = False
                    self._publish_status()
                    if self.on_connection_lost:
                        await self.on_connection_lost()

                if not self.adapter.connected:
                    restored = await self.adapter.connect()
                    self._publish_status()
                    if restored and not self._was_connected:
                        log.info("MT5 connection restored")
                        self._was_connected = True
                        if self.on_connection_restored:
                            await self.on_connection_restored()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - monitor must survive
                log.error("MT5 monitor iteration failed: %s", exc)
