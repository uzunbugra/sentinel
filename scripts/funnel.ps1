<#
.SYNOPSIS
    Run SentinelFlow on this computer and share it through Tailscale Funnel.

.DESCRIPTION
    Starts the Docker Compose stack with deploy/funnel/compose.funnel.yml (all
    ports on 127.0.0.1, one proxy on 127.0.0.1:8088), waits until the API is
    healthy through the proxy, then turns on Tailscale Funnel for port 8088 and
    prints the public https://<machine>.<tailnet>.ts.net address.

    The address works only while this computer is on, Docker is running and
    Funnel is on. Turn it off after the demo with -Stop.

    See docs/DEMO_TAILSCALE.md.

.PARAMETER Stop
    Turn Funnel off. The containers keep running locally.

.PARAMETER Down
    Turn Funnel off and stop the containers (data volumes are kept).

.PARAMETER NoBuild
    Start the existing images without rebuilding them.

.PARAMETER LocalOnly
    Start the stack and proxy but do not turn on Funnel
    (open http://localhost:8088 to rehearse).

.EXAMPLE
    .\scripts\funnel.ps1
    .\scripts\funnel.ps1 -Stop
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Down,
    [switch]$NoBuild,
    [switch]$LocalOnly
)

$ErrorActionPreference = 'Stop'
$ProxyPort = 8088
$Root = Split-Path -Parent $PSScriptRoot
$ComposeArgs = @('compose', '-f', 'docker-compose.yml', '-f', 'deploy/funnel/compose.funnel.yml')

function Find-Tailscale {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # ProgramW6432 is the 64-bit Program Files even from a 32-bit PowerShell,
    # where ProgramFiles points to "Program Files (x86)".
    foreach ($path in @(
            "$env:ProgramW6432\Tailscale\tailscale.exe",
            "$env:ProgramFiles\Tailscale\tailscale.exe",
            '/Applications/Tailscale.app/Contents/MacOS/Tailscale',
            '/usr/bin/tailscale')) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    throw 'Tailscale bulunamadı. https://tailscale.com/download adresinden kurup giriş yapın (docs/DEMO_TAILSCALE.md §1).'
}

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    # Docker and Tailscale write progress to stderr. Windows PowerShell 5.1
    # turns that into an error record, which 'Stop' would make fatal when the
    # output is redirected; success is decided by the exit code instead.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Exe @Arguments 2>&1 | ForEach-Object { Write-Host $_ } }
    finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') başarısız (çıkış kodu $LASTEXITCODE)" }
}

Push-Location $Root
try {
    if ($Stop -or $Down) {
        $tailscale = Find-Tailscale
        & $tailscale funnel --https=443 off
        Write-Host 'Funnel kapatıldı; genel adres artık açılmıyor.'
        if ($Down) {
            Invoke-Native docker ($ComposeArgs + @('down'))
            Write-Host 'Konteynerler durduruldu (veri volume''ları duruyor).'
        }
        return
    }

    if (-not (Test-Path '.env')) {
        throw '.env yok. .env.example dosyasını .env olarak kopyalayıp parolaları doldurun (docs/DEMO_TAILSCALE.md §2).'
    }
    if (-not (Test-Path 'models/fraud/current/model.txt')) {
        Write-Warning 'models/fraud/current altında model yok; ML alarmları üretilmez (docs/SPRINT4_DEMO.md §1).'
    }

    $tailscale = $null
    if (-not $LocalOnly) {
        $tailscale = Find-Tailscale
        $status = & $tailscale status --json | ConvertFrom-Json
        if ($status.BackendState -ne 'Running') {
            throw "Tailscale bağlı değil (durum: $($status.BackendState)). 'tailscale up' ile giriş yapın."
        }
    }

    $up = $ComposeArgs + @('up', '-d')
    if (-not $NoBuild) { $up += '--build' }
    try {
        Invoke-Native docker $up
    } catch {
        # One unhealthy optional service (e.g. Neo4j) makes `up` fail although
        # the web and API run. The API health check below decides.
        Write-Warning "docker compose up hata verdi: $($_.Exception.Message)"
        Write-Warning "Servislerin durumu: docker compose -f docker-compose.yml -f deploy/funnel/compose.funnel.yml ps -a"
    }

    $health = "http://127.0.0.1:$ProxyPort/api/v1/system/health"
    Write-Host "API bekleniyor: $health"
    $deadline = (Get-Date).AddMinutes(3)
    $healthy = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-RestMethod $health -TimeoutSec 5
            if ($resp.status -eq 'healthy' -or $resp.status -eq 'degraded') { $healthy = $true; break }
        } catch { }
        Start-Sleep -Seconds 3
    }
    if (-not $healthy) {
        throw "API 3 dakikada hazır olmadı. 'docker compose -f docker-compose.yml -f deploy/funnel/compose.funnel.yml logs api caddy' ile bakın."
    }
    Write-Host "Yerel adres: http://localhost:$ProxyPort"

    if ($LocalOnly) { return }

    Invoke-Native $tailscale @('funnel', '--bg', "$ProxyPort")
    $dns = ((& $tailscale status --json | ConvertFrom-Json).Self.DNSName).TrimEnd('.')
    Write-Host ''
    Write-Host "Paylaşılacak adres: https://$dns" -ForegroundColor Green
    Write-Host 'Bu adres bilgisayar açık ve Funnel açıkken çalışır. Demodan sonra:  .\scripts\funnel.ps1 -Stop'
    Write-Host 'İlk açılışta sertifika alınırken birkaç saniye beklemek gerekebilir.'
}
finally {
    Pop-Location
}
