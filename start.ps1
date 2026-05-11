$ErrorActionPreference = "Stop"

Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path)

$python = Join-Path $HOME ".virtualenvs\venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "ERROR: venv python not found: $python"
    exit 1
}

if (-not (Test-Path ".\app.py")) {
    Write-Host "ERROR: app.py not found in current directory:"
    Get-Location
    exit 1
}

& $python -m uvicorn app:app --host 127.0.0.1 --port 8000

exit $LASTEXITCODE
