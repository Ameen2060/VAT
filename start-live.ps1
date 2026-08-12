# ============================================================================
#  UAE VAT Compliance — one-command "bring the live site back up"
#
#  Run this after a reboot / if the site shows "server temporarily unavailable":
#      powershell -ExecutionPolicy Bypass -File .\start-live.ps1
#
#  It (1) starts the backend, (2) opens a public tunnel, (3) points the live
#  Vercel site (vat-ameen.vercel.app) at the new tunnel URL and redeploys.
#
#  NOTE: this is a STOPGAP while the backend runs on this machine. The permanent
#  fix is deploying the backend to Render (then this script is not needed at all).
# ============================================================================

$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$py     = Join-Path $root "apps\api\.venv\Scripts\python.exe"
$node   = "$env:LOCALAPPDATA\nodejs-portable\node-v20.18.1-win-x64"
$vc     = "$node\node_modules\vercel\dist\index.js"
$cf     = Join-Path $root "infra\cloudflared.exe"
$web    = Join-Path $root "apps\web"
$api    = Join-Path $root "apps\api"
$env:VERCEL_TELEMETRY_DISABLED = "1"

Write-Host "== 1/4  Restarting backend (port 8000) ==" -ForegroundColor Cyan
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
$env:EXPOSE_RESET_LINK = "true"
$env:APP_BASE_URL      = "https://vat-ameen.vercel.app"
Start-Process -WindowStyle Hidden -WorkingDirectory $api -FilePath $py `
  -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000"
# wait for health
for ($i=0; $i -lt 30; $i++) {
  try { if ((Invoke-WebRequest "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) { break } } catch {}
  Start-Sleep -Seconds 2
}
Write-Host "   backend up." -ForegroundColor Green

Write-Host "== 2/4  Opening public tunnel ==" -ForegroundColor Cyan
$tlog = Join-Path $env:TEMP "vat-tunnel.log"
if (Test-Path $tlog) { Remove-Item $tlog -Force }
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process -WindowStyle Hidden -FilePath $cf `
  -ArgumentList "tunnel","--url","http://localhost:8000","--no-autoupdate" `
  -RedirectStandardOutput $tlog -RedirectStandardError "$tlog.err"
$backendUrl = $null
for ($i=0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 2
  $hit = Select-String -Path $tlog,"$tlog.err" -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($hit) { $backendUrl = ($hit.Matches[0].Value); break }
}
if (-not $backendUrl) { Write-Host "   Could not obtain a tunnel URL." -ForegroundColor Red; exit 1 }
Write-Host "   tunnel: $backendUrl" -ForegroundColor Green

Write-Host "== 3/4  Pointing Vercel at the new backend ==" -ForegroundColor Cyan
Push-Location $web
foreach ($e in @("production","preview","development")) {
  & $node $vc env rm BACKEND_ORIGIN $e --yes 2>$null | Out-Null
  $backendUrl | & $node $vc env add BACKEND_ORIGIN $e 2>$null | Out-Null
}
Write-Host "== 4/4  Redeploying frontend (vat-ameen.vercel.app) ==" -ForegroundColor Cyan
& $node $vc --prod --yes 2>&1 | Select-String -Pattern "Aliased|Production|Error" | Select-Object -Last 3
Pop-Location

Write-Host ""
Write-Host "DONE — live at https://vat-ameen.vercel.app  (backend via $backendUrl)" -ForegroundColor Green
Write-Host "Keep this machine on and online for the site to stay up." -ForegroundColor Yellow
