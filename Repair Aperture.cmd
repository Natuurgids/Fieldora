@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Repair Aperture

echo.
echo ============================================================
echo                    Repair Aperture
echo ============================================================
echo.
echo This repairs Windows shortcuts, PATH integration, and registration.
echo It does not remove libraries, photographs, backups, or exports.
echo Close Aperture before continuing.
echo.

set "DEFAULT_LIBRARY="
set /p "DEFAULT_LIBRARY=Default library folder (leave blank to keep unchanged): "

if defined DEFAULT_LIBRARY (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\repair_windows_integration.ps1" -DefaultLibrary "%DEFAULT_LIBRARY%"
) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\repair_windows_integration.ps1"
)

set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
    echo.
    echo Repair failed with exit code %RESULT%.
    pause
    exit /b %RESULT%
)

echo.
echo Repair completed successfully.
echo.
pause
exit /b 0
