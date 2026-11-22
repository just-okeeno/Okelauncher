#Requires -Version 5.1
<#
.SYNOPSIS
  Build Oke Launcher - futuristic movie/TV launcher (Win32 + CMake).
.EXAMPLE
  .\build.ps1                 # configure + build Release
  .\build.ps1 -Run            # build and launch
  .\build.ps1 -Config Debug   # debug build
  .\build.ps1 -Clean -Build   # from scratch
  .\build.ps1 -Package        # zip the exe into dist\OkeLauncher.zip
  .\build.ps1 -GenerateIcon   # regenerate resources\app.ico (needs Python 3)
#>
[CmdletBinding()]
param(
    [ValidateSet('Release', 'Debug')]
    [string]$Config = 'Release',
    [switch]$Clean,
    [switch]$Build,
    [switch]$Run,
    [switch]$Package,
    [switch]$GenerateIcon
)

$ErrorActionPreference = 'Stop'
$Root     = $PSScriptRoot
$BuildDir = Join-Path $Root 'build'
$DistDir  = Join-Path $Root 'dist'

if (-not $Clean -and -not $Build -and -not $Run -and -not $Package -and -not $GenerateIcon) {
    $Build = $true
}

if ($GenerateIcon) {
    Write-Host '>> Generating icon...' -ForegroundColor Cyan
    python (Join-Path $Root 'tools\make_icon.py')
}

if ($Clean -and (Test-Path $BuildDir)) {
    Write-Host '>> Cleaning build directory...' -ForegroundColor Cyan
    Remove-Item $BuildDir -Recurse -Force
}

if ($Build) {
    Write-Host ">> Configuring ($Config)..." -ForegroundColor Cyan
    cmake -S $Root -B $BuildDir
    if ($LASTEXITCODE -ne 0) { throw "CMake configure failed ($LASTEXITCODE)" }

    Write-Host '>> Building...' -ForegroundColor Cyan
    cmake --build $BuildDir --config $Config --parallel
    if ($LASTEXITCODE -ne 0) { throw "Build failed ($LASTEXITCODE)" }

    $Exe = Get-ChildItem $BuildDir -Recurse -Filter 'OkeLauncher.exe' |
        Where-Object { $_.FullName -notmatch 'CMakeFiles' } |
        Select-Object -First 1
    if (-not $Exe) { throw 'OkeLauncher.exe was not produced.' }
    Write-Host ">> OK: $($Exe.FullName)" -ForegroundColor Green
}

if ($Run) {
    if (-not $Exe) {
        $Exe = Get-ChildItem $BuildDir -Recurse -Filter 'OkeLauncher.exe' |
            Where-Object { $_.FullName -notmatch 'CMakeFiles' } |
            Select-Object -First 1
    }
    if (-not $Exe) { throw 'Build first (-Build) - no OkeLauncher.exe found.' }
    Write-Host '>> Launching...' -ForegroundColor Cyan
    Start-Process $Exe.FullName
}

if ($Package) {
    if (-not $Exe) {
        $Exe = Get-ChildItem $BuildDir -Recurse -Filter 'OkeLauncher.exe' |
            Where-Object { $_.FullName -notmatch 'CMakeFiles' } |
            Select-Object -First 1
    }
    if (-not $Exe) { throw 'Build first (-Build) - no OkeLauncher.exe found.' }
    New-Item $DistDir -ItemType Directory -Force | Out-Null
    $Zip = Join-Path $DistDir 'OkeLauncher.zip'
    if (Test-Path $Zip) { Remove-Item $Zip -Force }
    Compress-Archive -Path $Exe.FullName -DestinationPath $Zip
    Write-Host ">> Packaged: $Zip" -ForegroundColor Green
}
