# Runs Sims 4 Studio's own PackageMergeUtility.Unmerge on a scratch COPY (research folder only).
param([string]$In, [string]$Out)
$s4s = 'C:\Program Files (x86)\Sims 4 Studio'
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s, $e)
  $n = (New-Object Reflection.AssemblyName($e.Name)).Name
  $p = Join-Path $s4s ($n + '.dll')
  if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) } return $null })
$asm = [Reflection.Assembly]::LoadFrom((Join-Path $s4s 'S4Studio.dll'))
$t = $asm.GetType('S4Studio.Data.IO.Package.PackageMergeUtility', $true)
$mu = [Activator]::CreateInstance($t, @([string]$In))
$pkg = $t.GetProperty('Package').GetValue($mu)
"IsMerged=" + $pkg.IsMerged
$man = $t.GetProperty('Manifest').GetValue($mu)
"Manifest version=" + $man.Version + " packages=" + $man.PackageCount
$t.GetMethod('Unmerge').Invoke($mu, @([string]$Out))
"done"
