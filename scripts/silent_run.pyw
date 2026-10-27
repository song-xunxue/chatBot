# -*- coding: utf-8 -*-
"""
计划任务无窗垫片:pythonw(GUI 子系统,自身无控制台)以 CREATE_NO_WINDOW 起 powershell 脚本。

为什么需要它:powershell.exe -WindowStyle Hidden 是"先创建控制台窗口再隐藏",
conhost 委派下会闪蓝窗;经 pythonw + CREATE_NO_WINDOW,子进程控制台从创建起就不可见,
零闪窗。用法(计划任务 Action):
  Execute   = C:\\Users\\26904\\anaconda3\\envs\\mychat\\pythonw.exe
  Arguments = "D:\\code\\Git_Local\\ChatBot\\scripts\\silent_run.pyw" "<目标.ps1>"

作者: 李文煜
日期: 2026-10-27
"""
import subprocess
import sys
from datetime import datetime

LOG = r"D:\code\Git_Local\ChatBot\logs\silent_run.log"


def _log(msg: str) -> None:
    # pythonw 无控制台,异常只能落文件(正常路径不记,防日志膨胀)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) < 2:
        _log("缺少参数:用法 silent_run.pyw <目标.ps1>")
        return 2
    script = sys.argv[1]
    try:
        # CREATE_NO_WINDOW(0x08000000):子控制台进程新建不可见控制台(区别于先建后隐)
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", script],
            creationflags=0x08000000, timeout=3600,
        )
        return proc.returncode
    except Exception as e:
        _log(f"运行失败 {script}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
