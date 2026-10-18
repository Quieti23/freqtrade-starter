[CmdletBinding()]
param(
    [ValidateSet("start", "init", "demo", "check", "status", "stop")]
    [string]$Action = "start",
    [ValidateSet("backtest", "paper", "both")]
    [string]$Mode = "backtest",
    [switch]$Gateway,
    [switch]$Redis,
    [ValidateRange(1, 365)]
    [int]$Days = 30,
    [switch]$SkipDemo
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Compose {
    param([string[]]$Arguments)
    & docker compose --project-directory $PSScriptRoot --file "$PSScriptRoot\compose.yaml" @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Compose failed ($LASTEXITCODE). Run .\start.ps1 -Action status, or docker compose logs."
    }
}

$previousRedisUrl = $env:GATEWAY_REDIS_URL
try {
    if ($Redis -and -not $Gateway) {
        throw "-Redis requires -Gateway."
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Install Docker Desktop with Linux containers, then run this script again."
    }
    $dockerOS = & docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0) { throw "Docker is not running." }
    if ($dockerOS -ne "linux") { throw "Switch Docker Desktop to Linux containers." }
    & docker compose version
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose v2 or newer is required." }
    if ($Action -eq "stop") {
        Invoke-Compose -Arguments @("--profile", "*", "down")
        return
    }
    if ($Action -eq "status") {
        Invoke-Compose -Arguments @("--profile", "*", "ps", "--all")
        return
    }
    New-Item -ItemType Directory -Path "$PSScriptRoot\runtime" -Force | Out-Null
    $helperFlags = @("--mode", $Mode)
    if ($Gateway) { $helperFlags += "--gateway" }
    if ($Redis) { $helperFlags += "--redis" }
    if ($Redis) { $env:GATEWAY_REDIS_URL = "redis://market_redis:6379/0" }
    else { $env:GATEWAY_REDIS_URL = "" }

    if ($Action -eq "start") {
        Invoke-Compose -Arguments @("--profile", "*", "stop", "backtest", "trader", "market_gateway", "market_redis")
    }
    if ($Action -in @("start", "init")) {
        Invoke-Compose -Arguments (@("run", "--rm", "--no-deps", "tools", "init") + $helperFlags)
    }
    if ($Action -eq "init") { return }
    $profiles = @("--profile", "tools")
    $services = @()
    if ($Mode -in @("backtest", "both")) {
        $profiles += @("--profile", "research")
        $services += "backtest"
    }
    if ($Mode -in @("paper", "both")) {
        $profiles += @("--profile", "paper")
        $services += "trader"
    }
    if ($Action -eq "start" -and $Redis) {
        $profiles += @("--profile", "redis")
        Invoke-Compose -Arguments ($profiles + @("up", "-d", "--wait", "--wait-timeout", "90", "market_redis"))
    }
    if ($Action -eq "start" -and $Gateway) {
        $profiles += @("--profile", "gateway")
        Invoke-Compose -Arguments ($profiles + @("up", "-d", "--build", "--wait", "--wait-timeout", "240", "market_gateway"))
    }
    if ($Action -eq "check") {
        Invoke-Compose -Arguments @("run", "--rm", "--no-deps", "tools", "validate")
        return
    }
    if ($Action -eq "demo") {
        Invoke-Compose -Arguments @("run", "--rm", "--no-deps", "tools", "demo", "--days", "$Days")
        return
    }
    Invoke-Compose -Arguments ($profiles + @("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "240") + $services)
    Invoke-Compose -Arguments (@("run", "--rm", "--no-deps", "tools", "verify") + $helperFlags)
    if (-not $SkipDemo -and $Mode -ne "paper") {
        Invoke-Compose -Arguments @("run", "--rm", "--no-deps", "tools", "demo", "--days", "$Days")
    }
    Write-Host "Ready. Selected service addresses (http):"
    foreach ($service in $services) {
        Write-Host "${service}:"
        Invoke-Compose -Arguments @("port", $service, "8080")
    }
    Write-Host "Credentials: runtime\config.backtest.json or runtime\config.paper.json -> api_server."
}
catch {
    Write-Error $_
    exit 1
}
finally {
    $env:GATEWAY_REDIS_URL = $previousRedisUrl
}
