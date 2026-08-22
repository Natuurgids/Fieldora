@echo off
set "LAUNCHER=%LOCALAPPDATA%\NatureAI\NatureAI Next\Launchers\start_natureai_next_debug.ps1"
if not exist "%LAUNCHER%" (
  echo NatureAI Next launchers are not installed.
  echo Run scripts\install_windows.ps1 first.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%"
