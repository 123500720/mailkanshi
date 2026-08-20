$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $python) {
    & $python launcher.py
    exit $LASTEXITCODE
}
try {
    & py -3 launcher.py
    exit $LASTEXITCODE
} catch {
    try {
        & python launcher.py
        exit $LASTEXITCODE
    } catch {
        Add-Content -Path (Join-Path $PSScriptRoot 'launcher_error.log') -Value ($_ | Out-String)
        Write-Host "启动失败，详情见 launcher_error.log"
        Read-Host "按回车退出"
        exit 1
    }
}
