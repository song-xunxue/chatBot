"""
REST 客户端（管理/配置通道）
基于 httpx 同步调用服务端 REST（人设列表/详情、健康检查、插件配置等）。
WS 是实时主通道，REST 用于初始化拉取与设置类操作。供 UI 主线程调用。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建 RestClient：get/post 通用 + 人设/health 便捷方法

2026-06-25
变更说明：
  1. 新增 get_avatar_bytes(rel_path)：GET rest_url/rel_path 拉人设头像字节，供左列表/气泡头像
"""
import httpx


class RestClient:
    """同步 REST 客户端：带 access_token 鉴权"""

    def __init__(self, base_url: str, token: str, timeout: float = 10.0):
        self._base = base_url.rstrip("/")
        self._headers = {"X-Access-Token": token}
        self._timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def get(self, path: str, **kwargs) -> dict | list:
        r = httpx.get(self._url(path), headers=self._headers, timeout=self._timeout, **kwargs)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, json_body: dict | None = None, **kwargs) -> dict | list:
        r = httpx.post(self._url(path), headers=self._headers, json=json_body, timeout=self._timeout, **kwargs)
        r.raise_for_status()
        return r.json()

    # —— 便捷方法 ——
    def health(self) -> dict:
        """健康检查（无需鉴权）"""
        r = httpx.get(f"{self._base}/health", timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def list_personas(self) -> list[dict]:
        return self.get("/api/v1/persona")

    def get_persona(self, persona_id: str) -> dict:
        return self.get(f"/api/v1/persona/{persona_id}")

    def get_pet_avatar_bytes(self) -> bytes | None:
        """下载桌宠头像字节；未上传(404)/失败返回 None（客户端回退默认外观）"""
        try:
            r = httpx.get(self._url("/api/v1/pet/avatar"), headers=self._headers, timeout=8.0)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                return r.content
        except Exception:
            pass
        return None

    def vision(self, image_bytes: bytes, prompt: str = "请简要描述这张图片的内容", mime: str = "image/jpeg") -> str:
        """图像理解：上传图片 → 文字描述（M6.2，硅基流动视觉模型）"""
        r = httpx.post(self._url("/api/v1/multimodal/vision"), headers=self._headers,
                       files={"file": ("image", image_bytes, mime)}, data={"prompt": prompt}, timeout=60)
        r.raise_for_status()
        return r.json()["text"]

    def get_avatar_bytes(self, rel_path: str) -> bytes | None:
        """下载人设头像字节（rel_path 为人设 dict 的 avatar 相对路径，如 static/avatar/x.jpg）。
        GET rest_url/rel_path；非图片/失败返回 None（调用方回退默认 svg，不崩）。"""
        if not rel_path:
            return None
        try:
            r = httpx.get(self._url("/" + rel_path.lstrip("/")), timeout=8.0)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                return r.content
        except Exception:
            pass
        return None

    def asr(self, audio_bytes: bytes, fmt: str = "wav") -> str:
        """语音识别：上传音频 → 文字（M6.2，硅基流动 SenseVoice）"""
        r = httpx.post(self._url("/api/v1/multimodal/asr"), headers=self._headers,
                       files={"file": (f"audio.{fmt}", audio_bytes, f"audio/{fmt}")}, timeout=60)
        r.raise_for_status()
        return r.json()["text"]
