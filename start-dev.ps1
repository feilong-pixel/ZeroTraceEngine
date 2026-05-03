Set-Location -Path $PSScriptRoot

~\.virtualenvs\venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
