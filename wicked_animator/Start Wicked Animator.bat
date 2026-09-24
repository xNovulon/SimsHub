@echo off
rem Opens Novulon's Wicked Animator. The app is "Wicked Animator.exe" (its own window, no console);
rem this file is kept for older shortcuts and the Sims Hub.
cd /d "%~dp0"
if exist "%~dp0Wicked Animator.exe" (
  start "" "%~dp0Wicked Animator.exe"
  exit /b 0
)

rem Fallback without the exe: start the engine quietly, then open it in an app-style browser window.
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8765/api/status) | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  start "" pythonw "%~dp0backend\server.py"
  powershell -NoProfile -Command "for ($i=0; $i -lt 60; $i++) { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8765/api/status) | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; exit 1"
)
set "URL=http://127.0.0.1:8765/"
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" (start "" "%EDGE%" --app=%URL% --start-maximized --force_high_performance_gpu) else (start "" %URL%)
exit /b 0
