# Runs Sims 4 Studio's own PackageMergeUtility merge path (as PackageMergeWindow does) on scratch files only.
param([string]$Dir)
$s4s = 'C:\Program Files (x86)\Sims 4 Studio'
[AppDomain]::CurrentDomain.add_AssemblyResolve({ param($s, $e)
  $n = (New-Object Reflection.AssemblyName($e.Name)).Name
  $p = Join-Path $s4s ($n + '.dll')
  if (Test-Path $p) { return [Reflection.Assembly]::LoadFrom($p) } return $null })
$asm = [Reflection.Assembly]::LoadFrom((Join-Path $s4s 'S4Studio.dll'))
$pt = $asm.GetType('S4Studio.Data.IO.Package.DBPFPackage', $true)
$pt.GetConstructors() | ForEach-Object { 'ctor(' + (($_.GetParameters() | ForEach-Object { $_.ParameterType.Name + ' ' + $_.Name }) -join ', ') + ')' }
$t = $asm.GetType('S4Studio.Data.IO.Package.PackageMergeUtility', $true)
$out = Join-Path $Dir 'merged2.package'
$mu = [Activator]::CreateInstance($t, @([string]$out))
$root = $t.GetProperty('Manifest').GetValue($mu).Root
$ctor = $pt.GetConstructors() | Where-Object { $_.GetParameters().Count -eq 5 -and $_.GetParameters()[0].ParameterType -eq [string] } | Select-Object -First 1
foreach ($f in @('merged.package', 'src2.package')) {
  $p = $ctor.Invoke(@([string](Join-Path $Dir $f), $true, $null, $null, $null))
  $t.GetMethod('AddPackage').Invoke($mu, @($root, $p))
  $p.Dispose()
}
$t.GetMethod('Defragment').Invoke($mu, @())
"merged"
