@echo off
REM [Dafeiyu] NapCat launcher - 2026-10-26 起改为转发 scripts\start-napcat.ps1
REM (原直拉写法无单实例判断,双击多次=多开;ps1 版有进程判据+互斥锁+无窗)
REM author: Li Wenyu / 2026-10-26
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\code\Git_Local\ChatBot\Vdafeiyu\scripts\start-napcat.ps1"
