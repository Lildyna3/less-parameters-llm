# Auditing the existing project on your laptop

## The problem, stated plainly

The ARES 2.0 brief names one authorized target:

```
C:\Users\User\Desktop\AI-TRADING-ASSISTANT
```

That folder is on your Windows Surface. This Claude Code session runs in an
ephemeral Linux container in the cloud. It has no drive mapping to your laptop,
no `/mnt/c`, and no remote-access agent. The path was checked, along with a
filesystem-wide search for `AI-TRADING-ASSISTANT`, `ares-frontend` and
`ARES_ROADMAP.md`: the only match anywhere is this repository's own roadmap.

So the audit the brief asks for cannot be performed from here as written. Not
"is difficult" — the files are not reachable. Everything downstream of the
audit (fix trade execution, verify Dynamic Confidence, fix
`AIAnalysisPage.jsx`, repair `get_strategy_stats()`, remove
`src\scanner.py.tmp`, rewrite `ARES_ROADMAP.md`) depends on reading those
files.

Two routes make it possible. They are not equivalent.

## Route A — run Claude Code on the Surface itself

Best fit for this brief. The session then sits *in* the project, with the real
`venv`, the real MT5 terminal, and the real `.env`. It is also the only way to
satisfy §9 (controlled demo execution test) and §77 steps 19–25, because a
real MT5 fill requires the terminal that only that machine has.

Install the native Windows build — not the npm package, which is what produced
`claude.exe … not a valid application for this OS platform` last time:

```powershell
irm https://claude.ai/install.ps1 | iex
```

If that fails, WinGet installs the same binary:

```powershell
winget install Anthropic.ClaudeCode
```

Confirm it landed, then start it in the project:

```powershell
claude --version
cd C:\Users\User\Desktop\AI-TRADING-ASSISTANT
claude
```

`claude --version` should print something like `2.1.211 (Claude Code)`. If it
says `command not found`, open a new PowerShell window first — the installer
adds to PATH and the old window has the old PATH.

Paste the ARES 2.0 brief there. Nothing needs to be pushed anywhere, and the
`.env` never leaves the machine.

## Route B — put the project on GitHub so this session can read it

Use this if Route A will not install. It gets the audit, the roadmap
reconciliation, the code fixes and the UI work done from here — but a real MT5
fill still has to be verified on the Surface afterwards, because MT5 is not
reachable from a Linux container either.

```powershell
cd C:\Users\User\Documents\ares-repo
git pull
powershell -ExecutionPolicy Bypass -File .\ares\scripts\Publish-Existing-Ares.ps1
```

That first run changes nothing outside the project and pushes nothing. It
verifies the folder, merges a `.gitignore` that excludes `venv\`,
`node_modules\`, build output and every `.env`, stages, and then **refuses to
commit** if anything matching `.env`, `*.key`, `*.pem`, `credentials*` or
`secrets*` was staged. It prints file names only, never file contents, so
nothing sensitive can end up in a screenshot.

If it reports OK, create the repository at <https://github.com/new> — name it
`ai-trading-assistant`, choose **Private**, add no README and no `.gitignore` —
then re-run with the URL it gives you:

```powershell
powershell -ExecutionPolicy Bypass -File .\ares\scripts\Publish-Existing-Ares.ps1 `
    -RemoteUrl https://github.com/<your-account>/ai-trading-assistant.git
```

Tell the session the repository name afterwards and the project can be
attached and audited.

## What will not be done either way

- Your `.env` will not be requested, read aloud, pushed, or pasted into a
  chat. If a credential is missing, you will be told to set it locally.
- No live-money execution path will be added. Demo only.
- No status will be marked DONE on the strength of a file existing.

## The other ARES

This repository contains a separate, working ARES built here over previous
sessions, under `ares/`. It is not the project the ARES 2.0 brief targets, and
it has not been merged into it, copied over it, or used to overwrite anything.
Its own audit is in `docs/ARES_ROADMAP.md`.
