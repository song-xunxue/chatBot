"""
GPT-SoVITS + frpc 一键启动器(M-tts,2026-08-08)
双击启动 GAG(GPT-SoVITS api_v2 9880)+ frpc(穿透),状态监控,一键停止。
pyinstaller 打包:pyinstaller --onefile --windowed --name GPT-SoVITS启动器 tts_launcher.py

作者: 李文煜
日期: 2026-08-08
"""
import os
import socket
import subprocess
import sys

import tkinter as tk
from tkinter import ttk

# 路径(改位置改这里)
# BASE = 启动器所在目录(exe 运行时取 sys.executable 目录;源码跑取脚本目录),frp 跟启动器同级
BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
GAG = r"E:\GPT-SoVITS\GAG v0.4.3.exe"   # GAG(GPT-SoVITS)启动器,E 盘固定位置
FRPC = os.path.join(BASE, "frp", "frp_0.70.0_windows_amd64", "frpc.exe")      # frp 跟启动器同级 frp\ 下
FRPC_CFG = os.path.join(BASE, "frp", "frp_0.70.0_windows_amd64", "frpc.toml")
API_PORT = 9880


def _port_open(port: int) -> bool:
    """检测本地端口是否在监听(GAG api_v2 起来的标志)"""
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        return True
    except OSError:
        return False


class Launcher:
    def __init__(self, root):
        self.root = root
        self.gag = None
        self.frpc = None
        root.title("GPT-SoVITS 启动器")
        root.geometry("340x220")
        root.resizable(False, False)

        ttk.Label(root, text="GPT-SoVITS(GAG) + frpc 一键启动", font=("", 10, "bold")).pack(pady=8)
        self.btn = ttk.Button(root, text="▶ 启动", command=self.toggle, width=18)
        self.btn.pack(pady=6)
        self.status = tk.Label(root, text="状态:未启动", justify="left", font=("Consolas", 9))
        self.status.pack(pady=8)
        ttk.Label(root, text="关此窗口=停止两者\n开机自启:把 exe 放「启动」文件夹", foreground="gray").pack(side="bottom", pady=6)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._poll()

    def toggle(self):
        if self.gag or self.frpc:
            self.stop()
        else:
            self.start()

    def start(self):
        # GAG(GUI exe,autostart_api=true 自动起 api_v2);frpc(命令行,隐藏控制台窗口)
        try:
            self.gag = subprocess.Popen([GAG])
        except Exception as e:
            self.status.config(text=f"GAG 启动失败:{e}")
            return
        si = subprocess.STARTUPINFO()  # 隐藏 frpc 黑窗
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            self.frpc = subprocess.Popen([FRPC, "-c", FRPC_CFG], startupinfo=si,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            self.status.config(text=f"frpc 启动失败:{e}")
        self.btn.config(text="■ 停止")

    def stop(self):
        for p in (self.gag, self.frpc):
            if p and p.poll() is None:
                p.terminate()
        self.gag = self.frpc = None
        self.btn.config(text="▶ 启动")

    def _poll(self):
        """每 2s 刷新状态(GAG 进程 / frpc 进程 / 9880 端口)"""
        gag_ok = self.gag is not None and self.gag.poll() is None
        frpc_ok = self.frpc is not None and self.frpc.poll() is None
        port_ok = _port_open(API_PORT)
        self.status.config(
            text=f"GAG  : {'运行' if gag_ok else '停止'}\n"
                 f"frpc : {'运行' if frpc_ok else '停止'}\n"
                 f"9880 : {'监听 ✓' if port_ok else '未监听'}"
                 + ("" if port_ok else "\n(等 GAG 自动起 api,约 10-30s)")
        )
        self.root.after(2000, self._poll)

    def on_close(self):
        self.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Launcher(root)
    root.mainloop()
