# LakeMind 一键部署脚本 (Windows PowerShell)
param([string]$Action = "")

$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoDir

function Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Green }

# 1. 前置检查
Step "1/6 前置检查"
$dockerOk = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerOk) { Fail "Docker 未安装。请先安装 Docker Desktop: https://docs.docker.com/desktop/" }
$null = docker compose version 2>&1
if ($LASTEXITCODE -ne 0) { Fail "Docker Compose v2 未安装" }
Ok "Docker + Compose 已就绪"

# 2. .env 检查
Step "2/6 环境配置"
if (-not (Test-Path .env)) {
    python scripts/init_env.py
    Fail "请编辑 .env 填入 MAAS_API_KEY 后重新运行本脚本"
}
$envContent = Get-Content .env -Raw
if ($envContent -match 'MAAS_API_KEY=<') { Fail "请在 .env 中填入 MAAS_API_KEY" }
Ok ".env 已配置"

# 3. 模型检查
Step "3/6 模型检查"
$asrModel = "LakeMindModelServing\data\asr-models\asr\sensevoice-small"
$embedCache = "LakeMindModelServing\data\fastembed_cache"
if ((Test-Path $asrModel) -and (Test-Path $embedCache)) {
    Ok "模型已存在，跳过下载"
} else {
    if ($Action -eq "--skip-models") {
        Warn "跳过模型下载"
    } else {
        Warn "模型未找到，需要下载（约 1GB，首次约 5-10 分钟）"
        pip install modelscope fastembed 2>$null
        if ($LASTEXITCODE -ne 0) { Fail "无法安装 modelscope/fastembed" }
        python scripts/download_models.py
        if ($LASTEXITCODE -ne 0) { Fail "模型下载失败" }
        Ok "模型下载完成"
    }
}

# 4. 拉取镜像
Step "4/6 拉取镜像（GHCR 公开镜像，无需登录）"
docker compose --env-file .env pull 2>&1
if ($LASTEXITCODE -ne 0) { Warn "部分镜像拉取失败，尝试继续" }
Ok "镜像就绪"

# 5. 启动
Step "5/6 启动 LakeMind"
docker compose --env-file .env up -d --no-build
Ok "容器已启动"

# 6. 等待健康
Step "6/6 等待健康检查"
Write-Host "等待所有服务就绪（最多 180 秒）..."
$allHealthy = $false
for ($i = 1; $i -le 36; $i++) {
    $output = docker compose --env-file .env ps --format json 2>&1
    $unhealthy = $output | ForEach-Object {
        try {
            $c = $_ | ConvertFrom-Json
            if ($c.State -eq "running" -and $c.Health -ne "healthy") { $c.Name }
        } catch {}
    }
    $unhealthy = $unhealthy | Where-Object { $_ }
    if (-not $unhealthy) {
        Ok "所有容器健康"
        $allHealthy = $true
        break
    }
    Write-Host -NoNewline "`r  [$i/36] 等待: $($unhealthy -join ' ')"
    Start-Sleep -Seconds 5
}
if (-not $allHealthy) { Warn "部分容器未在 180 秒内就绪" }

# 验证
Write-Host ""
try {
    $null = Invoke-RestMethod -Uri "http://localhost:10823/api/v1/system/health" -TimeoutSec 5
    Ok "Server API 健康"
} catch {
    Warn "Server API 未就绪"
}

Write-Host ""
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host "  LakeMind 部署完成！" -ForegroundColor Green
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ControlCenter:  http://localhost:3000"
Write-Host "  Server API:     http://localhost:10823"
Write-Host "  ModelServing:   http://localhost:10824"
Write-Host "  AssetMCP:       http://localhost:8401"
Write-Host "  DataMCP:        http://localhost:8402"
Write-Host "  AdminMCP:       http://localhost:8403"
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "验证: .\scripts\healthcheck.ps1"
Write-Host "停止: docker compose --env-file .env down"
