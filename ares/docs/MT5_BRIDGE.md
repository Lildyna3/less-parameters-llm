# ARES MT5 Bridge — setup and verification

## Why a bridge exists (the root cause)

The `MetaTrader5` Python package is a thin wrapper around the MetaTrader 5
**Windows terminal's** IPC interface. It ships only as a Windows wheel and has
no Linux or macOS build. This is a property of the vendor's software, not a
packaging problem on your machine:

* `pip install MetaTrader5` on Linux fails or installs nothing usable.
* No `MT5_PATH` value helps — there is no Linux terminal binary to point at.
* Running the terminal under Wine is unsupported and unreliable for trading.

So a Linux or cloud ARES backend **can never** talk to MT5 directly. Rather
than pretend otherwise, ARES splits the problem:

```
phone / laptop
   |
   v
ARES web app  ──►  ARES backend (Linux/cloud)
                        ▲
                        │  authenticated WebSocket, bridge dials OUT
                        │
                 ARES MT5 bridge (Windows)
                        |
                        v
                 MetaTrader 5 terminal ──► broker
```

The bridge connects **outward** to ARES, so the Windows machine needs no public
IP, no port forwarding and no inbound firewall rule.

## What you need

* A Windows machine that stays on: a spare PC, a Windows VM, or a cheap Windows
  VPS (any provider). It must run MetaTrader 5 logged into your **demo**
  account.
* Python 3.10+ on that Windows machine.
* Your ARES backend reachable from it (a URL, or `ws://127.0.0.1:8000` if you
  run both on the same machine).

## 1. Configure the backend

Set a shared secret on the ARES server, in its `.env`:

```
ARES_BRIDGE_TOKEN=<a long random string>
```

Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Restart ARES. Settings → Connections now shows **AUTHENTICATION REQUIRED →
AWAITING BRIDGE** instead of a fake connection.

## 2. Install the bridge on Windows

Copy `ares/bridge/ares_mt5_bridge.py` to the Windows machine, then:

```
py -m pip install MetaTrader5 websockets python-dotenv
```

Create a `.env` **next to the script** (never commit it):

```
ARES_BACKEND_URL=wss://your-ares-host/bridge/ws
ARES_BRIDGE_TOKEN=<the same token as the backend>
MT5_LOGIN=12345678
MT5_PASSWORD=your-demo-password
MT5_SERVER=Your-Broker-Demo
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

`MT5_PATH` is optional — set it only if auto-detection fails.

Use `ws://` instead of `wss://` only when the backend is on the same machine.
Anywhere else, terminate TLS in front of ARES: the bridge token travels in the
handshake.

## 3. Run it

```
py ares_mt5_bridge.py
```

Expected output:

```
[ares-bridge] attached to wss://your-ares-host/bridge/ws | MT5 state: CONNECTED
```

To keep it running after logout, register it as a scheduled task
(`schtasks /create /tn ARESBridge /tr "py C:\ares\ares_mt5_bridge.py" /sc onstart /ru SYSTEM`)
or wrap it with NSSM as a Windows service.

## 4. Verify the connection is genuine

ARES deliberately makes a fake "connected" state impossible. Check all four:

1. **Settings → Connections** shows `CONNECTED`, plus the bridge host name,
   your broker, server and a **masked** account number. If the terminal is
   closed or the broker drops, it shows `MT5 TERMINAL NOT RUNNING` or
   `BROKER DISCONNECTED` within ~15 seconds instead.
2. **`GET /api/bridge`** returns `"connected": true` **and** an `account`
   object. `attached: true` with `connected: false` means the bridge is running
   but its terminal is not actually trading-ready.
3. **Live prices flow.** Markets shows quotes tagged `MT5` (not `SIMULATED`),
   and the ticks change. ARES only marks market data ONLINE after a real tick
   arrives.
4. **Pull the plug test.** Close the MT5 terminal. Within a few seconds ARES
   must flip to an offline state and disable execution. If it keeps showing
   prices, something is wrong — report it; ARES is designed never to do that.

The status is derived from the bridge's heartbeat, which carries the terminal's
own state. A bridge that stops heartbeating for 45 seconds is treated as gone.

## Security notes

* Your MT5 password stays on the Windows machine, in that machine's local
  `.env`. It is used only for the local terminal login call. It is never sent
  to ARES, never logged, never shown in the UI, and never sent to any AI
  provider.
* ARES receives only non-sensitive account facts: masked login, broker, server,
  currency, balance, equity, leverage, trading permission and demo/live flag.
* The bridge token authenticates the bridge to ARES. Treat it like a password
  and rotate it by changing both `.env` files.
* Connection is not permission. Even with a live bridge, ARES stays in
  DEMO/PAPER execution: every order passes the risk engine, and Takeover Mode
  needs your explicit authorization.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `AUTHENTICATION REQUIRED` | no `ARES_BRIDGE_TOKEN` on the server | set it and restart |
| bridge exits `unauthorized` | tokens differ | make both `.env` values identical |
| `MT5 TERMINAL NOT RUNNING` | terminal closed or `initialize` failed | start MT5, log in, retry |
| `BROKER DISCONNECTED` | terminal open but no market data | check the terminal's own connection status bar |
| `AUTHENTICATION REQUIRED` after attaching | login rejected by the broker | re-check `MT5_LOGIN`/`MT5_PASSWORD`/`MT5_SERVER` |
| bridge reconnect loop | backend URL wrong or unreachable | verify `ARES_BACKEND_URL`, TLS, and that `/bridge/ws` is not blocked by a proxy |
