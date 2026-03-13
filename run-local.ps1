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

$backendJob = $null
$frontendJob = $null

try {
    # Start backend in background job
    $backendJob = Start-Job -Name "ai-presenter-backend" -ScriptBlock {
        param($dir, $venv)
        Set-Location $dir
        . (Join-Path $venv "Scripts\Activate.ps1")
        & python -m uvicorn app:app --reload --port 8000 --host 127.0.0.1 2>&1
    } -ArgumentList $BackendDir, $VenvDir

    Write-Ok "Backend starting on http://127.0.0.1:8000  (Swagger: http://127.0.0.1:8000/docs)"

    # Start frontend in background job
    $frontendJob = Start-Job -Name "ai-presenter-frontend" -ScriptBlock {
        param($dir)
        Set-Location $dir
        & npm run dev 2>&1
    } -ArgumentList $FrontendDir

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

    # Tail logs from both jobs
    while ($true) {
        # Backend output
        $backendOutput = Receive-Job -Job $backendJob -ErrorAction SilentlyContinue
        if ($backendOutput) {
            $backendOutput | ForEach-Object { Write-Host "[backend]  $_" -ForegroundColor DarkCyan }
        }

        # Frontend output
        $frontendOutput = Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue
        if ($frontendOutput) {
            $frontendOutput | ForEach-Object { Write-Host "[frontend] $_" -ForegroundColor DarkMagenta }
        }

        # Check if either job died
        if ($backendJob.State -eq "Failed") {
            Write-Err "Backend crashed. Check logs above."
            Receive-Job -Job $backendJob -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ -ForegroundColor Red }
            break
        }
        if ($frontendJob.State -eq "Failed") {
            Write-Err "Frontend crashed. Check logs above."
            Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ -ForegroundColor Red }
            break
        }

        Start-Sleep -Milliseconds 500
    }
}
finally {
    # Graceful cleanup on Ctrl+C or exit
    Write-Host ""
    Write-Step "Shutting down services"

    if ($backendJob) {
        Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
        Remove-Job -Job $backendJob -Force -ErrorAction SilentlyContinue
        Write-Ok "Backend stopped"
    }
    if ($frontendJob) {
        Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
        Remove-Job -Job $frontendJob -Force -ErrorAction SilentlyContinue
        Write-Ok "Frontend stopped"
    }

    Write-Host "Goodbye!" -ForegroundColor Cyan
}
