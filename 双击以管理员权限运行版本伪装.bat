@echo off
title 微信版本伪装启动器 - 管理员权限

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :run
) else (
    echo 正在请求管理员权限...
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b
)

:run
cd /d "%~dp0"
echo ----------------------------------------------------
echo         微信版本伪装器 - 运行中 (3.9.12.17 -> 3.9.15.15)
echo ----------------------------------------------------
echo.
python bypass_wechat_version.py
echo.
pause
