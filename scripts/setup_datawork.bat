@echo off
setlocal
cd /d "%~dp0\.."
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 scripts\setup_datawork.py %*
  exit /b %errorlevel%
)
python scripts\setup_datawork.py %*
exit /b %errorlevel%
