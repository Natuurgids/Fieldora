@echo off
set "PYTHON=%USERPROFILE%\miniconda3\envs\natureai-next\python.exe"
if not exist "%PYTHON%" set "PYTHON=%USERPROFILE%\anaconda3\envs\natureai-next\python.exe"
if not exist "%PYTHON%" (
  echo The natureai-next Python environment was not found.
  pause
  exit /b 1
)
"%PYTHON%" "%~dp0verify_install.py" --require-gui --require-ai
pause
