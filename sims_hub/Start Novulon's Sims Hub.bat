@echo off
title Novulon's Sims Hub
cd /d "%~dp0"

rem Fallback launcher. The Desktop shortcut runs "pythonw -m speedkit.hub --open", which shows no console at all.
rem Start the Hub's local server (once), then open it in its own window.
set "URL=http://127.0.0.1:8766/"
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8766/api/ping) | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 goto open

where python >nul 2>nul
if errorlevel 1 goto nopython
start "Novulon's Sims Hub server" /min python -m speedkit.hub
echo Starting Novulon's Sims Hub...
powershell -NoProfile -Command "for ($i=0; $i -lt 60; $i++) { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8766/api/ping) | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; exit 1"
if errorlevel 1 goto nostart

:open
rem Chrome, then Edge (every Windows 10/11 PC has it), then the default browser.
set "BROWSER="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "BROWSER=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if defined BROWSER goto app
start "" %URL%
exit /b 0

:app
rem The Hub's own browser profile, the same one the shortcut uses: its own taskbar entry, and it keeps its size.
set "PROFILE=%LOCALAPPDATA%\NovulonSimsHub\browser"
set "MAX="
if not exist "%PROFILE%" set "MAX=--start-maximized"
start "" "%BROWSER%" --app=%URL% --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check %MAX%
exit /b 0

:nopython
echo.
echo Novulon's Sims Hub needs Python, and it isn't on this PC yet.
echo Install Python 3 from https://www.python.org/downloads/ and then open the Hub again.
echo.
pause
exit /b 1

:nostart
echo.
echo Novulon's Sims Hub didn't start. Close this window and try once more.
echo If it still doesn't open, the details are in the "Novulon's Sims Hub server" window on the taskbar.
echo.
pause
exit /b 1
