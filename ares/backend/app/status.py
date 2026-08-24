"""System status registry.

Every subsystem reports one of ONLINE / DEGRADED / OFFLINE plus a human
reason. Components start OFFLINE and are only marked ONLINE after a real,
verified check — never merely because the application started.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ComponentState(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


@dataclass
class ComponentStatus:
    state: ComponentState = ComponentState.OFFLINE
    reason: str = "Not initialized"
    detail: dict = field(default_factory=dict)
    updated_at: str = ""

    def as_dict(self) -> dict:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "detail": self.detail,
            "updated_at": self.updated_at,
        }


COMPONENTS = (
    "mt5",
    "market_data",
    "ai",
    "database",
    "websocket",
    "web_intelligence",
    "execution",
)


class StatusRegistry:
    def __init__(self) -> None:
        self._components: dict[str, ComponentStatus] = {
            name: ComponentStatus() for name in COMPONENTS
        }

    def set(
        self,
        component: str,
        state: ComponentState,
        reason: str,
        detail: dict | None = None,
    ) -> None:
        if component not in self._components:
            self._components[component] = ComponentStatus()
        entry = self._components[component]
        entry.state = state
        entry.reason = reason
        entry.detail = detail or {}
        entry.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def get(self, component: str) -> ComponentStatus:
        return self._components[component]

    def snapshot(self) -> dict:
        return {name: status.as_dict() for name, status in self._components.items()}

    @property
    def overall(self) -> ComponentState:
        states = [s.state for s in self._components.values()]
        if all(s == ComponentState.ONLINE for s in states):
            return ComponentState.ONLINE
        if any(s == ComponentState.ONLINE for s in states):
            return ComponentState.DEGRADED
        return ComponentState.OFFLINE


status_registry = StatusRegistry()
