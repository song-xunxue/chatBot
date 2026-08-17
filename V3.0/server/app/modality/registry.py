"""
图像理解 Provider 注册表(配置驱动,2026-07-02 #7 深化)
单一注册表 _VISION_PROVIDERS(name→类/key字段/展示名),与 llm/registry 同构。
此前 get_vision 是 if-name→return-new 浅模块;现配置驱动,加 vision provider 只改一处。

作者: 李文煜
日期: 2026-07-02
"""
from dataclasses import dataclass

from modality.base import VisionProvider
from modality.glm import GLMVisionProvider
from modality.stub import StubVisionProvider
from core.config import settings


@dataclass(frozen=True)
class VisionSpec:
    """图像理解 provider 规格。key_attr 空=不需 key(stub)。"""
    name: str
    cls: type
    key_attr: str
    display: str


_VISION_PROVIDERS: list[VisionSpec] = [
    VisionSpec("glm", GLMVisionProvider, "glm_api_key", "GLM glm-4v"),
    VisionSpec("stub", StubVisionProvider, "", "占位(不调 API)"),
]
_BY_NAME: dict[str, VisionSpec] = {p.name: p for p in _VISION_PROVIDERS}


def get_vision(name: str = "") -> VisionProvider:
    """按名实例化图像理解 provider;未知名或需 key 但未配(非 stub)→降级 stub(链路不断)。
    优先显式 name,否则 settings.multimodal_vision_provider,默认 glm。"""
    spec = _BY_NAME.get((name or settings.multimodal_vision_provider or "glm").lower())
    if not spec:
        return StubVisionProvider()
    if spec.key_attr and not getattr(settings, spec.key_attr):
        return StubVisionProvider()   # 需 key 但未配 → 降级 stub
    return spec.cls()


def vision_specs() -> list[VisionSpec]:
    """所有 vision provider 规格(供面板/调试)"""
    return list(_VISION_PROVIDERS)
