# LakeMind health check (Windows PowerShell)
# Exit 0 = all healthy, exit 1 = some failures
Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$ErrorActionPreference = "Continue"
$failCount = 0

Write-Host "=== Containers ===" -ForegroundColor Green
docker compose --env-file .env ps 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "  [FAIL] compose not started" -ForegroundColor Red; $failCount++ }

Write-Host "`n=== Server API ===" -ForegroundColor Green
try {
    $h = Invoke-RestMethod -Uri "http://localhost:10823/api/v1/system/health" -TimeoutSec 5
    $h | ConvertTo-Json -Depth 3
} catch {
    Write-Host "  [FAIL] Server API unreachable" -ForegroundColor Red; $failCount++
}

Write-Host "`n=== MCP Health ===" -ForegroundColor Green
foreach ($port in 8401, 8402, 8403) {
    try {
        $null = Invoke-RestMethod -Uri "http://localhost:$port/health" -TimeoutSec 3
        Write-Host "  MCP :$port -- OK"
    } catch {
        Write-Host "  MCP :$port -- FAIL" -ForegroundColor Red; $failCount++
    }
}

Write-Host "`n=== Ray Serve ===" -ForegroundColor Green
try {
    $output = docker exec lakemind-ray-head python -c "
import ray; ray.init(address='auto', ignore_reinit_error=True, log_to_driver=False)
from ray import serve
s = serve.status()
if not s.applications:
    print('  [WARN] No Serve application running')
for n, a in s.applications.items():
    print(f'  {n}: {a.status.name}')
" 2>&1
    $output | ForEach-Object { Write-Host $_ }
    if ($output -notmatch "RUNNING") { $failCount++ }
} catch {
    Write-Host "  [FAIL] Ray unreachable" -ForegroundColor Red; $failCount++
}

Write-Host "`n=== ControlCenter ===" -ForegroundColor Green
try { $null = Invoke-RestMethod "http://localhost:3000/health" -TimeoutSec 3; Write-Host "  OK" }
catch { Write-Host "  FAIL" -ForegroundColor Red; $failCount++ }

Write-Host "`n=== ModelServing ===" -ForegroundColor Green
try { $null = Invoke-RestMethod "http://localhost:10824/health/ready" -TimeoutSec 3; Write-Host "  OK" }
catch { Write-Host "  FAIL" -ForegroundColor Red; $failCount++ }

Write-Host "`n=== Meeting Agent ===" -ForegroundColor Green
try { $null = Invoke-RestMethod "http://localhost:9100/api/health" -TimeoutSec 3; Write-Host "  OK" }
catch {
    try { $null = Invoke-WebRequest "http://localhost:9100" -TimeoutSec 3 -UseBasicParsing; Write-Host "  OK (web UI)" }
    catch { Write-Host "  FAIL" -ForegroundColor Red; $failCount++ }
}

Write-Host ""
if ($failCount -eq 0) {
    Write-Host "All checks passed." -ForegroundColor Green
} else {
    Write-Host "$failCount check(s) failed." -ForegroundColor Red
}
exit $failCount
