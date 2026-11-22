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

if (-not $Clean -and -not $Package -and -not $GenerateIcon) {
    $Build = $true
}

function Find-VSInstallPath {
    $vswhere = Join-Path "${env:ProgramFiles(x86)}" 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path $vswhere) {
        $p = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
        if ($p) { return ($p | Select-Object -First 1) }
    }
    return $null
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
    $vsPath = Find-VSInstallPath
    $clEnv  = Get-Command cl.exe -ErrorAction SilentlyContinue
    $genArgs = @()
    if ($vsPath) {
        if ($vsPath -like '*2022*')     { $genArgs = @('-G', 'Visual Studio 17 2022', '-A', 'x64') }
        elseif ($vsPath -like '*2019*') { $genArgs = @('-G', 'Visual Studio 16 2019', '-A', 'x64') }
        elseif ($vsPath -like '*2017*') { $genArgs = @('-G', 'Visual Studio 15 2017', '-A', 'x64') }
        Write-Host ">> Found Visual Studio: $vsPath" -ForegroundColor DarkGray
    }
    elseif (-not $clEnv) {
        throw 'No C++ toolchain found. Install VS 2022 Build Tools with the C++ workload, then run this script again:  winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"'
    }

    Write-Host ">> Configuring ($Config)..." -ForegroundColor Cyan
    cmake -S $Root -B $BuildDir @genArgs
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
