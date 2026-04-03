<#
.SYNOPSIS
    Starts the full AI Presenter application locally (backend + frontend).

.DESCRIPTION
    - Checks prerequisites (Python, Node.js, Azure CLI login)
    - Activates/creates the backend Python venv and installs dependencies
    - Installs frontend npm packages
    - Launches the FastAPI backend on port 8000
    - Launches the Vite dev server on port 5173
    - Opens the browser at http://localhost:5173
    - Ctrl+C gracefully stops both services

.EXAMPLE
    .\run-local.ps1              # normal start
    .\run-local.ps1 -SkipInstall # skip dependency installation
#>

param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$BackendDir  = Join-Path $ProjectRoot "demos\backend"
$FrontendDir = Join-Path $ProjectRoot "demos\frontend"
$VenvDir     = Join-Path $BackendDir ".venv"

# ── Colours ──────────────────────────────────────────────────────────────────
function Write-Step  { param($msg) Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "   OK  $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "   WARN  $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "   ERROR  $msg" -ForegroundColor Red }

# ── Prerequisite checks ─────────────────────────────────────────────────────
Write-Step "Checking prerequisites"

# Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Write-Err "Python not found. Install Python 3.12+ and add it to PATH."; exit 1 }
$pyVer = & python --version 2>&1
Write-Ok "Python: $pyVer"

# Node / npm
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { Write-Err "Node.js not found. Install Node.js 18+ and add it to PATH."; exit 1 }
$nodeVer = & node --version 2>&1
Write-Ok "Node.js: $nodeVer"

# Azure CLI login
try {
    $acct = az account show 2>&1 | ConvertFrom-Json -ErrorAction Stop
    Write-Ok "Azure CLI: logged in as $($acct.user.name)"
} catch {
    Write-Warn "Azure CLI not logged in. Avatar/AI features need 'az login'. Continuing anyway..."
}

# Backend .env
$envFile = Join-Path $BackendDir ".env"
if (-not (Test-Path $envFile)) {
    Write-Warn "No .env file found at $envFile. Backend may fail without Azure credentials."
}

# LibreOffice (optional — for real slide image rendering)
$soffice = Get-Command soffice -ErrorAction SilentlyContinue
if ($soffice) {
    Write-Ok "LibreOffice: found — slides will render as actual images"
} else {
    Write-Warn "LibreOffice not found — slides will use placeholder images. Install LibreOffice for full rendering."
}

# ── Backend setup ────────────────────────────────────────────────────────────
Write-Step "Setting up backend (FastAPI)"

if (-not (Test-Path $VenvDir)) {
    Write-Host "   Creating virtual environment..."
    & python -m venv $VenvDir
}

# Activate venv for current process
$activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
. $activateScript
Write-Ok "Virtual environment activated"

if (-not $SkipInstall) {
    Write-Host "   Installing Python dependencies..."
    & pip install --quiet -r (Join-Path $BackendDir "requirements.txt")
    # Extra packages needed for Voice Live proxy (pure-Python, no C compiler)
    & pip install --quiet websockets aiohttp --only-binary=:all: 2>$null
    Write-Ok "Python dependencies installed"
}

# ── Frontend setup ───────────────────────────────────────────────────────────
Write-Step "Setting up frontend (React + Vite)"

if (-not $SkipInstall) {
    Write-Host "   Installing npm packages..."
    Push-Location $FrontendDir
    & npm install --silent 2>$null
    Pop-Location
    Write-Ok "npm packages installed"
}

# ── Launch services ──────────────────────────────────────────────────────────
Write-Step "Starting services"

$backendProc = $null
$frontendProc = $null
$venvPython = Join-Path $VenvDir "Scripts\python.exe"

try {
    # Start backend as a separate process (avoids Start-Job Anaconda/path conflicts)
    $backendProc = Start-Process -FilePath $venvPython `
        -ArgumentList "-m", "uvicorn", "app:app", "--reload", "--reload-exclude", ".venv", "--port", "8000", "--host", "127.0.0.1" `
        -WorkingDirectory $BackendDir `
        -PassThru -NoNewWindow

    Write-Ok "Backend starting on http://127.0.0.1:8000  (Swagger: http://127.0.0.1:8000/docs)"

    # Start frontend as a separate process (npx is a batch script, so launch via cmd)
    $frontendProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npx vite" `
        -WorkingDirectory $FrontendDir `
        -PassThru -NoNewWindow

    Write-Ok "Frontend starting on http://localhost:5173"

    # Wait a moment for servers to boot, then open browser
    Start-Sleep -Seconds 4
    Write-Step "Opening browser"
    Start-Process "http://localhost:5173"

    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Green
    Write-Host "  AI Presenter is running locally!" -ForegroundColor Green
    Write-Host "  Frontend : http://localhost:5173" -ForegroundColor Green
    Write-Host "  Backend  : http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "  Swagger  : http://127.0.0.1:8000/docs" -ForegroundColor Green
    Write-Host "=============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Press Ctrl+C to stop both services." -ForegroundColor Yellow
    Write-Host ""

    # Wait for either process to exit
    while ($true) {
        if ($backendProc.HasExited) {
            Write-Err "Backend exited with code $($backendProc.ExitCode)."
            break
        }
        if ($frontendProc.HasExited) {
            Write-Err "Frontend exited with code $($frontendProc.ExitCode)."
            break
        }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    # Graceful cleanup on Ctrl+C or exit
    Write-Host ""
    Write-Step "Shutting down services"

    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
        Write-Ok "Backend stopped"
    }
    if ($frontendProc -and -not $frontendProc.HasExited) {
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
        Write-Ok "Frontend stopped"
    }

    Write-Host "Goodbye!" -ForegroundColor Cyan
}
