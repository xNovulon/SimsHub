# Builds "Sims Hub.exe" (a plain folder with .NET next to it) in program\, next to speedkit\, for trying out
# changes on this PC. Everyone else gets it from GitHub: .github\workflows\build-apps.yml builds and publishes it on
# every change, and each installed copy picks it up by itself. Close the Hub first (its files can't be replaced
# while it runs).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$out = Join-Path $root 'program'
dotnet publish (Join-Path $here 'SimsHub.csproj') -c Release -o $out -nologo -v:minimal
if ($LASTEXITCODE -ne 0) { throw "build failed" }
Write-Host "Built $(Join-Path $out 'Sims Hub.exe')"
