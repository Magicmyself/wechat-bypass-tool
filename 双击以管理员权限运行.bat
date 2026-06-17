@echo off
title 微信消息极速秒回助手 - 管理员启动器

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
echo         微信消息极速秒回助手 - 启动中 (UIA 优化版)
echo ----------------------------------------------------
echo.
python wechat_gui_wxauto.py
if %errorLevel% neq 0 (
    echo.
    echo [错误] 脚本异常退出，请检查 Python 环境或微信是否运行！
)
echo.
pause
