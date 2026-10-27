@echo off
rem napcat-local.cmd — 双击无窗口启动本栈的 NapCat（等价于 powershell -File start_napcat.ps1）
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_napcat.ps1"
if errorlevel 1 pause
