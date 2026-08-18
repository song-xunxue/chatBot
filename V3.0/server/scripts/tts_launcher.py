"""
GPT-SoVITS(api_v2) + frpc 一键启动器(V3.0 版,2026-08-17;与 V2.0 同代码,心跳报 V3.0 8091)
直接跑 api_v2.py(跳过 GAG GUI),从 tts_infer.yaml 自动加载清浔 dania 模型。
启动器 console 显示 api_v2 加载日志 + 9880 端口状态。关窗口=停止两者。
api_v2 就绪后每 30s 向云端面板上报心跳(heartbeat.json 指向 http://43.140.219.99:8091)。
打包:pyinstaller --onefile --console --name GPT-SoVITS启动器3.0 --icon ../../tts-tools/启动器.ico tts_launcher.py
注意:与 V2.0 启动器共享同一 GPT-SoVITS(9880)与同一 frp 隧道,不能同时跑——开一个即可
(心跳只报所开版本的面板;V3.0 为主力时日常开 3.0 版)。

作者: 李文煜
日期: 2026-08-08

2026-08-10
变更说明:
  1. 加心跳上报线程:api_v2 监听后每 30s POST /tts/gptsovits/heartbeat(配同目录 heartbeat.json);
     关闭时上报 ready=false。面板 status 端点心跳命中即不探测 frp 隧道(懒检测+免重复探测)。
  2. 心跳用标准库 urllib.request,避免给 pyinstaller exe 加 httpx 依赖。

2026-08-11
变更说明:
  1. 修关闭假阳性 bug:点窗口 X 关闭时 CTRL_CLOSE 只给 ~5s 清理,旧版 _post_heartbeat timeout 10s
     来不及完成 → Redis 心跳 90s TTL 残留 → 面板假显就绪。改:全局 _hb_cfg + _report_offline(短 timeout 3s,
     幂等)+ atexit + signal(SIGINT/SIGBREAK) + finally 四重触发,确保关闭清理窗口内上报 ready=false 清 Redis。
"""
import atexit
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

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
HEARTBEAT_INTERVAL = 30   # 秒;启动器每 30s 上报,面板 Redis TTL 90s 容错 3 周期

# 全局心跳配置:main 启动心跳前注入,供 atexit/signal handler 在进程退出时读
_hb_cfg = {"cloud_url": None, "token": None}


def _port_open(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def _load_heartbeat_config():
    """读同目录 heartbeat.json{cloud_url,token}。无文件/解析失败/缺字段返 None(心跳关闭,不影响启动器)。"""
    path = os.path.join(BASE, "heartbeat.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("cloud_url") and cfg.get("token"):
            return cfg
        print("  [心跳] heartbeat.json 缺 cloud_url/token,心跳关闭")
        return None
    except Exception as e:
        print(f"  [心跳] 读 heartbeat.json 失败({e}),心跳关闭")
        return None


def _post_heartbeat(cloud_url, token, ready, timeout=10):
    """同步 POST 心跳到云端(标准库 urllib,避免给 exe 加 httpx 依赖)。
    timeout 可调:关闭上报用 3s(确保 CTRL_CLOSE ~5s 清理窗口内完成)。失败仅打印(尽力而为)。
    返 True/False。"""
    try:
        url = cloud_url.rstrip("/") + "/api/v1/tts/gptsovits/heartbeat"
        data = json.dumps({"ready": ready, "reported_by": "launcher"}).encode("utf-8")
        req = urllib.request.Request(   # 构造 POST 请求(X-Access-Token header,与面板 verify_token 一致;非 Bearer)
            url, data=data, method="POST",
            headers={"X-Access-Token": token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # 发送
            return resp.status == 200
    except Exception as e:
        print(f"  [心跳] 上报失败(ready={ready}): {e}")
        return False


def _report_offline():
    """关闭时尽力上报 ready=false 让面板及时转红。短 timeout(3s) 确保在 CTRL_CLOSE 清理窗口内完成。
    幂等:atexit/signal/finally 多次调用安全(Redis delete 已清则服务端 no-op)。配置未注入时 no-op。"""
    url, token = _hb_cfg["cloud_url"], _hb_cfg["token"]
    if url and token:
        _post_heartbeat(url, token, ready=False, timeout=3)


def _signal_handler(signum, frame):
    """Ctrl+C / Ctrl+Break:上报离线后退出(raise SystemExit 触发 atexit + finally 双兜底)。"""
    _report_offline()
    raise SystemExit(0)


def _heartbeat_loop(cloud_url, token, stop_event):
    """后台线程:每 30s 上报就绪心跳(仅当 api_v2 9880 在监听);stop_event.set() 后上报离线再退出。

    竞态修复(2026-08-11):写 ready=True 后立即检查 stop_event——若写期间被 set(关闭),
    补发 ready=False 抵消,避免"ready=True 慢完成在 _report_offline 之后重写 Redis"致 90s 假就绪。"""
    while not stop_event.wait(HEARTBEAT_INTERVAL):   # 每 30s 醒来(stop 时 wait 立即返 True 跳出)
        if _port_open(API_PORT):
            _post_heartbeat(cloud_url, token, ready=True)
            if stop_event.is_set():   # 写 ready=True 期间收到关闭 → 补清跳出(防残留假就绪)
                break
    # 线程退出前上报离线(_report_offline 的冗余兜底;幂等)
    _post_heartbeat(cloud_url, token, ready=False, timeout=3)
    print("  [心跳] 已上报离线,线程退出")


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

    # 心跳上报(若配了 heartbeat.json):后台线程每 30s 通知云端"本地模型就绪"
    hb_cfg = _load_heartbeat_config()
    hb_stop = None
    if hb_cfg:
        _hb_cfg["cloud_url"], _hb_cfg["token"] = hb_cfg["cloud_url"], hb_cfg["token"]
        # 关闭上报四重触发:atexit(解释器退出)+ SIGINT/SIGBREAK(Ctrl+C/Break)+ finally(主循环异常)
        atexit.register(_report_offline)
        for sig in (signal.SIGINT, signal.SIGBREAK):
            try:
                signal.signal(sig, _signal_handler)
            except (ValueError, OSError):
                pass   # 非主线程/平台不支持,忽略(atexit + finally 仍兜底)
        hb_stop = threading.Event()
        threading.Thread(
            target=_heartbeat_loop,
            args=(hb_cfg["cloud_url"], hb_cfg["token"], hb_stop),
            daemon=True).start()
        print(f"[心跳] 已启动,每 {HEARTBEAT_INTERVAL}s 上报 -> {hb_cfg['cloud_url']}")
    else:
        print("[心跳] 未配 heartbeat.json,跳过(面板就绪检测将走主动探测)")

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
        if hb_stop is not None:
            hb_stop.set()   # 通知心跳线程上报离线后退出
        if frpc.poll() is None:
            frpc.terminate()
        if api_proc and api_proc.poll() is None:
            api_proc.terminate()
        _report_offline()   # 同步上报离线(短 timeout 3s,确保清理窗口内完成;幂等,与 atexit/线程重复安全)
        print("[完成] 已停止")


if __name__ == "__main__":
    main()
