$ErrorActionPreference = "Continue"

$Project = (Get-Location).Path
$Root = Split-Path $Project -Parent
$Stamp = Get-Date -Format "yyyy_MM_dd_HHmmss"
$Out = Join-Path $Project "CLONEXA_STATUS_GPT_$Stamp.txt"

function Add-Line {
    param([string]$Text = "")
    Add-Content -Path $Out -Value $Text -Encoding UTF8
}

function Add-Section {
    param([string]$Title)
    Add-Line ""
    Add-Line "==============================================================================="
    Add-Line $Title
    Add-Line "==============================================================================="
}

function Run-Cmd {
    param(
        [string]$Title,
        [string]$Cmd
    )
    Add-Section $Title
    Add-Line "> $Cmd"
    try {
        $result = cmd.exe /c $Cmd 2>&1
        if ($result) {
            Add-Line ($result -join "`n")
        } else {
            Add-Line "(sin salida)"
        }
    } catch {
        Add-Line "ERROR: $($_.Exception.Message)"
    }
}

function Test-Endpoint {
    param([string]$Url)
    Add-Section "HTTP CHECK: $Url"
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
        Add-Line "STATUS: $($response.StatusCode)"
        $content = [string]$response.Content
        if ($content.Length -gt 5000) {
            $content = $content.Substring(0, 5000) + "`n...[TRUNCADO]"
        }
        Add-Line $content
    } catch {
        Add-Line "ERROR: $($_.Exception.Message)"
    }
}

function File-Status {
    param([string]$Path)

    Add-Section "FILE STATUS: $Path"

    if (!(Test-Path $Path)) {
        Add-Line "NO EXISTE"
        return
    }

    $item = Get-Item $Path
    Add-Line "EXISTE: SI"
    Add-Line "FullName: $($item.FullName)"
    Add-Line "Size: $($item.Length)"
    Add-Line "LastWriteTime: $($item.LastWriteTime)"

    try {
        $hash = Get-FileHash $Path -Algorithm SHA256
        Add-Line "SHA256: $($hash.Hash)"
    } catch {
        Add-Line "HASH ERROR: $($_.Exception.Message)"
    }
}

function Search-Patterns {
    param(
        [string]$Path,
        [string[]]$Patterns
    )

    Add-Section "PATTERN SEARCH: $Path"

    if (!(Test-Path $Path)) {
        Add-Line "NO EXISTE"
        return
    }

    foreach ($pattern in $Patterns) {
        Add-Line ""
        Add-Line ">>> $pattern"
        try {
            $matches = Select-String -Path $Path -Pattern $pattern -SimpleMatch -ErrorAction SilentlyContinue
            if ($matches) {
                foreach ($m in $matches) {
                    Add-Line ("L{0}: {1}" -f $m.LineNumber, $m.Line.Trim())
                }
            } else {
                Add-Line "NO ENCONTRADO"
            }
        } catch {
            Add-Line "ERROR: $($_.Exception.Message)"
        }
    }
}

function File-Context {
    param(
        [string]$Path,
        [string]$Regex,
        [int]$Before = 8,
        [int]$After = 90
    )

    Add-Section "FILE CONTEXT: $Path :: $Regex"

    if (!(Test-Path $Path)) {
        Add-Line "NO EXISTE"
        return
    }

    $lines = Get-Content $Path
    $indexes = @()

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $Regex) {
            $indexes += $i
        }
    }

    if ($indexes.Count -eq 0) {
        Add-Line "NO ENCONTRADO"
        return
    }

    $idx = $indexes[0]
    $from = [Math]::Max(0, $idx - $Before)
    $to = [Math]::Min($lines.Count - 1, $idx + $After)

    for ($i = $from; $i -le $to; $i++) {
        Add-Line ("{0,5}: {1}" -f ($i + 1), $lines[$i])
    }
}

Add-Line "CLONEXA STATUS GPT EXPORT"
Add-Line "GeneratedAt: $(Get-Date -Format o)"
Add-Line "Project: $Project"
Add-Line "Root: $Root"
Add-Line "Computer: $env:COMPUTERNAME"
Add-Line "User: $env:USERNAME"

Add-Section "DIRECTORY"
Run-Cmd "CURRENT DIRECTORY LIST" "dir"

Add-Section "DOCKER"
Run-Cmd "DOCKER VERSION" "docker --version"
Run-Cmd "DOCKER COMPOSE VERSION" "docker compose version"
Run-Cmd "DOCKER COMPOSE SERVICES" "docker compose -p clonexa config --services"
Run-Cmd "DOCKER COMPOSE PS" "docker compose -p clonexa ps"
Run-Cmd "DOCKER CONTAINERS CLONEXA" "docker ps -a --filter name=clonexa"

Add-Section "API HEALTH CHECKS"
Test-Endpoint "http://127.0.0.1:8000/health"
Test-Endpoint "http://127.0.0.1:8000/api/v1/companies"
Test-Endpoint "http://127.0.0.1:8000/api/v1/packages"
Test-Endpoint "http://127.0.0.1:8000/api/v1/modules"

Add-Section "DOCKER LOGS"
Run-Cmd "API LOGS TAIL 260" "docker compose -p clonexa logs --tail=260 api"
Run-Cmd "DB LOGS TAIL 120" "docker compose -p clonexa logs --tail=120 db"

Add-Section "GIT"
Run-Cmd "GIT STATUS" "git status --short"
Run-Cmd "GIT BRANCH" "git branch --show-current"
Run-Cmd "GIT LOG LAST 8" "git log --oneline -8"
Run-Cmd "GIT DIFF NAME ONLY" "git diff --name-only"
Run-Cmd "GIT DIFF STAT" "git diff --stat"

Add-Section "CRITICAL FILES"
File-Status "app\services\auth_service.py"
File-Status "app\api\v1\endpoints\company_users.py"
File-Status "app\api\v1\endpoints\auth.py"
File-Status "app\web\admin_v2.js"
File-Status "docker-compose.yml"
File-Status "alembic.ini"

$authPatterns = @(
    "company_mini_payload",
    "company_modules_payload",
    "company_user_out_payload",
    "user_mini_payload",
    "hash_password",
    "verify_password",
    "create_access_token",
    "authenticate_user",
    "create_company_user",
    "created_at",
    "updated_at",
    "last_password_reset_at"
)

Search-Patterns "app\services\auth_service.py" $authPatterns
Search-Patterns "app\api\v1\endpoints\auth.py" $authPatterns
Search-Patterns "app\api\v1\endpoints\company_users.py" $authPatterns

File-Context "app\services\auth_service.py" "def\s+create_company_user" 10 120
File-Context "app\services\auth_service.py" "def\s+company_mini_payload" 5 40
File-Context "app\services\auth_service.py" "def\s+company_modules_payload" 5 40
File-Context "app\services\auth_service.py" "def\s+company_user_out_payload" 5 50

Add-Section "BACKUPS AND PATCH FILES"
try {
    Add-Line "Root backups:"
    $backups = Get-ChildItem $Root -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "backup|008d|008e|auth" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object FullName, LastWriteTime

    if ($backups) {
        Add-Line ($backups | Format-Table -AutoSize | Out-String)
    } else {
        Add-Line "No se encontraron backups en Root."
    }
} catch {
    Add-Line "ERROR backups root: $($_.Exception.Message)"
}

try {
    $downloads = Join-Path $env:USERPROFILE "Downloads"
    Add-Line "Downloads ZIPs relacionados:"
    $zips = Get-ChildItem $downloads -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "clonexa|008d|008e|008f|owner|admin" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object Name, FullName, LastWriteTime, Length

    if ($zips) {
        Add-Line ($zips | Format-Table -AutoSize | Out-String)
    } else {
        Add-Line "No se encontraron ZIPs relacionados en Downloads."
    }
} catch {
    Add-Line "ERROR downloads: $($_.Exception.Message)"
}

Add-Section "ALEMBIC"
Run-Cmd "ALEMBIC CURRENT" "alembic current"
Run-Cmd "ALEMBIC HISTORY LAST" "alembic history -r -8:current"

Add-Section "SUMMARY FLAGS"

$authFile = "app\services\auth_service.py"

if (Test-Path $authFile) {
    $authContent = Get-Content $authFile -Raw

    $required = @(
        "company_mini_payload",
        "company_modules_payload",
        "company_user_out_payload",
        "hash_password",
        "verify_password",
        "create_access_token",
        "authenticate_user",
        "create_company_user"
    )

    foreach ($r in $required) {
        if ($authContent -match $r) {
            Add-Line "OK: auth_service.py contiene $r"
        } else {
            Add-Line "MISSING: auth_service.py NO contiene $r"
        }
    }

    if ($authContent -match "created_at\s*=" -and $authContent -match "updated_at\s*=") {
        Add-Line "POSSIBLE_OK: auth_service.py contiene asignaciones created_at/updated_at"
    } else {
        Add-Line "POSSIBLE_ISSUE: auth_service.py NO muestra asignaciones claras created_at/updated_at"
    }
} else {
    Add-Line "CRITICAL: auth_service.py no existe"
}

Add-Line ""
Add-Line "EXPORT_FILE: $Out"

Write-Host ""
Write-Host "STATUS EXPORT GENERADO:"
Write-Host $Out
Write-Host ""
Write-Host "Sube ese archivo TXT al chat."
