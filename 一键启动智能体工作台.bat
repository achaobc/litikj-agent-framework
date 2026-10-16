@echo off
chcp 65001 >nul
title 立体空间智能体系统 (Litikj Agent OS)
cd /d "%~dp0"

echo ========================================================
echo   🪐 正在启动 立体空间智能体系统 (Litikj Agent OS) ...
echo ========================================================
echo.

if exist "立体空间智能体系统.exe" (
    start "" "立体空间智能体系统.exe"
    exit /b 0
)

if exist "runtime\python.exe" (
    runtime\python.exe run.py
    pause
    exit /b 0
)

if exist "run.py" (
    python run.py
    pause
    exit /b 0
)

echo [ERROR] 未找到桌面主程序或 Python 运行入口！
pause
