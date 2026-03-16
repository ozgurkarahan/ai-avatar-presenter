[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Hostname
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Path $PSScriptRoot -Parent
$teamsAssetsPath = Join-Path $projectRoot 'demos\frontend\public\teams'
$manifestPath = Join-Path $teamsAssetsPath 'manifest.json'
$colorIconPath = Join-Path $teamsAssetsPath 'color.png'
$outlineIconPath = Join-Path $teamsAssetsPath 'outline.png'
$outputZipPath = Join-Path $projectRoot 'teams-app-package.zip'
$tempPath = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())

try {
    foreach ($requiredPath in @($manifestPath, $colorIconPath, $outlineIconPath)) {
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "Required Teams asset not found: $requiredPath"
        }
    }

    New-Item -ItemType Directory -Path $tempPath -Force | Out-Null

    $manifestContent = [System.IO.File]::ReadAllText($manifestPath, [System.Text.Encoding]::UTF8)
    $packagedManifest = $manifestContent.Replace('{{TEAMS_APP_HOSTNAME}}', $Hostname)
    [System.IO.File]::WriteAllText((Join-Path $tempPath 'manifest.json'), $packagedManifest, [System.Text.Encoding]::UTF8)

    Copy-Item -LiteralPath $colorIconPath -Destination (Join-Path $tempPath 'color.png')
    Copy-Item -LiteralPath $outlineIconPath -Destination (Join-Path $tempPath 'outline.png')

    if (Test-Path -LiteralPath $outputZipPath) {
        Remove-Item -LiteralPath $outputZipPath -Force
    }

    Compress-Archive -Path (Join-Path $tempPath '*') -DestinationPath $outputZipPath -Force
    Write-Host "Created Teams app package at $outputZipPath"
}
finally {
    if (Test-Path -LiteralPath $tempPath) {
        Remove-Item -LiteralPath $tempPath -Recurse -Force
    }
}
