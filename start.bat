@echo off
title Gesture PPT Controller
color 0B
echo.
echo  =====================================================
echo   GESTURE PPT CONTROLLER
echo  =====================================================
echo.

REM Kill any leftover Python servers on port 5000
FOR /F "tokens=5" %%a IN ('netstat -aon ^| findstr ":5000" 2^>nul') DO (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 >nul

echo  [INFO] Starting server...
echo.
echo  =========================================
echo   Open your browser at:
echo   --->  http://localhost:5000  <---
echo  =========================================
echo.
echo  Press Ctrl+C to stop the server.
echo.

start "" "http://localhost:5000"

python app.py
pause
