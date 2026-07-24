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

# Keep this launcher ASCII-only so Windows PowerShell 5 does not corrupt UTF-8
# city arguments when the script has no byte-order mark.
$beijing = -join ([char[]](0x5317, 0x4EAC, 0x5E02))
$shanghai = -join ([char[]](0x4E0A, 0x6D77, 0x5E02))
$tianjin = -join ([char[]](0x5929, 0x6D25, 0x5E02))
$chongqing = -join ([char[]](0x91CD, 0x5E86, 0x5E02))
$citiesFile = Join-Path $backendRoot 'data\municipality-cities-utf8.txt'
[System.IO.File]::WriteAllLines(
    $citiesFile,
    @($beijing, $shanghai, $tianjin, $chongqing),
    [System.Text.UTF8Encoding]::new($false)
)

& ".\.venv\Scripts\python.exe" `
    "scripts\build_city_content.py" `
    "--cities-file" $citiesFile `
    "--top" "12" `
    "--candidate-limit" "20" `
    "--max-targets-per-city" "3" `
    "--max-active-cities" "1" `
    "--wait-for-quota-reset"

exit $LASTEXITCODE
