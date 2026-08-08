"""
GPT-SoVITS + frpc 一键启动器(console 版,M-tts 2026-08-08)
双击启动 GAG(GPT-SoVITS api_v2 9880)+ frpc(穿透),console 窗口实时监控状态,关窗=停止 frpc。
用 console 而非 tkinter(GUI):避免 conda 环境 pyinstaller 打包 tkinter DLL 失败。
打包:pyinstaller --onefile --console --name GPT-SoVITS启动器 tts_launcher.py

作者: 李文煜
日期: 2026-08-08
"""
import os
import socket
import subprocess
import sys
import time

BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
GAG = r"E:\GPT-SoVITS\GAG v0.4.3.exe"
FRPC = os.path.join(BASE, "frp", "frp_0.70.0_windows_amd64", "frpc.exe")
FRPC_CFG = os.path.join(BASE, "frp", "frp_0.70.0_windows_amd64", "frpc.toml")
API_PORT = 9880


def _port_open(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def main():
    print("=" * 50)
    print("  GPT-SoVITS(GAG) + frpc 一键启动器")
    print("=" * 50)

    gag = None
    if _port_open(API_PORT):
        print(f"[跳过] GAG 已在跑(9880 监听),不重复启动")
    else:
        print(f"[启动] GAG(GPT-SoVITS)... 等它自动起 api(约 10-30s)")
        try:
            gag = subprocess.Popen([GAG], cwd=os.path.dirname(GAG))  # cwd=GAG 目录,相对路径 runtime\python.exe 解析对
        except Exception as e:
            print(f"[错误] GAG 启动失败: {e}")
            input("按回车退出...")
            return

    print("[启动] frpc(穿透隧道)...")
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        frpc = subprocess.Popen([FRPC, "-c", FRPC_CFG], startupinfo=si,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        print(f"[错误] frpc 启动失败: {e}")
        input("按回车退出...")
        return

    print("\n[监控中] 关此窗口=停止 frpc(GAG 若本启动器启动也一并停,外部启动的不动)")
    print("状态每 2s 刷新:\n")
    try:
        while True:
            gag_ok = _port_open(API_PORT)
            frpc_ok = frpc.poll() is None
            status = (f"\r  GAG(9880): {'[OK] 监听' if gag_ok else '[..] 启动中'}"
                      f"   frpc: {'[OK] 运行' if frpc_ok else '[!!] 已退出'}"
                      f"        ")
            print(status, end="", flush=True)
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("\n\n[停止] 关闭中...")
        if frpc.poll() is None:
            frpc.terminate()
        if gag and gag.poll() is None:
            gag.terminate()
        print("[完成] frpc + GAG(本启动器启动的)已停止")


if __name__ == "__main__":
    main()
