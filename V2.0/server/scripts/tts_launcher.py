"""
GPT-SoVITS(api_v2) + frpc 一键启动器(console,2026-08-08)
直接跑 api_v2.py(跳过 GAG GUI),从 tts_infer.yaml 自动加载清浔 dania 模型。
启动器 console 显示 api_v2 加载日志 + 9880 端口状态。关窗口=停止两者。
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
GAG_DIR = r"E:\GPT-SoVITS"
# 直接跑 api_v2(不经 GAG GUI;tts_infer.yaml 已配 dania 模型,api_v2 启动自动加载)
API_CMD = [
    os.path.join(GAG_DIR, "runtime", "python.exe"),
    "api_v2.py",
    "-a", "0.0.0.0",   # 监听所有接口(frpc 要连,不能只 127.0.0.1)
    "-p", "9880",
    "-c", "GPT_SoVITS/configs/tts_infer.yaml",
]
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
    print("  GPT-SoVITS(api_v2 直跑) + frpc 启动器")
    print("  跳过 GAG GUI,直接 api_v2.py 加载清浔(dania)模型")
    print("=" * 50)

    api_proc = None
    if _port_open(API_PORT):
        print(f"[跳过] api_v2 已在跑(9880 监听)")
    else:
        print(f"[启动] api_v2.py(加载模型到 GPU 约 15-30s,请等)...")
        try:
            # 清除 pyinstaller 注入的 _MEIPASS/_PYI*/PYTHONPATH(会污染 runtime\python.exe 致 GPT-SoVITS 推理 Errno 22)
            clean_env = {k: v for k, v in os.environ.items() if not k.startswith(('_ME', '_PYI'))}
            clean_env.pop('PYTHONPATH', None)
            api_proc = subprocess.Popen(API_CMD, cwd=GAG_DIR, env=clean_env)
        except Exception as e:
            print(f"[错误] api_v2 启动失败: {e}")
            input("按回车退出..."); return

    print("[启动] frpc(穿透隧道)...")
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        frpc = subprocess.Popen([FRPC, "-c", FRPC_CFG], startupinfo=si,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        print(f"[错误] frpc 启动失败: {e}")
        input("按回车退出..."); return

    print("\n[监控中] 关此窗口=停止 api_v2 + frpc")
    print("等 9880 监听后(显示 [OK])再发 QQ 消息\n")
    try:
        while True:
            api_ok = _port_open(API_PORT)
            frpc_ok = frpc.poll() is None
            print(f"\r  api_v2(9880): {'[OK] 监听' if api_ok else '[..] 加载中(等模型)'}"
                  f"   frpc: {'[OK] 运行' if frpc_ok else '[!!] 已退出'}        ", end="", flush=True)
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("\n\n[停止] 关闭中...")
        if frpc.poll() is None:
            frpc.terminate()
        if api_proc and api_proc.poll() is None:
            api_proc.terminate()
        print("[完成] 已停止")


if __name__ == "__main__":
    main()
