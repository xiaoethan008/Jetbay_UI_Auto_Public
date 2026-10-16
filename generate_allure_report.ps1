param(
    [string]$ResultsDir = ".\artifacts\reports\allure-results",
    [string]$ReportDir = ".\artifacts\reports\allure-report"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not [IO.Path]::IsPathRooted($ResultsDir)) {
    $ResultsDir = Join-Path $projectRoot $ResultsDir
}
if (-not [IO.Path]::IsPathRooted($ReportDir)) {
    $ReportDir = Join-Path $projectRoot $ReportDir
}
$ReportDir = [IO.Path]::GetFullPath($ReportDir)
$workspacePrefix = [IO.Path]::GetFullPath($projectRoot).TrimEnd('\') + '\'
if (-not $ReportDir.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Allure report output must stay inside the project workspace: $ReportDir"
}

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
