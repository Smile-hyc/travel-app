param(
    [int]$WaitForProcessId = 0
)

Write-Warning "全国采集已停用；此兼容入口仅处理北京、上海、天津、重庆。请改用 run_municipality_content.ps1。"
& (Join-Path $PSScriptRoot "run_municipality_content.ps1") -WaitForProcessId $WaitForProcessId
exit $LASTEXITCODE
