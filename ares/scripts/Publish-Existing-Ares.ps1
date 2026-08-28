#Requires -Version 5.1
<#
.SYNOPSIS
    Prepares the existing AI-TRADING-ASSISTANT project on this Windows machine
    to be pushed to GitHub, so a remote Claude Code session can audit it.

.DESCRIPTION
    A Claude Code session running in the cloud cannot see C:\ on this laptop.
    The only way it can audit an existing local project is if that project is
    in a Git repository it can be given access to.

    This script does the local half of that, carefully:

      * verifies the project really is the one intended (src\, ares-frontend\,
        ARES_ROADMAP.md, venv\)
      * writes a .gitignore that excludes venv\, node_modules\, build output,
        caches and every .env file
      * refuses to continue if anything that looks like a secret would be
        committed — .env, *.key, *.pem, credential and secret files
      * makes the first commit
      * prints an inventory so the audit can be sized

    It does NOT create a GitHub repository and does NOT push unless you pass
    -RemoteUrl explicitly. Nothing leaves this machine until you say so.

    It never prints the contents of any file, so no secret can end up in a
    console transcript or a screenshot.

.PARAMETER ProjectPath
    The existing ARES project. Defaults to the Desktop location.

.PARAMETER RemoteUrl
    Optional. If given, adds this as 'origin' and pushes. Create the repository
    on github.com FIRST, and create it PRIVATE.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Publish-Existing-Ares.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\Publish-Existing-Ares.ps1 `
        -RemoteUrl https://github.com/Lildyna3/ai-trading-assistant.git
#>
[CmdletBinding()]
param(
    [string] $ProjectPath = 'C:\Users\User\Desktop\AI-TRADING-ASSISTANT',
    [string] $RemoteUrl = ''
)

# Native git writes progress to stderr; with 'Stop' some hosts turn that into a
# terminating error. Exit codes are checked explicitly instead.
$ErrorActionPreference = 'Continue'

function Write-Section([string] $Title) {
    Write-Host ''
    Write-Host $Title.ToUpper() -ForegroundColor Cyan
    Write-Host ('-' * $Title.Length) -ForegroundColor DarkGray
}

function Write-Line([string] $Name, [string] $State, [string] $Detail) {
    $colour = 'Gray'
    if ($State -eq 'OK')      { $colour = 'Green' }
    if ($State -eq 'WARN')    { $colour = 'Yellow' }
    if ($State -eq 'MISSING') { $colour = 'Red' }
    if ($State -eq 'BLOCKED') { $colour = 'Red' }
    Write-Host ('  {0,-24}' -f $Name) -NoNewline
    Write-Host ('{0,-9}' -f $State) -ForegroundColor $colour -NoNewline
    Write-Host $Detail -ForegroundColor DarkGray
}

# ---- 1. verify the target ------------------------------------------------------

Write-Section 'Target project'

if (-not (Test-Path -LiteralPath $ProjectPath)) {
    Write-Line 'Project path' 'MISSING' $ProjectPath
    Write-Host ''
    Write-Host 'That folder does not exist on this machine.' -ForegroundColor Red
    Write-Host 'Re-run with the real path, for example:' -ForegroundColor Yellow
    Write-Host '  -ProjectPath "C:\Users\User\Desktop\AI-TRADING-ASSISTANT"' -ForegroundColor Yellow
    exit 1
}
Write-Line 'Project path' 'OK' $ProjectPath

$expected = @(
    @{ Name = 'src\';            Path = 'src' },
    @{ Name = 'ares-frontend\';  Path = 'ares-frontend' },
    @{ Name = 'ARES_ROADMAP.md'; Path = 'ARES_ROADMAP.md' },
    @{ Name = 'venv\';           Path = 'venv' }
)
$found = 0
foreach ($item in $expected) {
    $full = Join-Path $ProjectPath $item.Path
    if (Test-Path -LiteralPath $full) {
        Write-Line $item.Name 'OK' 'present'
        $found++
    } else {
        Write-Line $item.Name 'WARN' 'not found'
    }
}
if ($found -lt 2) {
    Write-Host ''
    Write-Host 'This does not look like the ARES project described.' -ForegroundColor Red
    Write-Host 'Nothing was changed. Check the path and try again.' -ForegroundColor Yellow
    exit 1
}

# ---- 2. .gitignore -------------------------------------------------------------
# Written before `git add`, so the excluded paths are never staged even once.

Write-Section 'Protecting secrets and build output'

$ignorePath = Join-Path $ProjectPath '.gitignore'
$rules = @(
    '# Written by Publish-Existing-Ares.ps1 — do not commit secrets or build output.',
    '',
    '# Secrets. Never commit these.',
    '.env',
    '.env.*',
    '!.env.example',
    '*.key',
    '*.pem',
    '*.pfx',
    'credentials*',
    'secrets*',
    '',
    '# Python',
    'venv/',
    '.venv/',
    '__pycache__/',
    '*.py[cod]',
    '*.egg-info/',
    '.pytest_cache/',
    '',
    '# Node / frontend',
    'node_modules/',
    'dist/',
    'build/',
    '.vite/',
    '',
    '# Local state and logs',
    '*.log',
    'logs/',
    '*.db',
    '*.sqlite',
    '*.sqlite3',
    '',
    '# Editors / OS',
    '.vscode/',
    '.idea/',
    'Thumbs.db',
    'desktop.ini'
)

$existing = @()
if (Test-Path -LiteralPath $ignorePath) {
    $existing = @(Get-Content -LiteralPath $ignorePath)
    Write-Line '.gitignore' 'OK' ('existed with ' + $existing.Count + ' lines — merging')
} else {
    Write-Line '.gitignore' 'OK' 'creating'
}

# Merge rather than overwrite: keep whatever the project already ignored.
$merged = New-Object System.Collections.Generic.List[string]
foreach ($line in $existing) { $merged.Add($line) }
$added = 0
foreach ($rule in $rules) {
    if ($rule -eq '' -or $rule.StartsWith('#')) { continue }
    if ($existing -notcontains $rule) {
        $merged.Add($rule)
        $added++
    }
}
if ($added -gt 0) {
    if ($existing.Count -gt 0) { $merged.Insert($existing.Count, '') }
    # ASCII, no BOM — a BOM in .gitignore makes Git ignore the first rule.
    [System.IO.File]::WriteAllLines($ignorePath, $merged, (New-Object System.Text.UTF8Encoding($false)))
}
Write-Line 'ignore rules added' 'OK' ([string]$added + ' new')

# ---- 3. git init ---------------------------------------------------------------

Write-Section 'Repository'

$git = Get-Command git -ErrorAction SilentlyContinue
if ($null -eq $git) {
    Write-Line 'git' 'MISSING' 'install Git for Windows: https://git-scm.com/download/win'
    exit 1
}
Write-Line 'git' 'OK' (& git --version)

Push-Location -LiteralPath $ProjectPath
try {
    if (Test-Path -LiteralPath (Join-Path $ProjectPath '.git')) {
        Write-Line 'repository' 'OK' 'already initialised'
    } else {
        & git init --initial-branch=main | Out-Null
        if ($LASTEXITCODE -ne 0) {
            # Older Git has no --initial-branch.
            & git init | Out-Null
            & git checkout -b main 2>$null | Out-Null
        }
        Write-Line 'repository' 'OK' 'initialised on branch main'
    }

    & git add -A
    if ($LASTEXITCODE -ne 0) {
        Write-Line 'git add' 'MISSING' 'failed — see the git output above'
        Pop-Location
        exit 1
    }

    # ---- 4. secret gate -------------------------------------------------------
    # Names only, never contents. If anything sensitive is staged, unstage
    # everything and stop: an accidental push cannot be taken back.

    Write-Section 'Secret gate'

    $staged = @(& git diff --cached --name-only)
    $suspects = @()
    foreach ($path in $staged) {
        $leaf = Split-Path $path -Leaf
        $isSecret = $false
        if ($leaf -eq '.env') { $isSecret = $true }
        if ($leaf -like '.env.*' -and $leaf -ne '.env.example') { $isSecret = $true }
        if ($leaf -like '*.key' -or $leaf -like '*.pem' -or $leaf -like '*.pfx') { $isSecret = $true }
        if ($leaf -like 'credentials*' -or $leaf -like 'secrets*') { $isSecret = $true }
        if ($isSecret) { $suspects += $path }
    }

    if ($suspects.Count -gt 0) {
        & git reset | Out-Null
        Write-Line 'staged secrets' 'BLOCKED' ([string]$suspects.Count + ' file(s)')
        Write-Host ''
        Write-Host 'These would have been committed:' -ForegroundColor Red
        foreach ($path in $suspects) { Write-Host ('  ' + $path) -ForegroundColor Red }
        Write-Host ''
        Write-Host 'Nothing was committed and everything was unstaged.' -ForegroundColor Yellow
        Write-Host 'Move those files out of the project (or add them to .gitignore),' -ForegroundColor Yellow
        Write-Host 'then run this script again.' -ForegroundColor Yellow
        exit 1
    }
    Write-Line 'staged secrets' 'OK' 'none'

    $venvStaged = @($staged | Where-Object { $_ -like 'venv/*' -or $_ -like 'node_modules/*' })
    if ($venvStaged.Count -gt 0) {
        & git reset | Out-Null
        Write-Line 'venv/node_modules' 'BLOCKED' ([string]$venvStaged.Count + ' file(s) staged')
        Write-Host ''
        Write-Host 'The .gitignore did not take effect — these are probably already tracked.' -ForegroundColor Yellow
        Write-Host 'Run, then re-run this script:' -ForegroundColor Yellow
        Write-Host '  git rm -r --cached venv node_modules' -ForegroundColor Yellow
        exit 1
    }
    Write-Line 'venv/node_modules' 'OK' 'excluded'

    # ---- 5. commit ------------------------------------------------------------

    Write-Section 'Commit'

    $tracked = @(& git diff --cached --name-only)
    if ($tracked.Count -eq 0) {
        Write-Line 'commit' 'OK' 'nothing new to commit'
    } else {
        & git commit -q -m "Existing ARES project, for audit" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Line 'commit' 'WARN' 'git needs your identity'
            Write-Host ''
            Write-Host 'Run these two commands, then re-run this script:' -ForegroundColor Yellow
            Write-Host '  git config --global user.name "Your Name"' -ForegroundColor Yellow
            Write-Host '  git config --global user.email "you@example.com"' -ForegroundColor Yellow
            exit 1
        }
        Write-Line 'commit' 'OK' ([string]$tracked.Count + ' files committed')
    }

    # ---- 6. inventory ---------------------------------------------------------

    Write-Section 'Inventory (what the audit will cover)'

    $all = @(& git ls-files)
    $py  = @($all | Where-Object { $_ -like '*.py' })
    $js  = @($all | Where-Object { $_ -like '*.js' -or $_ -like '*.jsx' -or $_ -like '*.ts' -or $_ -like '*.tsx' })
    Write-Line 'tracked files' 'OK' ([string]$all.Count)
    Write-Line 'python files'  'OK' ([string]$py.Count)
    Write-Line 'frontend files' 'OK' ([string]$js.Count)

    # ---- 7. push --------------------------------------------------------------

    Write-Section 'Push'

    if ($RemoteUrl -eq '') {
        Write-Line 'remote' 'WARN' 'not provided — nothing was pushed'
        Write-Host ''
        Write-Host 'Next steps:' -ForegroundColor Cyan
        Write-Host '  1. Go to https://github.com/new' -ForegroundColor Gray
        Write-Host '  2. Name it  ai-trading-assistant' -ForegroundColor Gray
        Write-Host '  3. Choose PRIVATE. Do not add a README or .gitignore.' -ForegroundColor Gray
        Write-Host '  4. Re-run this script with the URL it shows you:' -ForegroundColor Gray
        Write-Host '     powershell -ExecutionPolicy Bypass -File .\scripts\Publish-Existing-Ares.ps1 `' -ForegroundColor Gray
        Write-Host '        -RemoteUrl https://github.com/<you>/ai-trading-assistant.git' -ForegroundColor Gray
    } else {
        $current = & git remote get-url origin 2>$null
        if ($LASTEXITCODE -eq 0 -and $current) {
            & git remote set-url origin $RemoteUrl
        } else {
            & git remote add origin $RemoteUrl
        }
        Write-Line 'remote' 'OK' $RemoteUrl
        & git push -u origin main
        if ($LASTEXITCODE -ne 0) {
            Write-Line 'push' 'MISSING' 'push failed — see the git output above'
            exit 1
        }
        Write-Line 'push' 'OK' 'pushed to origin/main'
        Write-Host ''
        Write-Host 'Now tell your Claude Code session the repository name, and it can' -ForegroundColor Green
        Write-Host 'attach the project and start the audit.' -ForegroundColor Green
    }
}
finally {
    Pop-Location
}

Write-Host ''
