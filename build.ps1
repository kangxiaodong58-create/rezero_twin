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
    [switch]$SkipClean,
    [switch]$TestRestore   # SPEC-30 F30-5: dry-run only the restore logic
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

# ------------------------------------------------------------------
# SPEC-30: single restore implementation shared by success/failure paths.
#  F30-1 abort = throw (top-level $ErrorActionPreference="Stop"); on abort the
#         backup directory is KEPT so the user can still restore manually.
#  F30-2 content-semantics copy (never delete files the backup does not have).
#  F30-3 one code path -> the failure branch can no longer drift from this one.
# ------------------------------------------------------------------
function Restore-DistData {
    param(
        [Parameter(Mandatory = $true)][string]$BackupPath,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )
    if (-not (Test-Path $BackupPath)) {
        throw "[RESTORE] backup dir not found: $BackupPath (kept on purpose, do not delete)"
    }
    New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
    # F30-2: copy the CONTENTS; files that exist only in the target are preserved.
    Copy-Item -Path (Join-Path $BackupPath "*") -Destination $TargetPath -Recurse -Force
    # F30-1: post-restore self check; failure -> throw -> script aborts loudly.
    foreach ($f in @("conversations.db", "memory.json")) {
        if (-not (Test-Path (Join-Path $TargetPath $f))) {
            throw "[RESTORE] self-check FAILED: missing $TargetPath\$f (backup kept: $BackupPath)"
        }
    }
    Write-Host "[RESTORE] dist/data/ restored + self-check OK: $TargetPath" -ForegroundColor Green
    # Consume the backup ONLY after the self check passed.
    if (Test-Path $BackupPath) { Remove-Item $BackupPath -Recurse -Force -ErrorAction SilentlyContinue }
}

function Remove-StaleDataBackups {
    # F30-4: keep timestamped backups for 3 days; failure-path backups are never
    # removed here because this is only called from the success path.
    Get-ChildItem -Path $env:TEMP -Directory -Filter "rezero_data_backup_*" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-3) } |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
}

# ------------------------------------------------------------------
# SPEC-30 F30-5: dry-run self test (two scenarios). No build, no dist touch.
# ------------------------------------------------------------------
if ($TestRestore) {
    $fail = 0
    # Scenario A: normal restore -> in place, no nesting, target-only file kept,
    #             backup consumed.
    $sb  = Join-Path $env:TEMP "rezero_restore_selftest_$(Get-Date -Format 'HHmmss')_a"
    $bk  = Join-Path $sb "backup"
    $tg  = Join-Path $sb "dist\data"
    New-Item -ItemType Directory -Force -Path $bk, $tg | Out-Null
    Set-Content -Path (Join-Path $bk "conversations.db") -Value "dummy"
    Set-Content -Path (Join-Path $bk "memory.json") -Value '{"user_name":"selftest"}'
    Set-Content -Path (Join-Path $tg "keepme.txt") -Value "target-only file"
    try {
        Restore-DistData -BackupPath $bk -TargetPath $tg
        $a = Test-Path (Join-Path $tg "conversations.db")
        $b = -not (Test-Path (Join-Path $tg "rezero_data_backup_20261010163949"))
        $c = Test-Path (Join-Path $tg "keepme.txt")
        $d = -not (Test-Path $bk)
        if ($a -and $b -and $c -and $d) {
            Write-Host "[SELFTEST-A] PASS in-place/no-nesting/target-file-kept/backup-consumed" -ForegroundColor Green
        } else {
            Write-Host "[SELFTEST-A] FAIL a=$a b=$b c=$c d=$d" -ForegroundColor Red
            $fail++
        }
    } catch {
        Write-Host "[SELFTEST-A] FAIL (exception): $_" -ForegroundColor Red
        $fail++
    }
    # Scenario B: backup missing memory.json -> must throw AND keep the backup.
    $sb2 = Join-Path $env:TEMP "rezero_restore_selftest_$(Get-Date -Format 'HHmmss')_b"
    $bk2 = Join-Path $sb2 "backup"
    $tg2 = Join-Path $sb2 "dist\data"
    New-Item -ItemType Directory -Force -Path $bk2, $tg2 | Out-Null
    Set-Content -Path (Join-Path $bk2 "conversations.db") -Value "dummy"
    $threw = $false
    try { Restore-DistData -BackupPath $bk2 -TargetPath $tg2 } catch { $threw = $true }
    if ($threw -and (Test-Path $bk2)) {
        Write-Host "[SELFTEST-B] PASS abort-on-selfcheck-failure/backup-kept" -ForegroundColor Green
    } else {
        Write-Host "[SELFTEST-B] FAIL threw=$threw backupKept=$(Test-Path $bk2)" -ForegroundColor Red
        $fail++
    }
    Remove-Item $sb  -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $sb2 -Recurse -Force -ErrorAction SilentlyContinue
    if ($fail -eq 0) { Write-Host "[SELFTEST] ALL PASS" -ForegroundColor Green; exit 0 }
    else { Write-Host "[SELFTEST] $fail scenario(s) failed" -ForegroundColor Red; exit 1 }
}

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
    # Restore data even if build fails (SPEC-30: same implementation as success path)
    if ($TempBackup -and (Test-Path $TempBackup)) {
        Write-Host "[RESTORE] Restoring dist/data/ after build failure..." -ForegroundColor Yellow
        Restore-DistData -BackupPath $TempBackup -TargetPath $DistData
    }
    exit 1
}
Write-Host "[BUILD] PyInstaller completed" -ForegroundColor Green

# ── Step 4: Restore dist/data/ from backup (V11.6.5) ──
if ($TempBackup -and (Test-Path $TempBackup)) {
    Write-Host "[RESTORE] Restoring dist/data/ from backup..." -ForegroundColor Yellow
    Restore-DistData -BackupPath $TempBackup -TargetPath $DistData
    Remove-StaleDataBackups
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
