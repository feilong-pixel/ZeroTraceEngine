# Environment

This document records the expected local development environment for ZeroTrace Engine.

## Supported Platform

ZeroTrace Engine is developed primarily for Windows.

Core behavior is local-first and filesystem-oriented. Some features, especially registry inspection and system Recycle Bin behavior, are Windows-specific.

## Python Environment

Use the existing virtual environment. Do not create a new virtual environment unless there is an explicit reason.

Windows:

```powershell
~\.virtualenvs\venv\Scripts\python.exe
```

Linux/macOS, if used for non-Windows checks:

```bash
~/.virtualenvs/venv/bin/python
```

## Creating The Virtual Environment

Only use this step when `~\.virtualenvs\venv` does not exist yet.

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "$HOME\.virtualenvs"
python -m venv "$HOME\.virtualenvs\venv"
& "$HOME\.virtualenvs\venv\Scripts\python.exe" -m pip install --upgrade pip
& "$HOME\.virtualenvs\venv\Scripts\python.exe" -m pip install -r requirements.txt
& "$HOME\.virtualenvs\venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
```

After creation, confirm the environment:

```powershell
& "$HOME\.virtualenvs\venv\Scripts\python.exe" --version
```

Linux/macOS:

```bash
mkdir -p ~/.virtualenvs
python3 -m venv ~/.virtualenvs/venv
~/.virtualenvs/venv/bin/python -m pip install --upgrade pip
~/.virtualenvs/venv/bin/python -m pip install -r requirements.txt
~/.virtualenvs/venv/bin/python -m pip install -r requirements-dev.txt
```

## Dependencies

Runtime dependencies are listed in:

```text
requirements.txt
```

Development and test dependencies are listed in:

```text
requirements-dev.txt
```

Install or refresh dependencies with the existing virtual environment:

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m pip install -r requirements.txt
~\.virtualenvs\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Running The App

The standard local server is:

```powershell
.\start.ps1
```

Equivalent direct command:

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open the app at:

```text
http://127.0.0.1:8000
```

## Running Tests

Use the project test script:

```powershell
.\test.ps1
```

Equivalent direct command:

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m pytest -q
```

`pytest.ini` disables pytest's cache provider so test artifacts stay out of the normal project cache flow.

## Runtime Data

These directories are runtime state, not source code:

```text
data/
logs/
ZeroTraceRecycle/
ZeroTraceRegistryRecycle/
.test-tmp/
```

They may contain local scan results, audit logs, recycle records, registry backups, or isolated test data.

Do not treat runtime data as portable source files. Do not delete or rewrite these directories unless the task explicitly requires it and the safety impact is understood.

## Frontend Environment

The frontend is plain HTML, CSS, and JavaScript ES modules under:

```text
static/
```

There is no frontend build step and no frontend package manager requirement for normal development.

## Safety Notes

- Keep file and registry operations local.
- Do not bypass the service/orchestration layer for destructive operations.
- Prefer reversible flows through `ZeroTraceRecycle/` and registry backup files.
- Keep tests isolated from real user files and real system cleanup targets.
