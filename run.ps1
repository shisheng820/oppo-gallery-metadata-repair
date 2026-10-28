param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$Profile,
    [string]$Make,
    [string]$Model,
    [string]$TakenAt,
    [string]$UtcOffset,
    [string]$Latitude,
    [string]$Longitude,
    [string]$Altitude,
    [string]$Iso,
    [string]$Aperture,
    [string]$Exposure,
    [string]$ExposureCompensation,
    [string]$FocalLength,
    [string]$FocalLength35mm,
    [string]$LensMake,
    [string]$LensModel,
    [switch]$Recursive,
    [switch]$FromFilenameTime,
    [switch]$OnlyMissing,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$repairArgs = @((Join-Path $PSScriptRoot 'repair.py'), $Source, '--output', $Output)
$fields = @{
    Profile='profile'; Make='make'; Model='model'; TakenAt='taken-at'; UtcOffset='utc-offset';
    Latitude='latitude'; Longitude='longitude'; Altitude='altitude'; Iso='iso';
    Aperture='aperture'; Exposure='exposure'; ExposureCompensation='ev'; FocalLength='focal-length';
    FocalLength35mm='focal-length-35mm'; LensMake='lens-make'; LensModel='lens-model'
}
foreach ($key in $fields.Keys) {
    if ($PSBoundParameters.ContainsKey($key)) {
        $repairArgs += ('--' + $fields[$key] + '=' + $PSBoundParameters[$key])
    }
}
if ($Recursive) { $repairArgs += '--recursive' }
if ($FromFilenameTime) { $repairArgs += '--from-filename-time' }
if ($OnlyMissing) { $repairArgs += '--only-missing' }
if ($Apply) { $repairArgs += '--apply' }
& $python @repairArgs
if ($LASTEXITCODE -ne 0) { throw 'Metadata operation failed. Inspect the output and report.json if created.' }
