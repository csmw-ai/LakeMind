# LakeMind one-click deploy (Windows PowerShell)
param([string]$Action = "")

$ErrorActionPreference = "Continue"
$RepoDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoDir

function Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Green }

# 1. Prerequisites
Step "1/7 Prerequisites"
$dockerOk = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerOk) { Fail "Docker not installed. Install Docker Desktop first." }
$null = docker compose version 2>&1
if ($LASTEXITCODE -ne 0) { Fail "Docker Compose v2 not installed" }
Ok "Docker + Compose ready"

# 2. .env check
Step "2/7 Environment config"
if (-not (Test-Path .env)) {
    python scripts/init_env.py
    Fail "Edit .env to fill MAAS_API_KEY, then re-run this script"
}
$envContent = Get-Content .env -Raw
if ($envContent -match 'MAAS_API_KEY=<') { Fail "Please fill MAAS_API_KEY in .env" }
Ok ".env configured"

# 3. Model check
Step "3/7 Model check"
$asrModel = "LakeMindModelServing\data\asr-models\asr\sensevoice-small"
$embedCache = "LakeMindModelServing\data\fastembed_cache"
if ((Test-Path $asrModel) -and (Test-Path $embedCache)) {
    Ok "Models exist, skip download"
} else {
    if ($Action -eq "--skip-models") {
        Warn "Skip model download"
    } else {
        Warn "Models not found, downloading (~1GB, 5-10 min)..."
        pip install modelscope fastembed 2>$null
        if ($LASTEXITCODE -ne 0) { Fail "Cannot install modelscope/fastembed" }
        python scripts/download_models.py
        if ($LASTEXITCODE -ne 0) { Fail "Model download failed" }
        Ok "Models downloaded"
    }
}

# 4. Pull images
Step "4/7 Pull images (GHCR public, no login needed)"
docker compose --env-file .env pull 2>&1
if ($LASTEXITCODE -ne 0) { Warn "Some images failed to pull, trying anyway" }
docker compose --env-file .env -f examples/meeting-agent/docker-compose.yml pull 2>&1
if ($LASTEXITCODE -ne 0) { Warn "meeting-agent image failed to pull, trying anyway" }
Ok "Images ready"

# 5. Start
Step "5/7 Start LakeMind"
docker compose --env-file .env up -d --no-build
Ok "LakeMind containers started"

# 6. Start meeting-agent
Step "6/7 Start meeting-agent"
docker compose --env-file .env -f examples/meeting-agent/docker-compose.yml up -d --no-build 2>&1
Ok "meeting-agent started"

# 7. Wait for health
Step "7/7 Wait for health"
Write-Host "Waiting for all services (up to 180s)..."
$allHealthy = $false
for ($i = 1; $i -le 36; $i++) {
    $output = docker compose --env-file .env ps --format json 2>&1
    $unhealthy = @()
    foreach ($line in $output) {
        try {
            $c = $line | ConvertFrom-Json
            if ($c.State -eq "running" -and $c.Health -ne "healthy") { $unhealthy += $c.Name }
        } catch {}
    }
    if ($unhealthy.Count -eq 0) {
        Ok "All containers healthy"
        $allHealthy = $true
        break
    }
    Write-Host -NoNewline "`r  [$i/36] waiting: $($unhealthy -join ' ')"
    Start-Sleep -Seconds 5
}
if (-not $allHealthy) { Warn "Some containers not healthy after 180s" }

# Verify
Write-Host ""
try {
    $null = Invoke-RestMethod -Uri "http://localhost:10823/api/v1/system/health" -TimeoutSec 5
    Ok "Server API healthy"
} catch {
    Warn "Server API not ready"
}

Write-Host ""
Write-Host "===================================" -ForegroundColor Green
Write-Host "  LakeMind deployed!" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Green
Write-Host "  Meeting Agent:  http://localhost:9100"
Write-Host "  ControlCenter:  http://localhost:3000"
Write-Host "  Server API:     http://localhost:10823"
Write-Host "  ModelServing:   http://localhost:10824"
Write-Host "  AssetMCP:       http://localhost:8401"
Write-Host "  DataMCP:        http://localhost:8402"
Write-Host "  AdminMCP:       http://localhost:8403"
Write-Host "===================================" -ForegroundColor Green
Write-Host ""
Write-Host "Verify: .\scripts\healthcheck.ps1"
Write-Host "Stop:   docker compose --env-file .env down"
