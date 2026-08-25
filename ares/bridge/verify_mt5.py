#!/usr/bin/env python3
"""ARES MT5 verification — TESTS 1..10 against the REAL Windows terminal.

Run this on the Windows machine that has MetaTrader 5 installed, after logging
the terminal into your DEMO account:

    .venv\\Scripts\\python.exe bridge\\verify_mt5.py

Every check talks to the actual terminal through the official MetaTrader5
package. Nothing here is simulated: if a check cannot be performed, it is
reported as FAIL or SKIP with the real reason, never as a pass.

Test 9/10 (order round-trip) uses MT5's `order_check`, which asks the broker to
validate an order WITHOUT placing it. No position is opened and no live-money
path exists in this script.
"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone

RESET, BOLD = "\033[0m", "\033[1m"
GREEN, RED, YELLOW, GREY = "\033[32m", "\033[31m", "\033[33m", "\033[90m"

results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> bool:
    colour = {"PASS": GREEN, "FAIL": RED, "SKIP": YELLOW}.get(status, "")
    print(f"  {name:<38} {colour}{status:<6}{RESET} {detail}")
    results.append((name, status, detail))
    return status == "PASS"


def mask(value) -> str:
    text = str(value)
    return "*" * max(0, len(text) - 4) + text[-4:]


def main() -> int:
    print()
    print(f"{BOLD}ARES — MT5 TERMINAL VERIFICATION{RESET}")
    print(f"{GREY}Host: {platform.node()} ({platform.system()} {platform.release()}) "
          f"· {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC{RESET}")
    print()

    if platform.system() != "Windows":
        print(f"{RED}This machine is not Windows ({platform.system()}).{RESET}")
        print("The MetaTrader5 package exists only for Windows. Run this on the")
        print("Surface (or a Windows VM) that has MetaTrader 5 installed.")
        return 2

    # ---- TEST 1: the bridge's own prerequisites -----------------------------
    print(f"{BOLD}TEST 1  Bridge prerequisites{RESET}")
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        record("MetaTrader5 package importable", "FAIL", str(exc))
        print()
        print(f"{RED}Cannot continue without the MetaTrader5 package.{RESET}")
        print("  Fix:  .venv\\Scripts\\python.exe -m pip install MetaTrader5")
        return 1
    record("MetaTrader5 package importable", "PASS", f"version {mt5.__version__}")

    try:
        import websockets  # noqa: F401
        record("websockets package importable", "PASS", "bridge can dial ARES")
    except ImportError:
        record("websockets package importable", "FAIL",
               "pip install websockets  (the bridge cannot connect without it)")

    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    path = os.getenv("MT5_PATH") or None
    if login and password and server:
        record("Credentials present in environment", "PASS", f"login {mask(login)} · {server}")
    else:
        record("Credentials present in environment", "SKIP",
               "MT5_LOGIN/MT5_PASSWORD/MT5_SERVER not all set; using the terminal's current session")

    # ---- TEST 2: terminal detected -------------------------------------------
    print()
    print(f"{BOLD}TEST 2  MT5 terminal detected{RESET}")
    candidates = [path] if path else []
    candidates += [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal.exe",
    ]
    found = next((c for c in candidates if c and os.path.isfile(c)), None)
    if found:
        record("Terminal executable located", "PASS", found)
    else:
        record("Terminal executable located", "SKIP",
               "not at a common path; MT5 may still be found automatically")

    # ---- TEST 3: terminal initialized -----------------------------------------
    print()
    print(f"{BOLD}TEST 3  MT5 terminal initialized{RESET}")
    kwargs = {}
    if login and password and server:
        kwargs = {"login": int(login), "password": password, "server": server}
    if found:
        kwargs["path"] = found

    if not mt5.initialize(**kwargs):
        code, message = mt5.last_error()
        record("mt5.initialize()", "FAIL", f"({code}) {message}")
        print()
        print(f"{RED}Cannot continue: the terminal did not initialize.{RESET}")
        print("  Common causes:")
        print("   -10003 / -10005  MetaTrader 5 is not running — start it and log in.")
        print("   -6               Authorization failed — check MT5_LOGIN/PASSWORD/SERVER.")
        print("  Then re-run this script.")
        return 1
    record("mt5.initialize()", "PASS", "terminal responded")

    terminal = mt5.terminal_info()
    if terminal:
        record("Terminal info retrieved", "PASS",
               f"build {terminal.build} · connected={terminal.connected} · trade_allowed={terminal.trade_allowed}")
        if not terminal.connected:
            record("Terminal connected to broker", "FAIL",
                   "the terminal reports it is NOT connected to the broker")
    else:
        record("Terminal info retrieved", "FAIL", "terminal_info() returned nothing")

    # ---- TEST 4 + 5: account and broker ------------------------------------------
    print()
    print(f"{BOLD}TEST 4  Demo account detected{RESET}")
    account = mt5.account_info()
    if account is None:
        record("account_info()", "FAIL", "empty — the login was rejected")
    else:
        is_demo = account.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        record("Account information", "PASS", f"login {mask(account.login)} · {account.currency}")
        record("Account is a DEMO account", "PASS" if is_demo else "FAIL",
               "DEMO" if is_demo else
               f"trade_mode={account.trade_mode} — ARES will not execute on a non-demo account")

        print()
        print(f"{BOLD}TEST 5  Broker / server detected{RESET}")
        record("Broker", "PASS", account.company)
        record("Server", "PASS", account.server)
        record("Trading permitted by broker", "PASS" if account.trade_allowed else "FAIL",
               "trade_allowed=True" if account.trade_allowed else
               "trade_allowed=False — the account cannot trade")

    # ---- TEST 6: live tick ----------------------------------------------------------
    print()
    print(f"{BOLD}TEST 6  Live tick retrieved{RESET}")
    probe_symbol, tick = None, None
    for symbol in ("EURUSD", "XAUUSD", "USDJPY", "GBPUSD"):
        if mt5.symbol_select(symbol, True):
            tick = mt5.symbol_info_tick(symbol)
            if tick is not None and tick.bid:
                probe_symbol = symbol
                break
    if tick and probe_symbol:
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(tick.time, tz=timezone.utc)
        record(f"Live tick for {probe_symbol}", "PASS",
               f"bid={tick.bid} ask={tick.ask} · {int(age.total_seconds())}s old")
        record("Symbols available", "PASS", f"{len(mt5.symbols_get() or [])} symbols")
    else:
        record("Live tick", "FAIL",
               "no tick from any probe symbol — the broker feed is not delivering data")

    # ---- TEST 7: candles (what ARES analyses) ------------------------------------------
    print()
    print(f"{BOLD}TEST 7  Account + market history retrieved{RESET}")
    if probe_symbol:
        rates = mt5.copy_rates_from_pos(probe_symbol, mt5.TIMEFRAME_M15, 0, 100)
        if rates is not None and len(rates):
            record(f"M15 candles for {probe_symbol}", "PASS", f"{len(rates)} bars")
        else:
            record(f"M15 candles for {probe_symbol}", "FAIL", "copy_rates_from_pos returned nothing")
    else:
        record("Candle history", "SKIP", "no probe symbol available")

    # ---- TEST 8: open positions -----------------------------------------------------------
    print()
    print(f"{BOLD}TEST 8  Open positions retrieved{RESET}")
    positions = mt5.positions_get()
    if positions is None:
        code, message = mt5.last_error()
        record("positions_get()", "FAIL", f"({code}) {message}")
    else:
        record("positions_get()", "PASS", f"{len(positions)} open position(s)")
        orders = mt5.orders_get()
        record("orders_get()", "PASS" if orders is not None else "FAIL",
               f"{len(orders or [])} pending order(s)")

    # ---- TEST 9 + 10: order request reaches MT5 and answers -----------------------------------
    print()
    print(f"{BOLD}TEST 9/10  Order request reaches MT5 and returns a response{RESET}")
    print(f"{GREY}  Uses order_check(): the broker validates the order WITHOUT placing it.{RESET}")
    if probe_symbol and account is not None:
        info = mt5.symbol_info(probe_symbol)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": probe_symbol,
            "volume": info.volume_min,
            "type": mt5.ORDER_TYPE_BUY,
            "price": mt5.symbol_info_tick(probe_symbol).ask,
            "deviation": 20,
            "magic": 0,
            "comment": "ARES verification (not placed)",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        check = mt5.order_check(request)
        if check is None:
            code, message = mt5.last_error()
            record("Order request reached MT5", "FAIL", f"({code}) {message}")
        else:
            record("Order request reached MT5", "PASS",
                   f"volume {info.volume_min} {probe_symbol} submitted for validation")
            ok = check.retcode == 0
            record("Execution response returned", "PASS" if ok else "FAIL",
                   f"retcode={check.retcode} · {check.comment} · "
                   f"margin required {check.margin} {account.currency}")
            if not ok:
                print(f"{GREY}    A non-zero retcode is the broker declining this test order "
                      f"(often insufficient free margin). The round-trip itself worked.{RESET}")
    else:
        record("Order round-trip", "SKIP", "no tradable symbol or account available")

    mt5.shutdown()

    # ---- verdict ------------------------------------------------------------------------------
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    skipped = sum(1 for _, s, _ in results if s == "SKIP")

    print()
    print(f"{BOLD}RESULT{RESET}")
    print(f"  {GREEN}{passed} passed{RESET} · {RED}{failed} failed{RESET} · {YELLOW}{skipped} skipped{RESET}")
    print()
    if failed == 0:
        print(f"{GREEN}MT5 TERMINAL VERIFIED{RESET} — the terminal, the demo account, the broker feed")
        print("and the order round-trip all responded. The ARES bridge can serve real data.")
        print()
        print("Next:  .venv\\Scripts\\python.exe bridge\\ares_mt5_bridge.py")
    else:
        print(f"{RED}NOT VERIFIED{RESET} — fix the FAIL rows above and re-run.")
        print("ARES will keep reporting MT5 as offline until this passes; it will not")
        print("display a connection it does not have.")
    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(130)
