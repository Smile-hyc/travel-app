param(
    [int]$WaitForProcessId = 0
)

$ErrorActionPreference = "Stop"
$backendRoot = Split-Path -Parent $PSScriptRoot

if ($WaitForProcessId -gt 0) {
    $existing = Get-Process -Id $WaitForProcessId -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        Wait-Process -Id $WaitForProcessId
    }
}

$env:PYTHONUTF8 = "1"
Set-Location -LiteralPath $backendRoot

& ".\.venv\Scripts\python.exe" `
    "scripts\build_city_content.py" `
    "--all-cities" `
    "--confirm-all" `
    "--wait-for-quota-reset"

exit $LASTEXITCODE
