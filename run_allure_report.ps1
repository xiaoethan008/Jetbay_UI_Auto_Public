param(
    [string]$ResultsDir = ".\allure-results",
    [string]$ReportDir = ".\allure-report",
    [switch]$Headless
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$resultsPath = Join-Path $projectRoot $ResultsDir
$reportPath = Join-Path $projectRoot $ReportDir
$resultsHistoryPath = Join-Path $resultsPath "history"
$reportHistoryPath = Join-Path $reportPath "history"
$pythonExe = Join-Path $projectRoot ".\.venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

New-Item -ItemType Directory -Force -Path $resultsPath | Out-Null

# Clear current raw results first so the same test does not accumulate multiple entries.
Get-ChildItem -Path $resultsPath -Force | Where-Object { $_.Name -ne "history" } | Remove-Item -Recurse -Force

# Restore the previous report history so Trend can continue across runs.
if (Test-Path $reportHistoryPath) {
    New-Item -ItemType Directory -Force -Path $resultsHistoryPath | Out-Null
    Get-ChildItem -Path $resultsHistoryPath -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    Copy-Item -Path (Join-Path $reportHistoryPath "*") -Destination $resultsHistoryPath -Recurse -Force
}

if ($Headless.IsPresent) {
    $env:HEADLESS = "true"
}

& $pythonExe -m pytest -v -s --alluredir=$resultsPath
if ($LASTEXITCODE -ne 0) {
    throw "Pytest failed with exit code $LASTEXITCODE"
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "generate_allure_report.ps1") -ResultsDir $resultsPath -ReportDir $reportPath
if ($LASTEXITCODE -ne 0) {
    throw "Allure report generation failed with exit code $LASTEXITCODE"
}

Write-Host "Allure test run completed. Report: $reportPath" -ForegroundColor Green
