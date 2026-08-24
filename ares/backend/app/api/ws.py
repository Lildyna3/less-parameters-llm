"""WebSocket hub: one endpoint, many subscribers, JSON messages
{type: ticks|alert|account|status|takeover, data: ...}."""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect

from ..logging_setup import get_logger
from ..status import ComponentState, status_registry

log = get_logger("ws")


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        status_registry.set("websocket", ComponentState.ONLINE,
                            f"{len(self._clients)} client(s) connected")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        count = len(self._clients)
        status_registry.set(
            "websocket",
            ComponentState.ONLINE if count else ComponentState.DEGRADED,
            f"{count} client(s) connected" if count else "No clients connected",
        )

    async def broadcast(self, message: dict) -> None:
        if not self._clients:
            return
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def serve(self, ws: WebSocket) -> None:
        await self.connect(ws)
        try:
            while True:
                # Keep the socket alive; inbound messages are ping/no-ops.
                await ws.receive_text()
        except WebSocketDisconnect:
            await self.disconnect(ws)
        except Exception as exc:  # noqa: BLE001
            log.debug("ws closed: %s", exc)
            await self.disconnect(ws)


hub = WebSocketHub()
