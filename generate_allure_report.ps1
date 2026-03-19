param(
    [string]$ResultsDir = ".\allure-results",
    [string]$ReportDir = ".\allure-report"
)

$ErrorActionPreference = "Stop"

$resultsPath = Resolve-Path $ResultsDir -ErrorAction SilentlyContinue
if (-not $resultsPath) {
    throw "Allure results directory not found: $ResultsDir"
}
$resultsPath = $resultsPath.Path

$reportHistoryPath = Join-Path $ReportDir "history"
$resultsHistoryPath = Join-Path $resultsPath "history"

# Copy previous history into current allure-results so Trend can accumulate across runs.
if (Test-Path $reportHistoryPath) {
    New-Item -ItemType Directory -Force -Path $resultsHistoryPath | Out-Null
    Copy-Item -Path (Join-Path $reportHistoryPath "*") -Destination $resultsHistoryPath -Recurse -Force
}

allure generate $resultsPath -o $ReportDir --clean

Write-Host "Allure report generated at $ReportDir" -ForegroundColor Green
