# Running ARES on your Windows Surface

This is the machine that can reach MetaTrader 5. Everything below is Windows
PowerShell — no Linux commands, no `.venv/bin/`, no `/tmp` paths.

> **Which shell?** Open **Windows PowerShell** from the Start menu. The scripts
> declare `#Requires -Version 5.1`, so the version that ships with Windows is
> enough; PowerShell 7 also works.

---

## 1. Get the code

```powershell
cd $HOME\Documents
git clone <your-repo-url> ares-repo
cd ares-repo\ares
```

If Git is not installed, get it from <https://git-scm.com/download/win>, or
download the repository as a ZIP and extract it.

From here on, every command assumes you are in that `ares` folder. Confirm:

```powershell
Get-Location
Test-Path .\backend\app\main.py      # must print True
```

## 2. Audit the machine (changes nothing)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Preflight-Ares.ps1
```

It reports Node, npm, Python, the ARES virtual environment, the frontend build,
your `.env`, port availability, and whether MetaTrader 5 is installed and
running — with a concrete action for anything missing.

Install whatever it flags:

| Missing | Where to get it |
|---|---|
| Node.js | <https://nodejs.org> (LTS installer) |
| Python 3.11+ | <https://python.org/downloads> — tick **Add python.exe to PATH** |
| MetaTrader 5 | your broker's download, or <https://www.metatrader5.com/en/download> |

Reopen PowerShell after installing anything, so PATH changes take effect.

## 3. Configure

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in at least:

```
ARES_BRIDGE_TOKEN=<a long random string>
MT5_LOGIN=<your demo login>
MT5_PASSWORD=<your demo password>
MT5_SERVER=<your demo server, exactly as MT5 shows it>
```

Generate a token:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`.env` is git-ignored. Never commit it, and never paste its contents into chat.

## 4. Start ARES

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Start-Ares.ps1
```

On the first run it creates the virtual environment, installs backend packages,
and builds the web app. Then it starts the backend and **verifies over HTTP**
that the health endpoint and API actually answer before printing:

```
SYSTEM READY
  Web app      http://localhost:8000
  From a phone http://192.168.x.x:8000   (same Wi-Fi)
```

Useful variants:

```powershell
.\scripts\Start-Ares.ps1 -Simulation      # no MT5 yet: labelled simulated feed
.\scripts\Start-Ares.ps1 -Port 8010       # port 8000 taken
.\scripts\Start-Ares.ps1 -Bridge          # also start the MT5 bridge
```

If it cannot start, it prints the component, the real error, the likely cause
and the next action — including the exact command to run the backend in the
foreground and see everything.

Stop ARES with the `Stop-Process -Id <PID>` line it prints, or:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## 5. Verify MetaTrader 5 (the ten tests)

1. Start **MetaTrader 5** and log into your **demo** account.
2. Confirm the terminal's status bar bottom-right shows a live connection.
3. Then:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Verify-MT5.ps1 -InstallMissing
```

`-InstallMissing` installs the Windows-only `MetaTrader5` package (plus
`websockets` and `python-dotenv`) into the ARES environment on first run.

It runs the full suite against the **real** terminal:

| # | Test |
|---|---|
| 1 | Bridge prerequisites (MetaTrader5 + websockets importable, credentials present) |
| 2 | MT5 terminal executable detected |
| 3 | `mt5.initialize()` succeeds; terminal build and connection state |
| 4 | Account retrieved **and confirmed to be a DEMO account** |
| 5 | Broker and server identified; trading permitted |
| 6 | A live tick retrieved, with its age |
| 7 | Candle history retrieved (what ARES analyses) |
| 8 | Open positions and pending orders retrieved |
| 9 | An order request reaches MT5 (`order_check`, validated **not placed**) |
| 10 | The execution response returns, with retcode and margin |

`MT5 TERMINAL VERIFIED` prints only when nothing failed. Anything else prints
the real MT5 error code and what it means.

No position is opened: test 9/10 uses `order_check`, which asks the broker to
validate an order without placing it. There is no live-money path in ARES.

## 6. Start the bridge

```powershell
.\backend\.venv\Scripts\python.exe .\bridge\ares_mt5_bridge.py
```

Leave that window open. Expected:

```
[ares-bridge] attached to ws://127.0.0.1:8000/bridge/ws | MT5 state: CONNECTED
```

To keep it running after you log out, register it as a scheduled task:

```powershell
$py = (Resolve-Path .\backend\.venv\Scripts\python.exe).Path
$sc = (Resolve-Path .\bridge\ares_mt5_bridge.py).Path
schtasks /create /tn "ARES MT5 Bridge" /tr "`"$py`" `"$sc`"" /sc onlogon /rl highest
```

## 7. Confirm what is actually connected

Open **Settings → Connections** in ARES. The **connection path** shows each
link on its own row, because these are four different things:

```
ARES backend    ONLINE      This process is serving the API.
Windows bridge  ONLINE      SURFACE (Windows 11) · bridge v1.0.0
MT5 terminal    ONLINE      C:\Program Files\MetaTrader 5\terminal64.exe
Broker          ONLINE      Your Broker · Your-Demo · DEMO
```

Read it as a chain — the first row that is not ONLINE is your problem:

| Row | OFFLINE means |
|---|---|
| Windows bridge | the bridge is not running, or the token does not match |
| MT5 terminal | the bridge is running, but MetaTrader 5 is closed or the login failed |
| Broker | the terminal is open, but it has no live broker connection |

A bridge that reports no MetaTrader5 package shows **DEGRADED** and the
terminal row shows **UNVERIFIED**: ARES will not present a protocol test client
as live MT5 data.

## 8. Reach ARES from your phone

While `Start-Ares.ps1` is running, use the `From a phone` URL it printed (both
devices on the same Wi-Fi). If it does not load, allow the port once:

```powershell
# Run PowerShell as Administrator
New-NetFirewallRule -DisplayName "ARES 8000" -Direction Inbound `
  -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
```

For access from outside your network, and for installing ARES as a phone app,
see [DEPLOYMENT.md](DEPLOYMENT.md).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `running scripts is disabled on this system` | execution policy | prefix with `powershell -ExecutionPolicy Bypass -File` |
| `Port 8000 is already in use` | an old ARES is still running | the script prints the PID and the `Stop-Process` command |
| `initialize failed (-10003)` | MetaTrader 5 is not running | start it, log in, re-run `Verify-MT5.ps1` |
| `initialize failed (-6)` | login rejected | re-check `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` against the terminal |
| `Account is a DEMO account — FAIL` | a live account is logged in | log MT5 into a demo account; ARES will not execute on a live one |
| Bridge exits `unauthorized` | tokens differ | make `ARES_BRIDGE_TOKEN` identical in `.env` and the bridge's environment |
| `NEWS UNAVAILABLE` | no egress to news hosts | expected on a restricted network; ARES shows nothing rather than inventing |
