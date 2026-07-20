$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectDir

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 scripts/setup_datawork.py @args
} else {
    & python scripts/setup_datawork.py @args
}
exit $LASTEXITCODE
