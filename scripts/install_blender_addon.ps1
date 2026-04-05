param(
    [ValidateSet('install','relink','uninstall')]
    [string]$Action = 'install',
    [string]$BlenderVersion
)

$AddonName = 'vertex_color_tool'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir '..')
$SourceDir = Join-Path $RepoRoot $AddonName

function Get-BlenderVersion {
    param([string]$Explicit)

    if ($Explicit) {
        return $Explicit
    }

    if ($env:BLENDER_VERSION) {
        return $env:BLENDER_VERSION
    }

    $blenderRoot = Join-Path $env:APPDATA 'Blender Foundation\Blender'
    if (-not (Test-Path $blenderRoot)) {
        Write-Error "Could not find $blenderRoot"
        exit 1
    }

    $dirs = Get-ChildItem -Path $blenderRoot -Directory
    if (-not $dirs) {
        Write-Error "No Blender versions found in $blenderRoot"
        exit 1
    }

    $sorted = $dirs | Sort-Object -Property @{ Expression = {
        $name = $_.Name
        try { [version]$name } catch { [version]'0.0' }
    }}

    return $sorted[-1].Name
}

$BlenderVersionDetected = Get-BlenderVersion -Explicit $BlenderVersion
$TargetDir = Join-Path $env:APPDATA ("Blender Foundation\Blender\{0}\scripts\addons" -f $BlenderVersionDetected)
$TargetLink = Join-Path $TargetDir $AddonName

if (-not (Test-Path $SourceDir)) {
    Write-Error "Expected add-on package at $SourceDir"
    exit 1
}

switch ($Action) {
    'install' {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
        if (Test-Path $TargetLink) {
            Write-Error "Add-on already exists at $TargetLink"
            Write-Error "Use '.\\install_blender_addon.ps1 relink' to replace it."
            exit 1
        }
        New-Item -ItemType Junction -Path $TargetLink -Target $SourceDir | Out-Null
        Write-Host "Installed $AddonName into Blender $BlenderVersionDetected"
        Write-Host "Path: $TargetLink"
    }
    'relink' {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
        if (Test-Path $TargetLink) {
            Remove-Item -Recurse -Force $TargetLink
        }
        New-Item -ItemType Junction -Path $TargetLink -Target $SourceDir | Out-Null
        Write-Host "Re-linked $AddonName into Blender $BlenderVersionDetected"
        Write-Host "Path: $TargetLink"
    }
    'uninstall' {
        if (Test-Path $TargetLink) {
            Remove-Item -Recurse -Force $TargetLink
            Write-Host "Removed $AddonName from Blender $BlenderVersionDetected"
            Write-Host "Path: $TargetLink"
        } else {
            Write-Host "Nothing to remove at $TargetLink"
        }
    }
}
