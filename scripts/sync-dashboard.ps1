<#
.SYNOPSIS
    Sync the dashboard subset from the private research repo into the public
    deploy repo, then commit and push so Streamlit Cloud rebuilds.

.DESCRIPTION
    Two repositories hold the same dashboard code:

      C:\Users\saika\sports-risk-nlp   private  -- the research repo, source of truth
      C:\Users\saika\srn-dashboard     public   -- the deploy repo, feeds Streamlit Cloud

    The research repo is authoritative for CODE. The deploy repo is authoritative
    for its own DEPLOYMENT FILES -- README.md, requirements.txt,
    .streamlit/config.toml, .gitignore -- which have no counterpart upstream and
    must never be overwritten by this script. That split is why this is a
    per-path copy and not a mirror of the whole tree: a mirror would delete the
    four files that make the deploy repo deployable.

    Runs in DRY RUN by default. Nothing is copied, committed or pushed until you
    pass -Apply. Read the diff it prints first.

.EXAMPLE
    .\sync-dashboard.ps1
    Show what would change. Copies nothing.

.EXAMPLE
    .\sync-dashboard.ps1 -Apply -Message "Phase 27: pupil baseline fix"
    Copy, commit with that message, and push.
#>

[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$Message = "",
    [string]$Source  = "C:\Users\saika\sports-risk-nlp",
    [string]$Deploy  = "C:\Users\saika\srn-dashboard"
)

$ErrorActionPreference = "Stop"

function Fail($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }
function Note($text) { Write-Host $text -ForegroundColor Cyan }

# --- sanity: both repos exist and are the ones we think they are ------------
if (-not (Test-Path $Source)) { Fail "research repo not found at $Source" }
if (-not (Test-Path $Deploy)) { Fail "deploy repo not found at $Deploy" }
if (-not (Test-Path (Join-Path $Deploy ".git"))) {
    Fail "$Deploy is not a git repository. If the .git folder is missing the deploy repo needs re-cloning from GitHub."
}
if (-not (Test-Path (Join-Path $Deploy "requirements.txt"))) {
    Fail "$Deploy has no requirements.txt -- that is a deployment file this script must not create. Wrong folder?"
}

# Refuse to run when the deploy repo has uncommitted work, because the commit
# below would sweep it up unreviewed.
Push-Location $Deploy
$dirty = git status --porcelain
Pop-Location
if ($dirty -and -not $Apply) {
    Note "NOTE: the deploy repo already has uncommitted changes:"
    $dirty | ForEach-Object { Write-Host "  $_" }
    Write-Host ""
}
if ($dirty -and $Apply) {
    Fail "the deploy repo has uncommitted changes. Commit or discard them first, so this sync's commit contains only the sync."
}

# --- what gets copied -------------------------------------------------------
# Directories mirrored wholesale (with /MIR, so deletions upstream propagate).
$dirs = @(
    "src",
    "dashboard",
    "config",
    "assets\narration"
)
# Individual files. tests\fixtures holds the committed known examples the
# ReplayBackend reads; paper\refs.bib is REQUIRED -- atlas_map.load_atlas()
# raises AtlasError rather than render a brain figure whose instrument anchors
# cannot be verified, so a sync that drops it breaks the Brain atlas page.
$files = @(
    @{ From = "tests\fixtures\dashboard_known_examples.json"; To = "tests\fixtures\dashboard_known_examples.json" },
    @{ From = "paper\refs.bib";                               To = "paper\refs.bib" }
)

# Never copied, whatever they contain.
$excludeDirs  = @("__pycache__", ".pytest_cache", ".ruff_cache", ".venv")
$excludeFiles = @("*.pyc", ".env")

$mode = if ($Apply) { "APPLY" } else { "DRY RUN" }
Note "=== sync-dashboard [$mode] ==="
Note "  from : $Source"
Note "  to   : $Deploy"
Write-Host ""

# --- copy -------------------------------------------------------------------
# /MIR mirrors (deletes files in the destination that are gone from the source),
# which is what keeps a renamed or deleted module from lingering in the deploy
# repo. It is safe ONLY because every path above is code that the research repo
# owns outright; it is never pointed at the deploy repo's root.
$roboFlags = @("/NJH", "/NJS", "/NP", "/NDL")
$roboFlags += "/XD"; $roboFlags += $excludeDirs
$roboFlags += "/XF"; $roboFlags += $excludeFiles
if (-not $Apply) { $roboFlags += "/L" }   # /L = list only, copy nothing

foreach ($d in $dirs) {
    $src = Join-Path $Source $d
    $dst = Join-Path $Deploy $d
    if (-not (Test-Path $src)) { Fail "expected directory missing in the research repo: $src" }
    Note "-- $d"
    robocopy $src $dst /MIR @roboFlags | Where-Object { $_.Trim() } | ForEach-Object { Write-Host "   $_" }
    # robocopy exit codes 0-7 are success; 8+ is a real failure.
    if ($LASTEXITCODE -ge 8) { Fail "robocopy failed on $d (exit $LASTEXITCODE)" }
}

foreach ($f in $files) {
    $src = Join-Path $Source $f.From
    $dst = Join-Path $Deploy $f.To
    if (-not (Test-Path $src)) { Fail "required file missing in the research repo: $src" }
    Note "-- $($f.To)"
    if ($Apply) {
        New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
        Copy-Item $src $dst -Force
        Write-Host "   copied"
    } else {
        $same = (Test-Path $dst) -and ((Get-FileHash $src).Hash -eq (Get-FileHash $dst).Hash)
        Write-Host $(if ($same) { "   unchanged" } else { "   WOULD COPY" })
    }
}

Write-Host ""

# --- show the result --------------------------------------------------------
Push-Location $Deploy
try {
    $changed = git status --porcelain
    if (-not $changed) {
        Note "Deploy repo is already up to date. Nothing to commit."
        exit 0
    }

    Note "Changes in the deploy repo:"
    $changed | ForEach-Object { Write-Host "  $_" }
    Write-Host ""

    # A deployment file appearing here means the copy list above reached
    # something it should not have. Stop rather than push it.
    $protected = @("README.md", "requirements.txt", ".streamlit/config.toml", ".gitignore")
    foreach ($p in $protected) {
        if ($changed -match [regex]::Escape($p)) {
            Fail "$p changed. That file belongs to the deploy repo and the sync must not touch it. Investigate before pushing."
        }
    }

    if (-not $Apply) {
        Note "DRY RUN -- nothing was copied. Re-run with -Apply to sync for real:"
        Write-Host "  .\sync-dashboard.ps1 -Apply -Message ""what changed"""
        exit 0
    }

    if (-not $Message) {
        $Message = "Sync dashboard from research repo"
    }

    git add -A
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { Fail "git commit failed" }
    git push
    if ($LASTEXITCODE -ne 0) { Fail "git push failed" }

    Write-Host ""
    Note "Pushed. Streamlit Cloud rebuilds automatically -- give it 2-3 minutes."
}
finally {
    Pop-Location
}
