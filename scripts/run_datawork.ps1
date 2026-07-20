$ErrorActionPreference = "Stop"
$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectDir

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    & $VenvPython -m datawork.web @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m datawork.web @args
} else {
    & python -m datawork.web @args
}
exit $LASTEXITCODE
