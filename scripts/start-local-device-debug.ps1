[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"
$androidRoot = Join-Path $repoRoot "android"
$backendPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$backendData = Join-Path $backendRoot "data"
$pidFile = Join-Path $backendData "local-device-debug.pid"
$healthUrl = "http://127.0.0.1:$Port/api/health"

function Find-Adb {
    $command = Get-Command adb -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
        (Join-Path $env:USERPROFILE "AppData\Local\Android\Sdk\platform-tools\adb.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    throw "ADB was not found. Install Android SDK Platform-Tools first."
}

function Test-BackendHealth {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        return $response.status -eq "ok" -and $response.code -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $androidRoot)) {
    throw "Android project was not found at $androidRoot"
}
if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend virtual environment is missing. Create backend/.venv and install backend/requirements.txt first."
}

$adb = Find-Adb
$deviceOutput = & $adb devices
if ($LASTEXITCODE -ne 0) {
    throw "ADB could not list connected devices."
}
$devices = @(
    $deviceOutput |
        Where-Object { $_ -match "^\S+\s+device$" } |
        ForEach-Object { ($_ -split "\s+")[0] }
)
if ($devices.Count -eq 0) {
    throw "No authorized Android device found. Connect the phone by USB and allow USB debugging."
}
if ($devices.Count -gt 1) {
    throw "More than one Android device is connected. Keep only the phone used for this debug session."
}
$serial = $devices[0]

& $adb -s $serial reverse "tcp:$Port" "tcp:$Port"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure adb reverse for device $serial."
}

if (-not (Test-BackendHealth)) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($null -ne $listener) {
        throw "Port $Port is already occupied by another local process, and it is not a healthy travel-app backend."
    }

    New-Item -ItemType Directory -Path $backendData -Force | Out-Null
    # PowerShell 5.1 Start-Process can fail when Conda exports both `Path` and
    # `PATH`. ShellExecute avoids rebuilding that case-insensitive dictionary.
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $backendPython
    $startInfo.Arguments = "-m uvicorn app.main:app --host 127.0.0.1 --port $Port"
    $startInfo.WorkingDirectory = $backendRoot
    $startInfo.UseShellExecute = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $process = [System.Diagnostics.Process]::Start($startInfo)
    if ($null -eq $process) {
        throw "Windows could not start the local backend process."
    }
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII

    $healthy = $false
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) {
            break
        }
        if (Test-BackendHealth) {
            $healthy = $true
            break
        }
    }
    if (-not $healthy) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
        throw "Backend failed to start. Run backend/.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port in a terminal to inspect the error."
    }
    Write-Host "Travel backend started (PID $($process.Id))." -ForegroundColor Green
} else {
    Write-Host "Travel backend was already healthy on port $Port." -ForegroundColor Green
}

Write-Host "ADB reverse configured for ${serial}: device 127.0.0.1:$Port -> computer 127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Health: $healthUrl"
Write-Host "Docs:   http://127.0.0.1:$Port/docs"
Write-Host "Review database: backend/data/reviews.sqlite3 (preserved)"
Write-Host "User database:   backend/data/users.sqlite3 (preserved or created automatically)"
Write-Host "Now run the app Debug configuration from Android Studio."
