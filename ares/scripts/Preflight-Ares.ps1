#Requires -Version 5.1
<#
.SYNOPSIS
    ARES Windows preflight — audits this machine without changing anything.

.DESCRIPTION
    Run this on the Windows Surface before starting ARES. It reports what is
    installed, what is missing, and exactly what to do about each gap. It makes
    no changes and installs nothing.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Preflight-Ares.ps1
#>
[CmdletBinding()]
param(
    [int] $BackendPort = 8000
)

$ErrorActionPreference = 'Continue'
$script:Failures = 0
$script:Warnings = 0

function Write-Section([string] $Title) {
    Write-Host ''
    Write-Host $Title.ToUpper() -ForegroundColor Cyan
    Write-Host ('-' * $Title.Length) -ForegroundColor DarkGray
}

function Write-Check([string] $Name, [string] $State, [string] $Detail, [string] $Action) {
    $colour = switch ($State) {
        'OK'      { 'Green' }
        'WARN'    { 'Yellow' }
        'MISSING' { 'Red' }
        default   { 'Gray' }
    }
    if ($State -eq 'MISSING') { $script:Failures++ }
    if ($State -eq 'WARN')    { $script:Warnings++ }

    Write-Host ('  {0,-26}' -f $Name) -NoNewline
    Write-Host ('{0,-9}' -f $State) -ForegroundColor $colour -NoNewline
    Write-Host $Detail
    if ($Action) { Write-Host ('    -> ' + $Action) -ForegroundColor DarkYellow }
}

function Get-CommandVersion([string] $Command, [string] $VersionArg = '--version') {
    $cmd = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    try { return (& $Command $VersionArg 2>&1 | Select-Object -First 1).ToString().Trim() }
    catch { return 'installed (version unavailable)' }
}

Write-Host ''
Write-Host 'ARES — WINDOWS PREFLIGHT' -ForegroundColor White
Write-Host 'Audit only. Nothing is installed or modified.' -ForegroundColor DarkGray

# ---- machine ---------------------------------------------------------------
Write-Section 'Machine'
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
Write-Check 'Operating system' 'OK' "$($os.Caption) $($os.Version)" ''
Write-Check 'PowerShell' 'OK' $PSVersionTable.PSVersion.ToString() ''
Write-Check 'Working directory' 'OK' (Get-Location).Path ''

# ---- repository -------------------------------------------------------------
Write-Section 'ARES repository'
# Windows PowerShell 5.1 (the Surface default) has no ternary operator.
if ($PSScriptRoot) { $repo = Split-Path -Parent $PSScriptRoot } else { $repo = (Get-Location).Path }
$backend  = Join-Path $repo 'backend'
$frontend = Join-Path $repo 'frontend'
$bridge   = Join-Path $repo 'bridge'

if (Test-Path (Join-Path $backend 'app\main.py')) {
    Write-Check 'Repository root' 'OK' $repo ''
} else {
    Write-Check 'Repository root' 'MISSING' $repo 'Run this script from inside the ares folder of the cloned repository.'
}
foreach ($pair in @(@('backend', $backend), @('frontend', $frontend), @('bridge', $bridge))) {
    if (Test-Path $pair[1]) { Write-Check ("Folder: " + $pair[0]) 'OK' $pair[1] '' }
    else { Write-Check ("Folder: " + $pair[0]) 'MISSING' $pair[1] 'The clone looks incomplete; re-clone the repository.' }
}

# ---- toolchains --------------------------------------------------------------
Write-Section 'Toolchains'
$node = Get-CommandVersion 'node'
if ($node) {
    $major = [int](($node -replace '^v','') -split '\.')[0]
    if ($major -ge 20) { Write-Check 'Node.js' 'OK' $node '' }
    else { Write-Check 'Node.js' 'WARN' "$node (ARES targets 20+)" 'Install Node 20 or newer from https://nodejs.org' }
} else {
    Write-Check 'Node.js' 'MISSING' 'not on PATH' 'Install the Node.js LTS installer from https://nodejs.org, then reopen PowerShell.'
}

$npm = Get-CommandVersion 'npm'
if ($npm) { Write-Check 'npm' 'OK' $npm '' }
else { Write-Check 'npm' 'MISSING' 'not on PATH' 'npm ships with Node.js; reinstall Node and reopen PowerShell.' }

# Windows Python is usually reached through the py launcher.
$python = $null; $pythonCmd = $null
foreach ($candidate in @('py', 'python')) {
    $version = Get-CommandVersion $candidate '--version'
    if ($version -and $version -match 'Python\s+3') { $python = $version; $pythonCmd = $candidate; break }
}
if ($python) {
    $minor = [int](($python -replace '^Python\s+3\.','') -split '\.')[0]
    if ($minor -ge 10) { Write-Check 'Python' 'OK' "$python (via '$pythonCmd')" '' }
    else { Write-Check 'Python' 'WARN' $python 'ARES targets Python 3.10+; upgrade from https://python.org/downloads' }
} else {
    Write-Check 'Python' 'MISSING' 'not on PATH' 'Install Python 3.11+ from https://python.org/downloads and tick "Add python.exe to PATH".'
}

# ---- ARES environment ----------------------------------------------------------
Write-Section 'ARES environment'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    Write-Check 'Backend virtualenv' 'OK' $venvPython ''
    $installed = & $venvPython -c "import importlib.util as u; print(all(u.find_spec(m) for m in ('fastapi','uvicorn','sqlalchemy','httpx')))" 2>&1
    if ("$installed".Trim() -eq 'True') { Write-Check 'Backend packages' 'OK' 'fastapi, uvicorn, sqlalchemy, httpx present' '' }
    else { Write-Check 'Backend packages' 'MISSING' 'incomplete' "Run: $venvPython -m pip install -r backend\requirements.txt" }
} else {
    Write-Check 'Backend virtualenv' 'MISSING' 'backend\.venv\Scripts\python.exe not found' "Run: $pythonCmd -m venv backend\.venv   (Start-Ares.ps1 does this for you)"
}

if (Test-Path (Join-Path $frontend 'node_modules')) { Write-Check 'Frontend packages' 'OK' 'node_modules present' '' }
else { Write-Check 'Frontend packages' 'MISSING' 'node_modules absent' 'Run: npm install --prefix frontend' }

if (Test-Path (Join-Path $frontend 'dist\index.html')) { Write-Check 'Frontend build' 'OK' 'dist\index.html present' '' }
else { Write-Check 'Frontend build' 'WARN' 'not built yet' 'Run: npm run build --prefix frontend   (Start-Ares.ps1 does this for you)' }

$envFile = Join-Path $repo '.env'
if (Test-Path $envFile) { Write-Check 'Configuration (.env)' 'OK' $envFile '' }
else { Write-Check 'Configuration (.env)' 'WARN' 'not found' "Run: Copy-Item .env.example .env   then edit it (never commit it)." }

# ---- ports ---------------------------------------------------------------------
Write-Section 'Ports'
$listener = Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = (Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Write-Check "Port $BackendPort" 'WARN' "in use by $owner (PID $($listener.OwningProcess))" "Stop it, or start ARES on another port: .\scripts\Start-Ares.ps1 -Port 8010"
} else {
    Write-Check "Port $BackendPort" 'OK' 'available' ''
}

# ---- MetaTrader 5 -----------------------------------------------------------------
Write-Section 'MetaTrader 5'
$mt5Paths = @(
    "$env:ProgramFiles\MetaTrader 5\terminal64.exe",
    "${env:ProgramFiles(x86)}\MetaTrader 5\terminal.exe"
)
$mt5Paths += Get-ChildItem "$env:ProgramFiles" -Filter 'terminal64.exe' -Recurse -Depth 2 -ErrorAction SilentlyContinue |
             Select-Object -ExpandProperty FullName
$terminal = $mt5Paths | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($terminal) { Write-Check 'Terminal executable' 'OK' $terminal '' }
else { Write-Check 'Terminal executable' 'MISSING' 'terminal64.exe not found' 'Install MetaTrader 5 from your broker, or set MT5_PATH in .env.' }

$running = Get-Process -Name 'terminal64' -ErrorAction SilentlyContinue
if ($running) { Write-Check 'Terminal running' 'OK' "PID $($running[0].Id)" '' }
else { Write-Check 'Terminal running' 'WARN' 'not running' 'Start MetaTrader 5 and log into your DEMO account before running the bridge.' }

if ($venvPython -and (Test-Path $venvPython)) {
    $hasMt5 = & $venvPython -c "import importlib.util;print(importlib.util.find_spec('MetaTrader5') is not None)" 2>&1
    if ("$hasMt5".Trim() -eq 'True') { Write-Check 'MetaTrader5 package' 'OK' 'importable in the ARES venv' '' }
    else { Write-Check 'MetaTrader5 package' 'MISSING' 'not installed' "Run: $venvPython -m pip install MetaTrader5 websockets python-dotenv" }
}

# ---- verdict --------------------------------------------------------------------------
Write-Section 'Verdict'
if ($script:Failures -eq 0 -and $script:Warnings -eq 0) {
    Write-Host '  READY — every check passed. Start ARES with: .\scripts\Start-Ares.ps1' -ForegroundColor Green
} elseif ($script:Failures -eq 0) {
    Write-Host "  READY WITH WARNINGS — $($script:Warnings) item(s) to review above." -ForegroundColor Yellow
    Write-Host '  Start-Ares.ps1 can resolve the build/venv warnings automatically.' -ForegroundColor DarkGray
} else {
    Write-Host "  NOT READY — $($script:Failures) blocking item(s). Fix the MISSING rows above, then re-run." -ForegroundColor Red
}
Write-Host ''
exit ([int]($script:Failures -gt 0))
