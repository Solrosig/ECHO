@echo off
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 24 LTS, reopen this window, and try again.
  pause
  exit /b 1
)
if not exist data\researcher.json (
  node scripts\setup.mjs
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
node server\start.mjs
pause
