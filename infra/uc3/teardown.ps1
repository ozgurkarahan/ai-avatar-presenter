#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Tears down the UC3 (podcast-style dual-avatar) demo infrastructure.

.DESCRIPTION
    Deletes the entire rg-uc3-podcast resource group asynchronously.
    NOTE: Soft-deleted Cognitive Services accounts may block a future redeploy
    with the same name — purge them via
      az cognitiveservices account purge --location westeurope --resource-group rg-uc3-podcast --name <name>
#>

[CmdletBinding()]
param(
    [string] $ResourceGroupName = 'rg-uc3-podcast',
    [string] $SubscriptionId
)

$ErrorActionPreference = 'Stop'

if ($SubscriptionId) {
    az account set --subscription $SubscriptionId | Out-Null
}

Write-Host "Deleting resource group '$ResourceGroupName' (async)..." -ForegroundColor Yellow
az group delete --name $ResourceGroupName --yes --no-wait

if ($LASTEXITCODE -ne 0) {
    throw "az group delete failed with exit code $LASTEXITCODE"
}

Write-Host "Delete started. Check progress with: az group show --name $ResourceGroupName" -ForegroundColor Green
