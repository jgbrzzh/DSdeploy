@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Deploy.ps1" -Action Backup
set RESULT=%ERRORLEVEL%
echo.
pause
exit /b %RESULT%
