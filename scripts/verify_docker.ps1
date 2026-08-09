# Focused re-run of Phase 2 verification checks 7 and 8 (the Docker gate).
# Closes OPEN-001. Use this while iterating on containers instead of the full
# verify_env.ps1, which also re-runs pytest and every pre-commit hook.
#
#   .\.venv\Scripts\Activate.ps1
#   .\scripts\verify_docker.ps1
#
# See docs/docker.md for what to do when a step fails.

$ErrorActionPreference = "Continue"
$fail = 0

function Step($name, $block) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: $name" -ForegroundColor Red; $script:fail++ }
    else { Write-Host "PASS: $name" -ForegroundColor Green }
}

# Probe the DAEMON, not just the CLI. `docker --version` succeeds with the
# daemon dead -- that is precisely why Phase 2 check 2 passed while 7 and 8
# failed. This step is the one that actually tells you the truth.
Write-Host "`n=== 0. Docker daemon reachable ===" -ForegroundColor Cyan
$server = docker info --format '{{.ServerVersion}}' 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: Docker daemon is not reachable." -ForegroundColor Red
    Write-Host $server -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Start Docker Desktop and WAIT for the tray icon to read" -ForegroundColor Yellow
    Write-Host "'Docker Desktop is running', then re-run this script." -ForegroundColor Yellow
    Write-Host "  Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'" -ForegroundColor Yellow
    Write-Host "If it will not start, see docs/docker.md section 2.3 (WSL / virtualization)." -ForegroundColor Yellow
    Write-Host "`n--------------------------------"
    Write-Host "Docker gate: BLOCKED (daemon down). Checks 7-8 not attempted." -ForegroundColor Red
    exit 1
}
Write-Host "Docker server version: $server"
Write-Host "PASS: Docker daemon reachable" -ForegroundColor Green

Step "7. Container build (light image)" { docker compose build app }
Step "8. Container hello-world"         { docker compose run --rm app python scripts/hello.py }

# Not part of the original Phase 2 gate, but it is the Phase 6 gate and it costs
# seconds once the image exists. Offline mode: no API key, no spend.
Step "9. Offline crew run in container" { docker compose run --rm agents }

Write-Host "`n--------------------------------"
if ($fail -eq 0) {
    Write-Host "Docker gate: ALL CHECKS PASSED - OPEN-001 can be closed." -ForegroundColor Green
    Write-Host "Now run .\scripts\verify_env.ps1 for the full 10/10 Phase 2 gate." -ForegroundColor Green
} else {
    Write-Host "Docker gate: $fail check(s) FAILED" -ForegroundColor Red
}
exit $fail
