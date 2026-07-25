[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot "backend\data\local-device-debug.pid"

$adbCommand = Get-Command adb -ErrorAction SilentlyContinue
if ($null -ne $adbCommand) {
    & $adbCommand.Source reverse --remove "tcp:$Port" 2>$null
}

if (Test-Path -LiteralPath $pidFile) {
    $processId = [int](Get-Content -LiteralPath $pidFile -Raw)
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        # Avoid a PowerShell 5.1 Stop-Process null-reference bug observed when
        # Conda exports duplicate case variants of environment keys.
        $process.Kill()
        $process.WaitForExit(5000) | Out-Null
        Write-Host "Stopped local travel backend PID $processId."
    }
    Remove-Item -LiteralPath $pidFile -Force
} else {
    Write-Host "No backend PID file was found; a manually started backend was left untouched."
}

Write-Host "Removed adb reverse for tcp:$Port."
