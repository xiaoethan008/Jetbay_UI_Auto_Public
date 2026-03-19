# PowerShell script to download necessary wheel files for offline installation
# Usage: run this on a machine with internet access, then copy the generated
# directory to the target machine that cannot reach PyPI.

param(
    [string]$OutputDir = "C:\jetbay_wheels"  # change as needed
)

if (-Not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

Write-Host "Downloading wheels to $OutputDir ..." -ForegroundColor Green

# Packages required by the project
$packages = @(
    'pytest',
    'playwright',
    'pytest-playwright'
)

# run pip download for each package
foreach ($pkg in $packages) {
    Write-Host "Downloading $pkg" -ForegroundColor Cyan
    py -3.10 -m pip download --dest $OutputDir $pkg
}

Write-Host "Download complete. Copy the directory to the offline machine and
use pip install --no-index --find-links <path> -r requirements.txt" -ForegroundColor Green
