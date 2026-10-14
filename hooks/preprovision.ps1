#!/usr/bin/env pwsh
# azd preprovision hook — fail closed unless authentication is configured.
# Values come from the azd environment (azd exports them to hooks). Secret values are never printed.
$ErrorActionPreference = 'Stop'

function Get-AzdValue([string]$name) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = (azd env get-value $name 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { $value = '' }
    }
    return $value
}

$insecure = (Get-AzdValue 'ALLOW_INSECURE_NO_AUTH').ToLowerInvariant() -eq 'true'
$required = @('AUTH_CLIENT_ID', 'AUTH_CLIENT_SECRET', 'ALLOWED_OBJECT_IDS')
$missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace((Get-AzdValue $_)) })

if ($missing.Count -gt 0) {
    if ($insecure) {
        Write-Host ''
        Write-Host '############################################################################' -ForegroundColor Red
        Write-Host '#  WARNING: ALLOW_INSECURE_NO_AUTH=true — provisioning WITHOUT Easy Auth.' -ForegroundColor Red
        Write-Host "#  Missing: $($missing -join ', ')" -ForegroundColor Red
        Write-Host '#  The app will be public and read-only: nobody can sign in or act as admin.' -ForegroundColor Red
        Write-Host '############################################################################' -ForegroundColor Red
        Write-Host ''
        exit 0
    }
    Write-Host "ERROR: refusing to provision without authentication. Missing azd env values: $($missing -join ', ')" -ForegroundColor Red
    Write-Host 'Set them with: azd env set AUTH_CLIENT_ID <app-id>; azd env set AUTH_CLIENT_SECRET <secret>; azd env set ALLOWED_OBJECT_IDS <oid1,oid2>' -ForegroundColor Yellow
    Write-Host 'Or, for a throw-away public read-only demo only: azd env set ALLOW_INSECURE_NO_AUTH true' -ForegroundColor Yellow
    exit 1
}

$guid = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
$bad = @()
if ((Get-AzdValue 'AUTH_CLIENT_ID').Trim() -notmatch $guid) { $bad += 'AUTH_CLIENT_ID' }
$tenant = Get-AzdValue 'AUTH_TENANT_ID'
if (-not [string]::IsNullOrWhiteSpace($tenant) -and $tenant.Trim() -notmatch $guid) { $bad += 'AUTH_TENANT_ID' }
foreach ($oid in (Get-AzdValue 'ALLOWED_OBJECT_IDS').Split(',')) {
    if ($oid.Trim() -notmatch $guid) { $bad += 'ALLOWED_OBJECT_IDS'; break }
}
if ($bad.Count -gt 0) {
    Write-Host "ERROR: expected GUID value(s) in: $($bad -join ', ') (ALLOWED_OBJECT_IDS is a comma-separated list of GUIDs)" -ForegroundColor Red
    exit 1
}

Write-Host 'preprovision: Easy Auth configuration present (AUTH_CLIENT_ID, AUTH_CLIENT_SECRET, ALLOWED_OBJECT_IDS).' -ForegroundColor Green
exit 0
