# Calls Sims 4 Studio 3.2.6.3's own PackageMergeUtility (AddPackage per source, then Defragment) on scratch files only.
param([string]$Dir, [string]$OutName, [string]$Sources)
$s4s = 'C:\Program Files (x86)\Sims 4 Studio'
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s, $e)
  $n = (New-Object Reflection.AssemblyName($e.Name)).Name
  $p = Join-Path $s4s ($n + '.dll')
  if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) } return $null })
$asm = [Reflection.Assembly]::LoadFrom((Join-Path $s4s 'S4Studio.dll'))
$pt = $asm.GetType('S4Studio.Data.IO.Package.DBPFPackage', $true)
$t = $asm.GetType('S4Studio.Data.IO.Package.PackageMergeUtility', $true)
$mu = [Activator]::CreateInstance($t, @([string](Join-Path $Dir $OutName)))
$root = $t.GetProperty('Manifest').GetValue($mu).Root
$ctor = $pt.GetConstructors() | Where-Object { $_.GetParameters().Count -eq 5 -and $_.GetParameters()[0].ParameterType -eq [string] } | Select-Object -First 1
foreach ($f in ($Sources -split ",")) {
  $p = $ctor.Invoke(@([string](Join-Path $Dir $f), $true, $null, $null, $null))
  $t.GetMethod('AddPackage').Invoke($mu, @($root, $p))
  $p.Dispose()
}
$t.GetMethod('Defragment').Invoke($mu, @())
$t.GetProperty('Package').GetValue($mu).Dispose()
"merged"
