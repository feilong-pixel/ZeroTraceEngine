Set-Location -Path $PSScriptRoot

~\.virtualenvs\venv\Scripts\python.exe -m pytest -q
exit $LASTEXITCODE
