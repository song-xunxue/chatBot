"""
Qwen3 思考模式关闭实测对比脚本(2026-10-25 关思考改造的实测留档)
对本地 Ollama(http://127.0.0.1:11434,qwen3:8b)同一句 user 消息做三路对比:
  ① /v1/chat/completions 默认(思考开,不设 max_tokens 上限)
  ② /v1/chat/completions + user 末尾注入 " /no_think"(软关思考)
  ③ /api/chat + "think": false(Ollama 原生,真正关思考)
每例记录:耗时 / prompt_eval_count / eval_count(/v1 对应 usage.prompt_tokens
与 completion_tokens)/ 回复文本 / content 是否为空。
附带:④ bug 复现(①+max_tokens=40,预期 content 空——token 全花在 <think> 段);
⑤ 走新代码端到端(LOCAL_LLM_API_BASE/LOCAL_LLM_DISABLE_THINK 环境变量注入,
LocalLLMProvider.chat(),断言实际请求 URL 走原生分支)。

用法(python bench_think.py [case],case 可选 openai/nothink/native/repro/e2e/all):
  python bench_think.py all      # 顺序全跑(①可能数分钟,2~4 tok/s)
  python bench_think.py openai   # 只跑 ①

作者: 李文煜
日期: 2026-10-25
"""
import os
import sys
import time
from pathlib import Path

# Windows 终端默认 GBK,改 stdout 为 UTF-8(中文回复正确输出)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 环境变量必须在导入 app 模块前设置(pydantic-settings 单例 import 时读 env;
# 真实环境变量优先级高于 .env,等价于"子进程带环境变量启动")
os.environ["LOCAL_LLM_API_BASE"] = "http://127.0.0.1:11434/v1"
os.environ["LOCAL_LLM_DISABLE_THINK"] = "true"

# app/ 入 sys.path(同级导入,与 pytest.ini pythonpath 一致)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import httpx  # noqa: E402  同步 HTTP 客户端(bench 与 provider 路径一致)

OLLAMA_ROOT = "http://127.0.0.1:11434"   # Ollama 根地址(不带 /v1)
MODEL = os.environ.get("LOCAL_LLM_MODEL", "qwen3:8b")
USER_TEXT = "用一句中文说你在本机运行"     # 三路对比统一用这句
TIMEOUT = 570.0                          # 单请求超时(秒);① 思考开可能数分钟,超时记截断


def _fmt_reply(text: str, limit: int = 60) -> str:
    """回复文本截断成单行(markdown 表格用;换行与竖线替换防破表)"""
    one_line = (text or "").replace("\n", " ").replace("|", "/")
    return one_line[:limit] + ("..." if len(one_line) > limit else "")


def _bench_openai(label: str, append_no_think: bool = False, max_tokens: int | None = None) -> dict:
    """①②④:OpenAI 兼容 /v1/chat/completions 路径(可选注入 /no_think、max_tokens 上限)"""
    content = USER_TEXT + (" /no_think" if append_no_think else "")
    payload = {"model": MODEL, "stream": False,
               "messages": [{"role": "user", "content": content}]}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=TIMEOUT) as client:   # post 发 JSON 请求,等完整响应
            resp = client.post(f"{OLLAMA_ROOT}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        elapsed = time.perf_counter() - start
        usage = data.get("usage", {})                    # /v1 用量字段(prompt/completion_tokens)
        msg0 = (data.get("choices") or [{}])[0].get("message", {})
        text = msg0.get("content") or ""
        return {"case": label, "sec": elapsed, "prompt": usage.get("prompt_tokens"),
                "eval": usage.get("completion_tokens"), "empty": not text.strip(),
                "reply": _fmt_reply(text),
                "note": f"全长{len(text)}字,含<think>={'<think>' in text},"
                        f"message字段={sorted(msg0.keys())}"}
    except httpx.ReadTimeout:                            # 超时(①可能超 570s)
        return {"case": label, "sec": time.perf_counter() - start, "prompt": None,
                "eval": None, "empty": None, "reply": f">{TIMEOUT:.0f}s 被截断(ReadTimeout)"}


def _bench_native() -> dict:
    """③:Ollama 原生 /api/chat + think:false(新代码默认分支)"""
    payload = {"model": MODEL, "stream": False, "think": False,
               "messages": [{"role": "user", "content": USER_TEXT}]}
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(f"{OLLAMA_ROOT}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        elapsed = time.perf_counter() - start
        text = data.get("message", {}).get("content") or ""
        return {"case": "③ /api/chat + think:false", "sec": elapsed,
                "prompt": data.get("prompt_eval_count"), "eval": data.get("eval_count"),
                "empty": not text.strip(), "reply": _fmt_reply(text),
                "note": f"全长{len(text)}字,thinking字段={'thinking' in data.get('message', {})}"}
    except httpx.ReadTimeout:
        return {"case": "③ /api/chat + think:false", "sec": time.perf_counter() - start,
                "prompt": None, "eval": None, "empty": None, "reply": "超时"}


def _e2e_new_code() -> dict:
    """⑤:走新代码端到端——LocalLLMProvider.chat(),录制实际请求 URL 验证走原生分支"""
    import llm.local as local_mod
    from llm.local import LocalLLMProvider
    from llm.base import Message

    recorded: list[str] = []
    orig_client = local_mod.httpx.Client                # 保存真 Client,用后还原

    class _RecClient:
        """录制 post 的 URL 并委托真 httpx.Client(不 mock 网络,真连 Ollama)"""
        def __init__(self, *a, **k):
            self._inner = orig_client(*a, **k)
        def __enter__(self):
            self._inner.__enter__()
            return self
        def __exit__(self, *a):
            return self._inner.__exit__(*a)
        def post(self, url, **k):
            recorded.append(url)
            return self._inner.post(url, **k)

    local_mod.httpx.Client = _RecClient
    try:
        p = LocalLLMProvider(api_key="")
        start = time.perf_counter()
        import asyncio                                    # chat 是协程,run 驱动
        resp = asyncio.run(p.chat([Message(role="user", content=USER_TEXT)]))
        elapsed = time.perf_counter() - start
    finally:
        local_mod.httpx.Client = orig_client
    ok_native = any(u.endswith("/api/chat") for u in recorded)
    return {"case": "⑤ 新代码 e2e(disable_think=true)",
            "sec": elapsed, "prompt": None, "eval": None,
            "empty": not resp.text.strip(),
            "reply": f"URL={recorded[0] if recorded else '无'};原生分支={ok_native};"
                     f"回复={_fmt_reply(resp.text)};finish={resp.finish_reason}"}


_CASES = {
    "openai": lambda: _bench_openai("① /v1 默认(思考开)"),
    "nothink": lambda: _bench_openai("② /v1 + /no_think 注入", append_no_think=True),
    "native": _bench_native,
    "repro": lambda: _bench_openai("④ /v1 默认 + max_tokens=40(bug 复现)", max_tokens=40),
    "e2e": _e2e_new_code,
}


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = list(_CASES) if case == "all" else [case]
    print(f"模型: {MODEL} | user: {USER_TEXT!r} | 单请求超时: {TIMEOUT:.0f}s", flush=True)
    for name in names:
        r = _CASES[name]()
        sec = f"{r['sec']:.1f}"
        print(f"[{name}] {r['case']} | 耗时 {sec}s | prompt_eval={r['prompt']} "
              f"| eval={r['eval']} | content空={r['empty']} | {r.get('note', '')}"
              f"\n        回复: {r['reply']}", flush=True)
        # markdown 表格行(逐例输出,便于中途截断时仍保留已完成数据)
        print(f"| {r['case']} | {sec} | {r['prompt']} | {r['eval']} "
              f"| {r['empty']} | {r['reply']} |", flush=True)


if __name__ == "__main__":
    main()
