# Builds "Wicked Animator.exe" (next to web\ and backend\) and points the Desktop and Start Menu shortcuts at it.
# Works offline: the WebView2 parts are in lib\. Close the app first (the exe can't be replaced while it runs).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$offline = Join-Path $here 'obj\offline-feed'
New-Item -ItemType Directory -Force $offline | Out-Null
$out = Join-Path $here 'bin\publish'
dotnet publish (Join-Path $here 'WickedAnimator.csproj') -c Release -o $out --source $offline -nologo -v:minimal
if ($LASTEXITCODE -ne 0) { throw "build failed" }
$exe = Join-Path $root 'Wicked Animator.exe'
Copy-Item (Join-Path $out 'Wicked Animator.exe') $exe -Force
$ws = New-Object -ComObject WScript.Shell
$links = @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Wicked Animator.lnk'),
           (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Novulon's Wicked Animator.lnk"))
foreach ($p in $links) {
  $l = $ws.CreateShortcut($p)
  $l.TargetPath = $exe; $l.Arguments = ''; $l.WorkingDirectory = $root; $l.IconLocation = "$exe,0"
  $l.WindowStyle = 1                     # a normal window (never "Run: Minimized")
  $l.Description = "Novulon's Wicked Animator - make WickedWhims animations without Blender"
  $l.Save()
}
Write-Host "Built $exe"
