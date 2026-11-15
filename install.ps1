# install.ps1 - msg-optimizer plugin installer for Windows
# Installs msg-optimizer into both Hermes plugin directories and creates profile symlinks.
#
# Usage:
#   .\install.ps1 [-Profile <name>] [-AllProfiles] [-DryRun]
#
# Dual install paths:
#   1. C:\Users\<user>\AppData\Local\hermes\plugins\msg-optimizer\
#   2. $HOME\.hermes\plugins\msg-optimizer\
param(
    [string]$Profile = "",
    [switch]$AllProfiles,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$PluginName = "msg-optimizer"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== msg-optimizer installer (Windows) ===" -ForegroundColor Cyan

$ProfilesBase = "C:\Users\$env:USERNAME\AppData\Local\hermes"
$WinPlugins   = Join-Path $ProfilesBase "plugins"
$HomePlugins  = Join-Path $env:USERPROFILE ".hermes\plugins"

$Targets = @(
    @{ Path=$WinPlugins;   Label="AppData (Windows native)" },
    @{ Path=$HomePlugins;  Label="$HOME\.hermes" }
)

Write-Host "[1/3] Installing plugin source..." -ForegroundColor Yellow
foreach ($t in $Targets) {{
    $dest = Join-Path $t.Path $PluginName
    if ($DryRun) {{
        Write-Host "  [dry-run] $dest"
    }} else {{
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Get-ChildItem $ScriptDir -Exclude '.git' -Recurse -File | ForEach-Object {{
            $rel = $_.FullName.Substring($ScriptDir.Length).Replace('\', '/')
            $out = Join-Path $dest $rel
            New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
            Copy-Item $_.FullName -Destination $out -Force
        }}
        if (-not (Test-Path (Join-Path $dest '.git'))) {{
            if (Test-Path (Join-Path $ScriptDir '.git')) {{
                Copy-Item (Join-Path $ScriptDir '.git') (Join-Path $dest '.git') -Recurse -Force
            }}
        }}
        Write-Host "  [ok] $($t.Label): $dest"
    }}
}}

Write-Host "[2/3] Setting up profile symlinks..." -ForegroundColor Yellow
$AllProfs = if ($Profile) {{ @($Profile) }} else {{
    Get-ChildItem "$ProfilesBase\profiles" -Directory `
        | Where-Object {{ $_.Name -notmatch '^\.' }} `
        | ForEach-Object {{ $_.Name }}
}}

foreach ($prof in $AllProfs) {{
    $cfg = Join-Path "$ProfilesBase\profiles\$prof" "config.yaml"
    $has = $false
    if (Test-Path $cfg) {{
        $has = (Get-Content $cfg -Raw) -match '-\s*msg-optimizer\s*$'
    }}
    if (-not $has) {{ continue }}
    $link = Join-Path "$ProfilesBase\profiles\$prof\plugins" $PluginName
    $src  = Join-Path $WinPlugins $PluginName
    if ($DryRun) {{
        Write-Host "  [dry-run] $link -> $src"
    }} else {{
        if (Test-Path $link) {{
            if ((Get-Item $link).LinkType -eq "Symlink") {{ Remove-Item $link -Force }}
            elseif ((Get-Item $link).PSIsContainer) {{ Remove-Item $link -Recurse -Force }}
            else {{ Remove-Item $link -Force }}
        }}
        cmd /c "mklink /D `"$link`" `"$src`"" | Out-Null
        Write-Host "  [ok] $prof/plugins/$PluginName -> $src"
    }}
}}

Write-Host "[3/3] Verification..." -ForegroundColor Yellow
$n = 0
foreach ($t in $Targets) {{
    if (Test-Path (Join-Path $t.Path "$PluginName\__init__.py")) {{ $n++ }}
}}
Write-Host "  installed to $n location(s)"
Write-Host "Done. Restart the Hermes gateway." -ForegroundColor Green
