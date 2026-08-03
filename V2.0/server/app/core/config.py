"""
服务端配置加载
基于 pydantic-settings 从项目根 .env 读取配置。

V2.0 重点是 QQ 官方机器人(Webhook)接入,凭证只需 2 个:
  - QQ AppID:机器人 ID
  - QQ AppSecret:既换 access_token(调 QQ REST 发消息),又作 Webhook 回调 Ed25519 验签密钥派生源
    (QQ 文档术语「Bot Secret」即此字段;OpenClaw/AstrBot/阿里云接入均只需 2 凭证佐证,用户后台确认无独立 Bot Secret)

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建配置模块:服务端/Redis/QQ 凭证(AppID+AppSecret)统一从项目根 .env 加载
  2. 凭证从「AppSecret+BotSecret 双凭证」修正为「单 AppSecret」(用户后台确认无独立 Bot Secret)

2026-06-27
变更说明：
  1. M2 扩展:搬入 V1.0 的 LLM Providers / 人设 / 四级记忆 / 插件 配置字段(copy 核心模块用)
  2. M2 新增:心情系统参数(docs/03 §4) + 聊天记录 block 参数(docs/02 §6/§7),均为 V2.0 原创
  3. 多模态(TTS/ASR/图像生成/Vision)留 M6,本里程碑不声明

2026-06-30
变更说明：
  1. M7 新增 mood_history_keep(mood 历史曲线保留条数,面板实时监控页用)、
     cors_origins(Web 面板 CORS 允许 origin,逗号分隔,空则用默认 dev origin)

2026-06-30
变更说明：
  1. M8 新增 takeover_pending_ttl_sec(代答 pending 保留秒,默认 86400)、
     takeover_batch_max(批量代答/录入上限)、takeover_queue_orphan_scan_limit(孤儿 pid 扫描上限)

2026-08-04
变更说明：
  1. 新增 log_level(根 logger 级别,默认 INFO;.env 设 LOG_LEVEL=DEBUG 排障免改代码)
     配合 core/logging_config.setup_logging 修应用 logging 盲区(业务 INFO 原被默认配置丢弃)

2026-08-04 #2
变更说明：
  1. M-tts 新增 TTS 语音合成配置(tts_enable/voice/speed/gain/emotion/send_text_also/provider/model)
"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录(本文件位于 server/app/core/,向上三级到项目根 V2.0/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """服务端配置:字段名小写,自动映射 .env 中的大写键;extra=ignore 忽略未声明键"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),  # 从项目根 .env 读取
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 中未声明的键
    )

    # 1.服务端
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    access_token: str = "change-me-please"  # 单人场景访问令牌(Web 面板 REST 鉴权,M7 用)
    cors_origins: str = ""  # Web 面板 CORS 允许的 origin(逗号分隔;空则用默认 dev origin localhost:5173)

    # 2.Redis(云端 Docker)
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""

    # 3.QQ 官方机器人凭证(只需 AppID + AppSecret;AppSecret 既换 token 又作 Ed25519 验签密钥派生源)
    qq_app_id: str = Field(default="", validation_alias="APPID")  # .env 旧字段 APPID(无下划线),显式别名映射
    qq_app_secret: str = Field(default="", validation_alias="QQ_APP_SECRET")  # 既换 access_token,又作 Ed25519 验签密钥派生源
    # QQ API 端点 base(便于切沙箱 sandbox.api.sgroup.qq.com,默认正式环境)
    qq_api_base: str = "https://api.sgroup.qq.com"  # 发消息 REST base
    qq_token_base: str = "https://bots.qq.com/app"  # 换 access_token 接口 base
    qq_webhook_public_url: str = ""  # Webhook 回调公网 URL(部署/调试用,代码可不读)
    qq_signature_max_skew_sec: int = 300  # 验签时间戳防重放容忍秒数(QQ 推荐 300)

    # 4.LLM Providers(M2 copy V1.0 llm 模块用;key 缺失时 provider 不注册,pipeline 降级)
    glm_api_key: str = ""
    deepseek_api_key: str = ""
    siliconflow_api_key: str = ""
    chat_provider: str = "glm"  # 默认聊天 provider(MessageContext 兜底;GLM 限流时 .env 设 CHAT_PROVIDER=deepseek 切换,免改代码)

    # 5.人设系统(M2 copy V1.0 persona 模块用)
    persona_active_id: str = "default"  # 未绑定对象时使用的默认人设 id
    persona_dir: str = "server/data/persona"  # 人设 JSON 文件双写目录(相对项目根 V2.0/)

    # 6.四级记忆系统(M2 copy V1.0 memory 模块用)
    memory_enabled: bool = True  # 总开关,False 时降级为无记忆
    memory_working_window: int = 20  # 工作记忆滑窗轮数(get_history 二次裁剪)
    memory_episodic_enable: bool = True
    memory_episodic_summarize_threshold: int = 12  # 每 N 轮触发一次 Episodic 摘要
    memory_episodic_reflect_interval: int = 5  # 每 N 次摘要触发一次反思
    memory_longterm_enable: bool = True
    memory_longterm_max_facts: int = 200  # 长期记忆条目上限,超出触发遗忘淘汰
    memory_longterm_extract_threshold: int = 6  # 每 N 轮批量提取长期事实(2026-07-07 优化3,替每轮单条降成本;0=禁用)
    memory_retrieve_topk: int = 5  # 检索召回 top-K
    memory_summary_provider: str = ""  # 编码用 LLM provider,空则用对话同款
    memory_summary_model: str = ""  # 编码用模型,空则用 provider 默认
    # 遗忘评分权重与阈值(沿用 V1.0 forgetting.py)
    memory_forget_w_importance: float = 0.4
    memory_forget_w_recency: float = 0.3
    memory_forget_w_access: float = 0.15
    memory_forget_w_emotion: float = 0.15
    memory_forget_threshold: float = 0.3
    memory_forget_halflife_hours: float = 72.0
    # M4 记忆融合增强(借鉴 angel_memory:BM25 检索 / 加权随机召回 / 睡眠巩固)
    memory_retriever: str = "bm25"  # 检索器:bm25(BM25 评分)/ keyword(交集计数)
    memory_weighted_sample: bool = True  # 加权随机召回(避确定性偏见,angel_memory 借鉴)
    memory_consolidate_enable: bool = True  # 睡眠巩固:episodic 摘要→long-term fact + 冗余清理
    memory_consolidate_importance: float = 0.6  # 巩固提炼 fact 的最低 importance(低于则丢弃)
    memory_episodic_keep: int = 20  # episodic 保留条数(超则清理最旧,睡眠巩固触发)
    # 向量语义检索(2026-07-07 记忆优化阶段1:激活向量检索,BM25+向量 RRF 融合)
    memory_embedding_provider: str = "glm"  # embedding provider(glm/空=禁用,降级纯 BM25)
    memory_embedding_model: str = "embedding-3"  # GLM embedding-3(2048 维)
    memory_embedding_sim_threshold: float = 0.85  # 语义去重 cosine 阈值(>= 视为重复,替 Jaccard)

    # 7.插件系统(M2 copy V1.0 plugins 基础设施用;M2 不加载业务插件,只保证 EventBus/钩子链路通)
    plugin_enabled: bool = True  # 插件系统总开关,False 时降级(不初始化、不触发任何钩子)
    plugin_dir: str = "server/app/plugins"  # 插件根目录(相对项目根);_ 前缀子目录不被自动加载
    plugin_auto_discover: bool = True  # 启动时自动扫描+加载插件目录(M2 阶段目录内无业务插件)
    plugin_tick_interval: float = 60.0  # on_tick 调度间隔(秒),驱动 mood 衰减/时间/主动消息

    # 8.心情系统(M2 新增,docs/03 §4;从 V1.0 mood_dynamic 融入架构,不再作独立插件)
    mood_step: float = 0.1  # 对话情感关键词触发的 mood ±step
    mood_decay: float = 0.05  # on_tick 向中性回归的衰减幅度
    mood_neutral: float = 0.5  # 中性 mood 值(衰减回归目标)
    mood_kaomoji_prob: float = 0.3  # QQ 回复末尾附颜文字的概率(0-1,docs/03 §7.2)
    mood_history_keep: int = 100  # mood 历史曲线保留条数(M7 面板实时监控页,set_mood 写时 LTRIM)

    # 9.聊天记录 block 结构(M2 新增,docs/02 §6/§7/§10)
    block_silence_min: int = 10  # 静默分组阈值(分钟):超时关闭旧 block 开新 block
    input_debounce_sec: float = 2.0  # 连发防抖窗口(秒):用户连发在此窗口合并为一次 LLM 调用
    chat_history_max_blocks: int = 2  # get_history 取最近 N 个 block 拼 LLM 上下文
    chat_history_max_messages: int = 20  # get_history 二次裁剪的最大消息条数

    # 10.评分系统(M3 新增,docs/01 §4 / docs/02 §5 score 四元组 / docs/03 §5 评分补偿)
    score_enabled: bool = True  # 自动评分总开关:每条 ai 回复发用户后自动 LLM 评分
    score_provider: str = ""  # 评分用 LLM provider,空则用对话同款(默认 glm)
    score_model: str = ""  # 评分用模型,空则用 provider 默认模型
    score_positive_threshold: int = 85  # 正样本阈值:score>=此值归类 positive(驱动反推正样本)
    score_negative_threshold: int = 60  # 负样本阈值:score<此值归类 negative(驱动反推负样本)
    score_health_window: int = 20  # 人设健康度统计窗口:近 N 条 ai/proxy 消息求均分(docs/01 §4)
    score_sample_keep: int = 20  # 每类(正/负)评分样本最多留存条数(防 List 无限增长)
    # 11.反推人设(M3 新增,docs/01 §4 驱动反推 / docs/02 §5.1):评分样本 → 人设字段提炼合并
    reverse_infer_enabled: bool = True  # 反推总开关
    reverse_infer_provider: str = "glm"  # 反推专用 provider(与聊天解耦,无 key 降级空 diff)
    reverse_infer_mode: str = "fill_empty"  # 合并模式:fill_empty(只填空)/ overwrite(覆盖查漂移)
    reverse_infer_max_fields: int = 6  # 单次反推最多改写字段数(整体接受,不拆散语义)
    # 12.MCP / 工具循环(M5,docs/01 §6):tool-loop + 自研工具 + MCP client
    tool_loop_enable: bool = True  # tool-loop 总开关:有注册工具时 LLM 可 function calling 调工具
    tool_loop_max_iterations: int = 5  # tool-loop 最大循环轮数(防死循环)
    web_search_enable: bool = True  # DuckDuckGo 联网兜底工具开关(docs/01 §6 联网兜底)
    mcp_enable: bool = True  # MCP client 总开关(连外部 MCP server)
    mcp_servers: str = ""  # MCP server 列表 JSON([{name,transport:stdio|sse,command,args|url}]),空则不连
    # 13.插件兼容(M6,docs/01 §8 / docs/04 §8):.star 兼容层 + V1.0 原生插件收敛
    star_enable: bool = True  # .star 兼容层总开关(加载 AstrBot 风格 .star 插件)
    star_dir: str = "server/data/star_plugins"  # .star 插件目录(相对项目根,放 *.py)

    # 14.代人聊天 takeover(M8,docs/01 §11 / docs/02 §8):代答 pending 队列 + 批量连发真实下发 QQ
    takeover_pending_ttl_sec: int = 86400  # pending 待答保留秒数(管理员可能延迟代答,V1.0 的 120s 太短)
    takeover_batch_max: int = 20  # 批量代答/录入条数上限(防滥用,截断)
    takeover_queue_orphan_scan_limit: int = 50  # resolve/list_queue 扫描孤儿 pid 上限(防雪崩)

    # 15.多模态-图像理解(M-vision,2026-07-01):QQ 收图 → GLM vision 解析成文本 → 进 pipeline
    multimodal_vision_enable: bool = True   # 图像理解总开关:收图消息时尝试解析;关则图片消息忽略/纯文本
    multimodal_vision_provider: str = "glm"  # 图像理解 provider(glm 用 glm-4v;stub 占位;无 key 自动降级 stub)
    glm_vision_model: str = "glm-4v-flash"   # GLM 视觉模型(free 轻量;可改 glm-4v / glm-4v-plus)
    multimodal_vision_prompt: str = "请用中文简洁描述这张图片的内容(用于对话上下文)。"  # 视觉解析提示词

    # 16.日志(2026-08-04):应用 logging 级别,配合 core/logging_config.setup_logging 修盲区
    log_level: str = "INFO"  # 根 logger 级别(INFO/DEBUG/WARNING;.env LOG_LEVEL 覆盖;排障用 DEBUG)

    # 17.TTS 语音合成(M-tts,2026-08-04):CosyVoice2-0.5B via 硅基流动 → 转 silk → QQ 语音条
    #    provider/model 级配置(用户面板开关/音色/语速/gain 在 plugins/tts_reply/plugin.yaml config_schema)
    tts_provider: str = "siliconflow"  # TTS provider(仅 siliconflow 实现 CosyVoice2;无 key 降级 stub)
    tts_model: str = "FunAudioLLM/CosyVoice2-0.5B"  # TTS 模型(硅基流动 CosyVoice2)
    tts_emotion_provider: str = ""  # 情感推导 LLM provider(空=用 chat_provider)


# 全局配置单例
settings = Settings()
