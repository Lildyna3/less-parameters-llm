#Requires -Version 5.1
<#
.SYNOPSIS
    Runs the ARES MT5 verification suite (TESTS 1-10) against the real terminal.

.DESCRIPTION
    A thin wrapper around bridge\verify_mt5.py that uses the ARES virtual
    environment, loads .env if present, and installs the MetaTrader5 package
    only if you ask it to.

    Start MetaTrader 5 and log into your DEMO account before running this.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Verify-MT5.ps1
.EXAMPLE
    .\scripts\Verify-MT5.ps1 -InstallMissing
#>
[CmdletBinding()]
param(
    [switch] $InstallMissing
)

$ErrorActionPreference = 'Stop'

$repo   = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $repo 'backend\.venv\Scripts\python.exe'
$script = Join-Path $repo 'bridge\verify_mt5.py'

if (-not (Test-Path $venvPy)) {
    Write-Host ''
    Write-Host 'ARES VIRTUAL ENVIRONMENT' -ForegroundColor White
    Write-Host 'MISSING' -ForegroundColor Red
    Write-Host ''
    Write-Host 'Error:';        Write-Host "  $venvPy not found" -ForegroundColor Yellow
    Write-Host 'Likely cause:'; Write-Host '  ARES has not been started on this machine yet.'
    Write-Host 'Action:';       Write-Host '  Run .\scripts\Start-Ares.ps1 first (it creates the environment).' -ForegroundColor Green
    Write-Host ''
    exit 1
}

if (-not (Test-Path $script)) {
    Write-Host "bridge\verify_mt5.py not found under $repo — the clone is incomplete." -ForegroundColor Red
    exit 1
}

# Load .env so MT5_LOGIN / MT5_PASSWORD / MT5_SERVER reach the verifier.
# Values stay in this process; nothing is printed.
$envFile = Join-Path $repo '.env'
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
            $name, $value = $line.Split('=', 2)
            [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), 'Process')
        }
    }
    Write-Host "[ares] loaded configuration from $envFile" -ForegroundColor DarkGray
}

$hasMt5 = & $venvPy -c "import importlib.util;print(importlib.util.find_spec('MetaTrader5') is not None)" 2>&1
if ("$hasMt5".Trim() -ne 'True') {
    if ($InstallMissing) {
        Write-Host '[ares] installing MetaTrader5, websockets, python-dotenv…' -ForegroundColor Cyan
        & $venvPy -m pip install --disable-pip-version-check -q MetaTrader5 websockets python-dotenv
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'pip install failed — run it manually to see the full error.' -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host ''
        Write-Host 'METATRADER5 PACKAGE' -ForegroundColor White
        Write-Host 'MISSING' -ForegroundColor Red
        Write-Host ''
        Write-Host 'Error:';        Write-Host '  The MetaTrader5 package is not installed in the ARES environment.' -ForegroundColor Yellow
        Write-Host 'Likely cause:'; Write-Host '  It is a Windows-only wheel and is not part of requirements.txt.'
        Write-Host 'Action:';       Write-Host '  Re-run with -InstallMissing, or install it yourself:' -ForegroundColor Green
        Write-Host "    $venvPy -m pip install MetaTrader5 websockets python-dotenv" -ForegroundColor Green
        Write-Host ''
        exit 1
    }
}

& $venvPy $script
exit $LASTEXITCODE
