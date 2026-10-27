@echo off
REM 已并入 start-qingxun.ps1(唯一入口:--token local-8091 单源 + redis 先行防 FAKEREDIS)
REM 本文件仅保留兼容旧调用并转发;勿再新增引用(2026-10-26 token 双轨收敛)
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\code\Git_Local\ChatBot\V3.0-local\scripts\start-qingxun.ps1"
