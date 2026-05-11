Set-Location -Path $PSScriptRoot

& (Join-Path $HOME ".virtualenvs\venv\Scripts\python.exe") -m pytest -q
exit $LASTEXITCODE
