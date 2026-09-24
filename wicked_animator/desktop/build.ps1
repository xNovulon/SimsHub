# Builds "Wicked Animator.exe" (with .NET inside it) next to web\ and backend\, for trying out changes on this PC.
# Everyone else gets it from GitHub: .github\workflows\build-apps.yml builds and publishes it on every change, and each
# installed copy picks it up by itself. Close the app first (the exe can't be replaced while it runs).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$out = Join-Path $here 'bin\publish'
dotnet publish (Join-Path $here 'WickedAnimator.csproj') -c Release -o $out -nologo -v:minimal
if ($LASTEXITCODE -ne 0) { throw "build failed" }
$exe = Join-Path $root 'Wicked Animator.exe'
Copy-Item (Join-Path $out 'Wicked Animator.exe') $exe -Force
Write-Host "Built $exe"
