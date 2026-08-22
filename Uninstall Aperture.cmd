@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Uninstall Aperture

echo.
echo ============================================================
echo                   Uninstall Aperture
echo ============================================================
echo.
echo Aperture libraries, photographs, backups, and exports are never removed.
echo Close Aperture and Aperture Maintenance Center before continuing.
echo.
echo  1. Remove Aperture package only
echo  2. Remove Aperture and the complete Conda environment
echo  3. Full reset: environment, application data, and install reports
echo  4. Cancel
echo.
set /p "CHOICE=Choose 1, 2, 3, or 4: "

if "%CHOICE%"=="1" goto package_only
if "%CHOICE%"=="2" goto remove_environment
if "%CHOICE%"=="3" goto full_reset
if "%CHOICE%"=="4" goto cancelled

echo Invalid choice.
pause
exit /b 2

:package_only
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0scripts\uninstall_windows.ps1' -Confirm:$false"
goto finished

:remove_environment
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0scripts\uninstall_windows.ps1' -RemoveEnvironment -StopRunningProcesses -Confirm:$false"
goto finished

:full_reset
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0scripts\uninstall_windows.ps1' -RemoveEnvironment -StopRunningProcesses -RemoveApplicationData -RemoveInstallationReports -Confirm:$false"
goto finished

:cancelled
echo Uninstall cancelled.
exit /b 0

:finished
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
    echo.
    echo Uninstall failed with exit code %RESULT%.
    pause
    exit /b %RESULT%
)

echo.
echo Uninstall completed successfully.
echo Your libraries and photographs were not removed.
echo.
pause
exit /b 0
