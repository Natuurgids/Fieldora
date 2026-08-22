@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\cleanup_legacy_data.ps1" %*
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo Cleanup utility exited with code %EXITCODE%.
pause
exit /b %EXITCODE%
