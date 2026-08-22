@echo off
set "LAUNCHER=%LOCALAPPDATA%\NatureAI\NatureAI Next\Launchers\start_admin_console.cmd"
if not exist "%LAUNCHER%" (
  echo NatureAI Next launchers are not installed.
  echo Run scripts\install_windows.ps1 first.
  pause
  exit /b 1
)
call "%LAUNCHER%"
