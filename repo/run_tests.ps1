# ============================================================
# run_tests.ps1 — One-click test runner (Windows PowerShell)
# Run from the project root:  pwsh run_tests.ps1
#                         or: powershell -ExecutionPolicy Bypass -File run_tests.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO = $ROOT

function Write-Info  { param($msg) Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "[PASS]  $msg" -ForegroundColor Green }
function Write-Fail  { param($msg) Write-Host "[FAIL]  $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Acceptance Test Suite - Neighborhood Commerce System"  -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# --- Prerequisites ---
Write-Info "Checking Python..."
try { python --version | Out-Null } catch { Write-Fail "python not found - install Python 3.12+"; exit 1 }

Write-Info "Checking pytest..."
try { python -m pytest --version | Out-Null } catch { Write-Fail "pytest not found - run: pip install pytest"; exit 1 }

# --- Data directories and Fernet key ---
Write-Info "Ensuring data directories exist..."
New-Item -ItemType Directory -Force -Path (Join-Path $REPO "data\keys")        | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $REPO "data\logs")        | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $REPO "data\attachments") | Out-Null

$keyFile = Join-Path $REPO "data\keys\secret.key"
if (-not (Test-Path $keyFile)) {
    Write-Info "Generating Fernet encryption key..."
    python -c @"
from cryptography.fernet import Fernet
with open(r'$keyFile', 'wb') as f:
    f.write(Fernet.generate_key())
"@
    Write-Ok "Key written to $keyFile"
}

# --- Environment ---
$env:PYTHONPATH      = $REPO
$env:FERNET_KEY_PATH = $keyFile
$env:LOG_FILE        = Join-Path $REPO "data\logs\app.jsonl"
$env:ATTACHMENT_DIR  = Join-Path $REPO "data\attachments"

Set-Location $ROOT

# --- Run unit tests ---
Write-Host ""
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  PHASE 1 - Unit Tests  (unit_tests/)"                   -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan

$unitResult = 0
try {
    python -m pytest unit_tests/ -v --tb=short --no-header -q
} catch {
    $unitResult = $LASTEXITCODE
}
if ($LASTEXITCODE -ne 0) { $unitResult = $LASTEXITCODE }

# --- Run API functional tests ---
Write-Host ""
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  PHASE 2 - API Functional Tests  (API_tests/)"          -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan

$apiResult = 0
try {
    python -m pytest API_tests/ -v --tb=short --no-header -q
} catch {
    $apiResult = $LASTEXITCODE
}
if ($LASTEXITCODE -ne 0) { $apiResult = $LASTEXITCODE }

# --- Integration / job tests ---
Write-Host ""
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  PHASE 3 - Integration/Job Tests  (tests/)"             -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan

$jobsResult = 0
try {
    python -m pytest tests/ -v --tb=short --no-header -q
} catch {
    $jobsResult = $LASTEXITCODE
}
if ($LASTEXITCODE -ne 0) { $jobsResult = $LASTEXITCODE }

# --- Aggregate summary ---
Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  SUMMARY"                                                 -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
python -m pytest unit_tests/ API_tests/ tests/ --tb=no -q 2>&1 | Select-Object -Last 5 | Write-Host
$ErrorActionPreference = $oldEap

Write-Host ""
if ($unitResult -eq 0 -and $apiResult -eq 0 -and $jobsResult -eq 0) {
    Write-Ok "All tests passed."
    exit 0
} else {
    Write-Fail "One or more tests failed."
    if ($unitResult  -ne 0) { Write-Fail "  Unit tests:         FAILED (exit $unitResult)" }
    if ($apiResult   -ne 0) { Write-Fail "  API tests:          FAILED (exit $apiResult)" }
    if ($jobsResult  -ne 0) { Write-Fail "  Integration tests:  FAILED (exit $jobsResult)" }
    exit 1
}
