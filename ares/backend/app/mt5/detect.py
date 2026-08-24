"""MetaTrader 5 terminal + Python package detection.

Detection is honest and three-tiered; each tier is reported separately so the
UI can distinguish TERMINAL FOUND from CONNECTED from MARKET DATA STREAMING:

  1. platform_supported  – the official MetaTrader5 package is Windows-only.
  2. package_available   – `import MetaTrader5` succeeds.
  3. terminal_path       – a terminal64.exe was located (configured or common
                           install locations).
"""

from __future__ import annotations

import importlib.util
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

COMMON_WINDOWS_PATHS = [
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal.exe",
    r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
    r"C:\Program Files\FTMO MetaTrader 5\terminal64.exe",
    r"C:\Program Files\IC Markets Global MT5 Terminal\terminal64.exe",
]


@dataclass
class MT5Detection:
    platform_supported: bool
    package_available: bool
    terminal_path: str | None
    os_name: str
    notes: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.platform_supported and self.package_available

    def as_dict(self) -> dict:
        return {
            "platform_supported": self.platform_supported,
            "package_available": self.package_available,
            "terminal_found": self.terminal_path is not None,
            "terminal_path": self.terminal_path,
            "os": self.os_name,
            "notes": self.notes,
        }


def detect_mt5(configured_path: str | None = None) -> MT5Detection:
    os_name = platform.system()
    notes: list[str] = []

    platform_supported = os_name == "Windows"
    if not platform_supported:
        notes.append(
            f"The official MetaTrader5 Python package requires Windows; this host runs {os_name}. "
            "Run the ARES backend on a Windows machine (or a Windows VM/VPS) with MT5 installed to connect."
        )

    package_available = importlib.util.find_spec("MetaTrader5") is not None
    if not package_available:
        notes.append("Python package 'MetaTrader5' is not installed (pip install MetaTrader5).")

    terminal_path: str | None = None
    candidates: list[str] = []
    if configured_path:
        candidates.append(configured_path)
    if os_name == "Windows":
        candidates.extend(COMMON_WINDOWS_PATHS)
        # Scan per-broker installs under Program Files.
        for base in (r"C:\Program Files", r"C:\Program Files (x86)"):
            base_path = Path(base)
            if base_path.exists():
                for exe in base_path.glob("*/terminal64.exe"):
                    candidates.append(str(exe))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            terminal_path = candidate
            break

    if terminal_path is None:
        if configured_path:
            notes.append(f"Configured MT5_PATH does not exist: {configured_path}")
        notes.append(
            "MetaTrader 5 terminal not found. Please install MT5 or configure MT5_PATH."
        )

    return MT5Detection(
        platform_supported=platform_supported,
        package_available=package_available,
        terminal_path=terminal_path,
        os_name=os_name,
        notes=notes,
    )
