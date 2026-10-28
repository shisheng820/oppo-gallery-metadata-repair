param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$Make,
    [string]$Model,
    [switch]$Apply,
    [switch]$VerifyPhone,
    [string]$DeviceHost,
    [int]$Port = 65000,
    [string]$Certificate,
    [string]$Serial
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'First create .venv and install requirements.txt as described in README.' }
if ($VerifyPhone -and (!$Apply -or !$DeviceHost -or !$Serial)) {
    throw '-VerifyPhone requires -Apply, -DeviceHost and -Serial.'
}
$repairArgs = @((Join-Path $PSScriptRoot 'repair.py'), $Source, '--output', $Output)
if ($Make) { $repairArgs += @('--make', $Make) }
if ($Model) { $repairArgs += @('--model', $Model) }
if ($Apply) { $repairArgs += '--apply' }
& $python @repairArgs
if ($LASTEXITCODE -ne 0) { throw 'Repair failed; phone verification was not started.' }
if ($VerifyPhone) {
    $report = Get-Content -Raw -Encoding UTF8 (Join-Path $Output 'report.json') | ConvertFrom-Json
    $verifyArgs = @((Join-Path $PSScriptRoot 'verify_gallery.py'), (Join-Path $Output 'repaired.jpg'),
        '--host', $DeviceHost, '--port', $Port, '--serial', $Serial,
        '--expected-model', $report.model, '--evidence', (Join-Path $Output 'device'))
    if ($Certificate) { $verifyArgs += @('--certificate', $Certificate) }
    & $python @verifyArgs
    if ($LASTEXITCODE -ne 0) { throw 'Phone verification failed; inspect private reports.' }
}
