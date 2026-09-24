# Desktop helper for checking the game: screenshots, clicks, keys.
#   desk.ps1 shot <file> [scalePercent]
#   desk.ps1 click <x> <y>
#   desk.ps1 move <x> <y>
#   desk.ps1 keys <sendkeys-string>        (System.Windows.Forms.SendKeys syntax, e.g. "^+c" = Ctrl+Shift+C)
#   desk.ps1 type <text>
#   desk.ps1 focus                         (bring The Sims 4 to the front)
param([string]$action, [string]$a1, [string]$a2)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class U32 {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[U32]::SetProcessDPIAware() | Out-Null

function Focus-Game {
  $p = Get-Process TS4_x64 -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($p -and $p.MainWindowHandle -ne 0) { [U32]::ShowWindow($p.MainWindowHandle, 9) | Out-Null; [U32]::SetForegroundWindow($p.MainWindowHandle) | Out-Null; Start-Sleep -Milliseconds 300; return $true }
  return $false
}

switch ($action) {
  'shot' {
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $scale = if ($a2) { [double]$a2 / 100 } else { 0.6 }
    $w = [int]($b.Width * $scale); $h = [int]($b.Height * $scale)
    $small = New-Object System.Drawing.Bitmap $w, $h
    $g2 = [System.Drawing.Graphics]::FromImage($small)
    $g2.InterpolationMode = 'HighQualityBicubic'
    $g2.DrawImage($bmp, 0, 0, $w, $h)
    $small.Save($a1, [System.Drawing.Imaging.ImageFormat]::Png)
    "saved $a1 ($w x $h, full $($b.Width) x $($b.Height))"
  }
  'click' {
    Focus-Game | Out-Null
    [U32]::SetCursorPos([int]$a1, [int]$a2) | Out-Null; Start-Sleep -Milliseconds 120
    [U32]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
    [U32]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    "clicked $a1,$a2"
  }
  'move' { [U32]::SetCursorPos([int]$a1, [int]$a2) | Out-Null; "moved" }
  'keys' { Focus-Game | Out-Null; [System.Windows.Forms.SendKeys]::SendWait($a1); "sent keys $a1" }
  'type' { Focus-Game | Out-Null; foreach ($ch in $a1.ToCharArray()) { $s = [string]$ch; if ('+^%~(){}[]'.Contains($s)) { $s = '{' + $s + '}' }; [System.Windows.Forms.SendKeys]::SendWait($s); Start-Sleep -Milliseconds 25 }; "typed $a1" }
  'cheat' {
    # Ctrl+Shift+C opens the cheat console; hold the keys with keybd_event (SendKeys chords are unreliable in games)
    Focus-Game | Out-Null
    [U32]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero); [U32]::keybd_event(0x10, 0, 0, [UIntPtr]::Zero)
    [U32]::keybd_event(0x43, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 80
    [U32]::keybd_event(0x43, 0, 2, [UIntPtr]::Zero); [U32]::keybd_event(0x10, 0, 2, [UIntPtr]::Zero); [U32]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
    "cheat console toggled"
  }
  'enter' { Focus-Game | Out-Null; [U32]::keybd_event(0x0D, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 50; [U32]::keybd_event(0x0D, 0, 2, [UIntPtr]::Zero); "enter" }
  'focus' { if (Focus-Game) { "focused" } else { "no game window" } }
  'waitload' {
    # wait until the plain blue loading screen is gone (or timeout seconds), sampling a few pixels
    $limit = if ($a1) { [int]$a1 } else { 240 }
    $t0 = Get-Date
    $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $seenLoading = $false
    while (((Get-Date) - $t0).TotalSeconds -lt $limit) {
      $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
      $blue = 0
      foreach ($pt in @(@(150, 900), @(1750, 300), @(300, 250), @(1700, 1000))) {
        $c = $bmp.GetPixel($pt[0], $pt[1])
        if ([Math]::Abs($c.R - 37) -lt 12 -and [Math]::Abs($c.G - 55) -lt 12 -and [Math]::Abs($c.B - 96) -lt 14) { $blue++ }
      }
      $g.Dispose(); $bmp.Dispose()
      if ($blue -ge 3) { $seenLoading = $true } elseif ($seenLoading -or ((Get-Date) - $t0).TotalSeconds -gt 8) { "loaded after $([int]((Get-Date) - $t0).TotalSeconds) s"; return }
      Start-Sleep -Milliseconds 1500
    }
    "timeout after $limit s"
  }
}
