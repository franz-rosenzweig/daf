# Builds Daf for Windows on this PC, as the Windows workflow does on GitHub's: the tests,
# the icon, the app, the self-test, and with Inno Setup installed the installer.
# Needs the .NET 10 SDK, and for the self-test Python 3.12 with Daf's requirements.
#
#   windows\build.ps1 [-Version 0.1.0] [-SkipSelfTest]
#
# The app ends up in build\Daf (it runs from there as it is); the installer in build\out.
param([string]$Version = "", [switch]$SkipSelfTest)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot)

if (-not $Version) { $Version = ([xml](Get-Content windows\Daf\Daf.csproj)).Project.PropertyGroup.Version | Where-Object { $_ } | Select-Object -First 1 }

dotnet run --project windows\Tests -c Release
if ($LASTEXITCODE) { throw "the tests failed" }

powershell -NoProfile -File windows\tools\make-icon.ps1
Remove-Item -Recurse -Force build\Daf -ErrorAction SilentlyContinue
dotnet publish windows\Daf\Daf.csproj -c Release -r win-x64 -p:Platform=x64 -p:Version=$Version -o build\Daf
if ($LASTEXITCODE) { throw "the app didn't build" }

if (-not $SkipSelfTest) {
    & windows\selftest.ps1 -App build\Daf\Daf.exe
    if ($LASTEXITCODE) { throw "the self-test failed" }
}

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc /Q "/DVersion=$Version" "/DSource=$PWD\build\Daf" windows\installer.iss
    if ($LASTEXITCODE) { throw "the installer didn't build" }
    "made build\out\Daf-$Version-Setup.exe"
} else {
    "no Inno Setup: build\Daf is the app, without an installer"
}
