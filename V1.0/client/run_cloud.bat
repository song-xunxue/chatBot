@echo off
chcp 65001 >nul
REM MyChat 客户端 - 一键连接云服务器试用
REM 作者: 李文煜  日期: 2026-06-24
REM 双击运行；含 access_token
set CLIENT_SERVER_URL=http://43.140.219.99:8000
set CLIENT_WS_URL=ws://43.140.219.99:8000/ws
set ACCESS_TOKEN=1bd86c187a76d738f023b8f9680d7525
C:\Users\26904\anaconda3\envs\mychat\python.exe "%~dp0app\main.py"
pause
