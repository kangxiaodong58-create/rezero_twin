# ReZeroTwin EXE Build Script (auto-protect .env + data)
# Usage: .\build.ps1
#
# ============================================================
# DATA SAFETY RULES (V11.6.5) - DO NOT VIOLATE
# 1. NEVER delete user data: dist/data/, <project>/data/,
#    conversations.db, memory.json under data/
# 2. Clean only build cache and rebuildable binaries.
# 3. If wiping dist/, FIRST backup dist/data/, restore AFTER build.
# 4. .env backup/restore must NOT touch data/.
# 5. Acceptance: old chat survives overwrite install.
# 6. Dev may use a separate data_dev/; never treat "delete DB" as default test step.
# ============================================================

param(
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"
$RootEnv = Join-Path $ProjectRoot ".env"
$DistEnv = Join-Path $DistDir ".env"
$DistData = Join-Path $DistDir "data"
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"

Write-Host "=== ReZeroTwin Build Script ===" -ForegroundColor Cyan

# ── Step 1: Backup dist/.env + dist/data/ before clean ──
$TempBackup = $null
if (-not $SkipClean) {
    # 1a: backup .env
    if (Test-Path $DistEnv) {
        Write-Host "[BACKUP] dist/.env found, backing up to project root..." -ForegroundColor Yellow
        Copy-Item $DistEnv $RootEnv -Force
        Write-Host "[BACKUP] .env done" -ForegroundColor Green
    }

    # 1b: backup dist/data/ (V11.6.5 data safety)
    if (Test-Path $DistData) {
        $TempBackup = Join-Path $env:TEMP "rezero_data_backup_$(Get-Date -Format 'yyyyMMddHHmmss')"
        Write-Host "[BACKUP] dist/data/ found, backing up to temp..." -ForegroundColor Yellow
        Copy-Item $DistData $TempBackup -Recurse -Force
        if (-not (Test-Path $TempBackup)) {
            Write-Host "[ERROR] dist/data/ backup FAILED - aborting build to protect user data" -ForegroundColor Red
            exit 1
        }
        Write-Host "[BACKUP] dist/data/ backed up to: $TempBackup" -ForegroundColor Green
    }

    # ── Step 2: Clean old build artifacts ──
    Write-Host "[CLEAN] Removing build/ and dist/..." -ForegroundColor Yellow
    Remove-Item -Path $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $DistDir -Recurse -Force -ErrorAction SilentlyContinue
}

# ── Step 3: PyInstaller build ──
Write-Host "[BUILD] Starting PyInstaller..." -ForegroundColor Yellow
& $VenvPython -m PyInstaller ReZeroTwin.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] PyInstaller build failed" -ForegroundColor Red
    # Restore data even if build fails
    if ($TempBackup -and (Test-Path $TempBackup)) {
        Write-Host "[RESTORE] Restoring dist/data/ after build failure..." -ForegroundColor Yellow
        Copy-Item $TempBackup $DistData -Recurse -Force
        Remove-Item $TempBackup -Recurse -Force -ErrorAction SilentlyContinue
    }
    exit 1
}
Write-Host "[BUILD] PyInstaller completed" -ForegroundColor Green

# ── Step 4: Restore dist/data/ from backup (V11.6.5) ──
if ($TempBackup -and (Test-Path $TempBackup)) {
    Write-Host "[RESTORE] Restoring dist/data/ from backup..." -ForegroundColor Yellow
    # If dist/data exists (e.g. PyInstaller created it), overwrite with backup (old data wins)
    if (Test-Path $DistData) {
        Remove-Item $DistData -Recurse -Force
    }
    Copy-Item $TempBackup $DistData -Recurse -Force
    Remove-Item $TempBackup -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[RESTORE] dist/data/ restored" -ForegroundColor Green
}

# ── Step 5: Copy .env to dist/ ──
if (Test-Path $RootEnv) {
    Write-Host "[DEPLOY] Copying .env to dist/..." -ForegroundColor Yellow
    Copy-Item $RootEnv $DistEnv -Force
    Write-Host "[DEPLOY] .env deployed" -ForegroundColor Green
} else {
    Write-Host "[WARN] No .env in project root. Create one with DEEPSEEK_API_KEY" -ForegroundColor Red
    Write-Host "       Format: DEEPSEEK_API_KEY=sk-your-key-here" -ForegroundColor Yellow
}

# ── Verify ──
$ExePath = Join-Path $DistDir "ReZeroTwin.exe"
if (Test-Path $ExePath) {
    $size = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
    Write-Host ""
    Write-Host "=== BUILD SUCCESS ===" -ForegroundColor Green
    Write-Host "  EXE: $ExePath"
    Write-Host "  Size: ${size} MB"
    if (Test-Path $DistEnv) {
        Write-Host "  .env: deployed" -ForegroundColor Green
    } else {
        Write-Host "  .env: MISSING (place manually)" -ForegroundColor Red
    }
    if (Test-Path $DistData) {
        $dbPath = Join-Path $DistData "conversations.db"
        if (Test-Path $dbPath) {
            Write-Host "  data/: preserved (conversations.db OK)" -ForegroundColor Green
        } else {
            Write-Host "  data/: exists but no conversations.db" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  data/: none (fresh install)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[ERROR] EXE not generated" -ForegroundColor Red
    exit 1
}
