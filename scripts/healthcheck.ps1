# LakeMind health check (Windows PowerShell)
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))

Write-Host "=== Containers ===" -ForegroundColor Green
docker compose --env-file .env ps 2>$null

Write-Host "`n=== Server API ===" -ForegroundColor Green
try {
    $h = Invoke-RestMethod -Uri "http://localhost:10823/api/v1/system/health" -TimeoutSec 5
    $h | ConvertTo-Json -Depth 3
} catch {
    Write-Host "  [FAIL] Server API unreachable" -ForegroundColor Red
}

Write-Host "`n=== MCP Health ===" -ForegroundColor Green
foreach ($port in 8401, 8402, 8403) {
    try {
        $null = Invoke-RestMethod -Uri "http://localhost:$port/health" -TimeoutSec 3
        Write-Host "  MCP :$port -- OK"
    } catch {
        Write-Host "  MCP :$port -- FAIL" -ForegroundColor Red
    }
}

Write-Host "`n=== Ray Serve ===" -ForegroundColor Green
try {
    $output = docker exec lakemind-ray-head python3 -c "
import ray; ray.init(address='auto', ignore_reinit_error=True)
from ray import serve
s = serve.status()
if not s.applications:
    print('  [WARN] No Serve application running')
for n, a in s.applications.items():
    print(f'  {n}: {a.status.name}')
" 2>&1
    Write-Host $output
} catch {
    Write-Host "  [FAIL] Ray unreachable" -ForegroundColor Red
}

Write-Host "`n=== ControlCenter ===" -ForegroundColor Green
try { $null = Invoke-RestMethod "http://localhost:3000/health" -TimeoutSec 3; Write-Host "  OK" }
catch { Write-Host "  FAIL" -ForegroundColor Red }

Write-Host "`n=== ModelServing ===" -ForegroundColor Green
try { $null = Invoke-RestMethod "http://localhost:10824/health/ready" -TimeoutSec 3; Write-Host "  OK" }
catch { Write-Host "  FAIL" -ForegroundColor Red }
