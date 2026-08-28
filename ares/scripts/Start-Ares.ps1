#Requires -Version 5.1
<#
.SYNOPSIS
    Starts ARES on Windows and verifies it actually responds.

.DESCRIPTION
    Prepares dependencies if needed, starts the backend (which also serves the
    web app), then verifies the running application over HTTP. It reports
    SYSTEM READY only after the health endpoint and API answer for real —
    never merely because a process exists.

    Errors are reported in full: COMPONENT / STATUS / ERROR / LIKELY CAUSE /
    NEXT ACTION. Nothing is hidden behind "server unavailable".

.PARAMETER Port
    Port to serve on. Default 8000.

.PARAMETER Simulation
    Start with the labelled simulated market feed (for use without MT5).

.PARAMETER SkipBuild
    Do not rebuild the web app even if dist is missing or stale.

.PARAMETER Bridge
    Also start the Windows MT5 bridge in its own window.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Start-Ares.ps1
.EXAMPLE
    .\scripts\Start-Ares.ps1 -Port 8010 -Simulation
.EXAMPLE
    .\scripts\Start-Ares.ps1 -Bridge
#>
[CmdletBinding()]
param(
    [int]    $Port = 8000,
    [switch] $Simulation,
    [switch] $SkipBuild,
    [switch] $Bridge
)

$ErrorActionPreference = 'Stop'

function Write-Step([string] $Message) {
    Write-Host "[ares] $Message" -ForegroundColor Cyan
}

function Write-Problem {
    param(
        [string] $Component, [string] $Status, [string] $ErrorText,
        [string] $Cause, [string] $Action
    )
    Write-Host ''
    Write-Host $Component.ToUpper() -ForegroundColor White
    Write-Host $Status -ForegroundColor Red
    Write-Host ''
    if ($ErrorText) { Write-Host 'Error:';        Write-Host "  $ErrorText" -ForegroundColor Yellow }
    if ($Cause)     { Write-Host 'Likely cause:'; Write-Host "  $Cause" }
    if ($Action)    { Write-Host 'Action:';       Write-Host "  $Action" -ForegroundColor Green }
    Write-Host ''
}

$repo     = Split-Path -Parent $PSScriptRoot
$backend  = Join-Path $repo 'backend'
$frontend = Join-Path $repo 'frontend'
$venvPy   = Join-Path $backend '.venv\Scripts\python.exe'

Write-Host ''
Write-Host 'ARES — WINDOWS STARTUP' -ForegroundColor White
Write-Host "Repository: $repo" -ForegroundColor DarkGray

# ---- 1. dependencies ---------------------------------------------------------
Write-Step 'Checking dependencies…'

if (-not (Test-Path (Join-Path $backend 'app\main.py'))) {
    Write-Problem 'ARES REPOSITORY' 'NOT FOUND' `
        "backend\app\main.py is missing under $repo" `
        'This script is not inside the ares folder of the repository.' `
        'cd into the cloned ares folder and run .\scripts\Start-Ares.ps1 from there.'
    exit 1
}

$pythonCmd = $null
foreach ($candidate in @('py', 'python')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $version = (& $candidate --version 2>&1 | Out-String).Trim()
        if ($version -match 'Python\s+3') { $pythonCmd = $candidate; break }
    }
}
if (-not (Test-Path $venvPy)) {
    if (-not $pythonCmd) {
        Write-Problem 'PYTHON' 'MISSING' `
            'No Python 3 interpreter found on PATH (tried "py" and "python").' `
            'Python is not installed, or was installed without adding it to PATH.' `
            'Install Python 3.11+ from https://python.org/downloads, tick "Add python.exe to PATH", reopen PowerShell.'
        exit 1
    }
    Write-Step 'Creating the backend virtual environment…'
    & $pythonCmd -m venv (Join-Path $backend '.venv')
    if ($LASTEXITCODE -ne 0) {
        Write-Problem 'PYTHON VIRTUALENV' 'FAILED' `
            "'$pythonCmd -m venv' exited with code $LASTEXITCODE" `
            'The venv module is unavailable or the folder is not writable.' `
            'Run the command manually to see the full error, or reinstall Python with the standard library included.'
        exit 1
    }
}

$needPackages = & $venvPy -c "import importlib.util as u; print(all(u.find_spec(m) for m in ('fastapi','uvicorn','sqlalchemy','httpx')))" 2>&1
if ("$needPackages".Trim() -ne 'True') {
    Write-Step 'Installing backend packages…'
    & $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $backend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        Write-Problem 'BACKEND PACKAGES' 'INSTALL FAILED' `
            "pip exited with code $LASTEXITCODE" `
            'No network access, a proxy blocking PyPI, or a compiler missing for a dependency.' `
            "Run manually to see the full output: $venvPy -m pip install -r backend\requirements.txt"
        exit 1
    }
}

if (-not $SkipBuild -and -not (Test-Path (Join-Path $frontend 'dist\index.html'))) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Problem 'WEB APP BUILD' 'CANNOT BUILD' `
            'npm is not on PATH.' `
            'Node.js is not installed, or PowerShell was opened before installing it.' `
            'Install Node.js LTS from https://nodejs.org, reopen PowerShell, then re-run this script. (Or pass -SkipBuild to run API-only.)'
        exit 1
    }
    if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
        Write-Step 'Installing web app packages (first run, this takes a minute)…'
        npm install --prefix $frontend --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            Write-Problem 'WEB APP PACKAGES' 'INSTALL FAILED' "npm install exited with code $LASTEXITCODE" `
                'No network access, or a proxy blocking the npm registry.' `
                "Run manually: npm install --prefix $frontend"
            exit 1
        }
    }
    Write-Step 'Building the web app…'
    npm run build --prefix $frontend
    if ($LASTEXITCODE -ne 0) {
        Write-Problem 'WEB APP BUILD' 'BUILD FAILED' "npm run build exited with code $LASTEXITCODE" `
            'A TypeScript or bundler error in the frontend.' `
            "Run manually to see the errors: npm run build --prefix $frontend"
        exit 1
    }
}

# ---- 2. port ------------------------------------------------------------------
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    Write-Problem 'ARES BACKEND' 'CANNOT START' `
        "Port $Port is already in use by $($owner.ProcessName) (PID $($listener.OwningProcess))." `
        'A previous ARES instance is still running, or another application holds the port.' `
        "Stop it with:  Stop-Process -Id $($listener.OwningProcess)`n  Or start on another port:  .\scripts\Start-Ares.ps1 -Port 8010"
    exit 1
}

# ---- 3. start -------------------------------------------------------------------
if ($Simulation) {
    $env:ARES_MARKET_DATA__MODE = 'simulation'
    Write-Step 'Simulated market data enabled — every price is labelled SIMULATED.'
}
$env:ARES_SYSTEM__HOST = '0.0.0.0'   # reachable from your phone on the same network
$env:ARES_SYSTEM__PORT = "$Port"

$logDir = Join-Path $repo 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$logFile = Join-Path $logDir "ares-$stamp.log"

Write-Step "Starting the ARES backend on port $Port…"
$process = Start-Process -FilePath $venvPy `
    -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port',"$Port",'--proxy-headers') `
    -WorkingDirectory $backend -PassThru -RedirectStandardOutput $logFile `
    -RedirectStandardError "$logFile.err" -WindowStyle Hidden

# ---- 4. verify it actually answers -------------------------------------------------
Write-Step 'Verifying the application responds…'
$health = $null
for ($attempt = 1; $attempt -le 30; $attempt++) {
    if ($process.HasExited) { break }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        break
    } catch { Start-Sleep -Milliseconds 700 }
}

if (-not $health) {
    $stderr = if (Test-Path "$logFile.err") { (Get-Content "$logFile.err" -Tail 15) -join "`n" } else { '' }
    $stdout = if (Test-Path $logFile)       { (Get-Content $logFile -Tail 15) -join "`n" }       else { '' }
    Write-Problem 'ARES BACKEND' 'OFFLINE' `
        (($stderr + "`n" + $stdout).Trim()) `
        'The backend process exited or never began serving.' `
        "Full log: $logFile`n  Run it in the foreground to see everything:`n    cd $backend`n    .venv\Scripts\python.exe -m uvicorn app.main:app --port $Port"
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    exit 1
}

# The web app itself must be served, not just the API.
$webOk = $false
try {
    $page = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec 5 -UseBasicParsing
    $webOk = ($page.StatusCode -eq 200)
} catch { $webOk = $false }

# ---- 5. optional bridge ---------------------------------------------------------------
if ($Bridge) {
    $bridgeScript = Join-Path $repo 'bridge\ares_mt5_bridge.py'
    if (-not (Test-Path $bridgeScript)) {
        Write-Problem 'MT5 BRIDGE' 'NOT STARTED' "bridge\ares_mt5_bridge.py not found under $repo" `
            'The clone is incomplete.' 'Re-clone the repository.'
    } elseif (-not $env:ARES_BRIDGE_TOKEN) {
        Write-Problem 'MT5 BRIDGE' 'NOT STARTED' 'ARES_BRIDGE_TOKEN is not set.' `
            'The bridge and the backend must share a token.' `
            "Add ARES_BRIDGE_TOKEN=<random string> to $repo\.env and to bridge\.env, then re-run with -Bridge."
    } else {
        Write-Step 'Starting the MT5 bridge in a separate window…'
        Start-Process -FilePath $venvPy -ArgumentList @($bridgeScript) `
            -WorkingDirectory (Join-Path $repo 'bridge')
    }
}

# ---- 6. report ---------------------------------------------------------------------------
$components = $health.components
$mt5State   = $components.mt5.state
$dataState  = $components.market_data.state

Write-Host ''
Write-Host 'SYSTEM READY' -ForegroundColor Green
Write-Host '(verified: the health endpoint and API responded over HTTP)' -ForegroundColor DarkGray
Write-Host ''
Write-Host ('  Web app      http://localhost:{0}' -f $Port) -ForegroundColor White
$lan = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        Select-Object -First 1).IPAddress
if ($lan) { Write-Host ('  From a phone http://{0}:{1}   (same Wi-Fi)' -f $lan, $Port) -ForegroundColor White }
Write-Host ('  API docs     http://localhost:{0}/docs' -f $Port) -ForegroundColor DarkGray
Write-Host ''
Write-Host ('  Backend      ONLINE   (PID {0})' -f $process.Id)
Write-Host ('  Web app      {0}' -f $(if ($webOk) { 'SERVED' } else { 'NOT SERVED — run: npm run build --prefix frontend' }))
Write-Host ('  Market data  {0}   {1}' -f $dataState, $components.market_data.reason)
Write-Host ('  MT5          {0}   {1}' -f $mt5State, $components.mt5.reason)
Write-Host ''
if ($mt5State -ne 'ONLINE') {
    Write-Host '  MT5 is not connected yet. Start MetaTrader 5, log into your DEMO account,' -ForegroundColor DarkYellow
    Write-Host '  then run:  .\scripts\Verify-MT5.ps1' -ForegroundColor DarkYellow
    Write-Host ''
}
Write-Host ('  Log file     {0}' -f $logFile) -ForegroundColor DarkGray
Write-Host ('  Stop ARES    Stop-Process -Id {0}' -f $process.Id) -ForegroundColor DarkGray
Write-Host ''
