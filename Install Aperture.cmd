@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Install Aperture

if "%~1"=="" (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_aperture_frontend.ps1"
) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_aperture_frontend.ps1" -InstallerArguments %*
)
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
    echo.
    echo ============================================================
    echo Installation failed with exit code %RESULT%.
    echo Review the messages above. No Aperture Library is removed.
    echo ============================================================
    echo.
    pause
    exit /b %RESULT%
)

if /I not "%~1"=="/silent" (
    echo.
    pause
)
exit /b 0
