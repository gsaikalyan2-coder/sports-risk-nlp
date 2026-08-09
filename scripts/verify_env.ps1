# Phase 2 environment verification runbook (Windows / PowerShell).
# Run from the repo root inside the activated .venv:
#   .\.venv\Scripts\Activate.ps1
#   .\scripts\verify_env.ps1
# Each step prints PASS/FAIL. Stop at the first FAIL and report the error.
#
# Iterating on Docker specifically? Use .\scripts\verify_docker.ps1 instead --
# it re-runs only the container checks. See docs/docker.md.

$ErrorActionPreference = "Continue"
$fail = 0
function Step($name, $block) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: $name" -ForegroundColor Red; $script:fail++ }
    else { Write-Host "PASS: $name" -ForegroundColor Green }
}

Step "1. Python version (expect 3.11.x)" { python --version }

# Probes the daemon, not just the CLI. `docker --version` succeeds even when the
# daemon is down, which is how checks 7-8 previously failed while check 2 passed.
Step "2. Docker daemon reachable"        { docker info --format '{{.ServerVersion}}' }

Step "3. Git status"                     { git status --short; $global:LASTEXITCODE = 0 }
Step "4. Dependency consistency"         { pip check }
Step "5. Test suite"                     { pytest }
Step "6. Local hello-world"              { python scripts/hello.py }
Step "7. Container build (light image)"  { docker compose build app }
Step "8. Container hello-world"          { docker compose run --rm app python scripts/hello.py }
Step "9. Offline crew run (Phase 6 gate)" { python scripts/run_crew.py --offline }
Step "10. Pre-commit hooks over repo"    { pre-commit run --all-files }

Write-Host "`n=== 11. Secret hygiene ===" -ForegroundColor Cyan
$tracked = git ls-files | Select-String -Pattern "^\.env$"
if ($tracked) { Write-Host "FAIL: .env is tracked by git!" -ForegroundColor Red; $fail++ }
else { Write-Host "PASS: .env is not tracked" -ForegroundColor Green }

Write-Host "`n--------------------------------"
if ($fail -eq 0) { Write-Host "Phase 2 environment: ALL CHECKS PASSED" -ForegroundColor Green }
else { Write-Host "Phase 2 environment: $fail check(s) FAILED" -ForegroundColor Red }
exit $fail
