param(
    [string]$ResultsDir = ".\artifacts\reports\allure-results",
    [string]$ReportDir = ".\artifacts\reports\allure-report",
    [switch]$Headless
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$resultsPath = if ([IO.Path]::IsPathRooted($ResultsDir)) { $ResultsDir } else { Join-Path $projectRoot $ResultsDir }
$reportPath = if ([IO.Path]::IsPathRooted($ReportDir)) { $ReportDir } else { Join-Path $projectRoot $ReportDir }

# These directories are recursively cleaned below. Check their absolute paths first.
$workspacePrefix = [IO.Path]::GetFullPath($projectRoot).TrimEnd('\') + '\'
foreach ($outputPath in @($resultsPath, $reportPath)) {
    $resolvedOutputPath = [IO.Path]::GetFullPath($outputPath)
    if (-not $resolvedOutputPath.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Allure output must stay inside the project workspace: $resolvedOutputPath"
    }
}
$resultsHistoryPath = Join-Path $resultsPath "history"
$reportHistoryPath = Join-Path $reportPath "history"

function Get-PythonCommand {
    $venvPython = Join-Path $projectRoot ".\.venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @{
            FilePath = $venvPython
            Arguments = @()
            Display = $venvPython
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return @{
            FilePath = $pythonCmd.Source
            Arguments = @()
            Display = $pythonCmd.Source
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{
            FilePath = $pyLauncher.Source
            Arguments = @("-3")
            Display = "$($pyLauncher.Source) -3"
        }
    }

    throw "Python executable not found. Checked: $venvPython, python in PATH, and py launcher."
}

$pythonCommand = Get-PythonCommand
Write-Host "Using Python: $($pythonCommand.Display)" -ForegroundColor Cyan

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

& $pythonCommand.FilePath @($pythonCommand.Arguments + @("-m", "pytest", "-v", "-s", "--alluredir=$resultsPath"))
if ($LASTEXITCODE -ne 0) {
    throw "Pytest failed with exit code $LASTEXITCODE"
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $projectRoot "generate_allure_report.ps1") -ResultsDir $resultsPath -ReportDir $reportPath
if ($LASTEXITCODE -ne 0) {
    throw "Allure report generation failed with exit code $LASTEXITCODE"
}

Write-Host "Allure test run completed. Report: $reportPath" -ForegroundColor Green
