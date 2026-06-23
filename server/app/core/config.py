"""
服务端配置加载
基于 pydantic-settings 从项目根 .env 读取配置

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.2 创建配置模块：服务端、Redis、LLM、多模态凭据统一从 .env 加载
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（本文件位于 server/app/core/，向上三级到项目根）
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """服务端配置：字段名小写，自动映射 .env 中的大写键"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),  # 从项目根 .env 读取
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 中未声明的键（如客户端专用变量）
    )

    # 1.服务端
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    access_token: str = "change-me-please"  # 单人场景访问令牌（WS/REST 鉴权）

    # 2.Redis（云端 Docker）
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""

    # 3.LLM Providers（对应 F-C-03；lmarena 已移除不做）
    glm_api_key: str = ""
    deepseek_api_key: str = ""
    siliconflow_api_key: str = ""

    # 4.多模态服务（M6 阶段使用）
    tts_api_key: str = ""
    asr_api_key: str = ""
    image_gen_api_key: str = ""

    # 5.人设系统（M3）
    persona_active_id: str = "default"             # 未绑定对象时使用的默认人设 id
    persona_dir: str = "server/data/persona"       # 人设 JSON 文件双写目录（相对项目根）

    # 6.四级记忆系统（M3）
    memory_enabled: bool = True                    # 总开关，False 时降级为 M2 行为
    memory_working_window: int = 20                 # 工作记忆滑窗轮数
    memory_episodic_enable: bool = True
    memory_episodic_summarize_threshold: int = 12   # 每 N 轮触发一次 Episodic 摘要
    memory_episodic_reflect_interval: int = 5       # 每 N 次摘要触发一次反思
    memory_longterm_enable: bool = True
    memory_longterm_max_facts: int = 200            # 长期记忆条目上限，超出触发遗忘淘汰
    memory_retrieve_topk: int = 5                   # 检索召回 top-K
    memory_summary_provider: str = ""               # 编码用 LLM provider，空则用对话同款
    memory_summary_model: str = ""                  # 编码用模型，空则用 provider 默认
    # 遗忘评分权重与阈值（docs/06 §6.1 / §10）
    memory_forget_w_importance: float = 0.4
    memory_forget_w_recency: float = 0.3
    memory_forget_w_access: float = 0.15
    memory_forget_w_emotion: float = 0.15
    memory_forget_threshold: float = 0.3
    memory_forget_halflife_hours: float = 72.0


# 全局配置单例
settings = Settings()
