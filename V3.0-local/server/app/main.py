"""
MyChat V2.0 服务端入口
FastAPI 应用工厂、生命周期、健康检查、QQ Webhook 路由。

M2 范围:QQ Webhook 收私聊消息 → 连发防抖 → pipeline(persona/记忆/mood/LLM)→ 被动回复。
lifespan 启动:QQ httpx 客户端 + Redis 预热 + 人设/mood 种子 + 插件系统(空载) + mood 衰减循环。

日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建服务端最小应用骨架:create_app 工厂 + lifespan(httpx 单例)+ /health + 挂 qq_router

2026-06-27
变更说明：
  1. M2 lifespan 整合:人设默认 seed + mood 默认 5 档种表 + 插件系统(空载) + mood 衰减循环

2026-06-28
变更说明：
  1. M3 挂载评分/反推 REST 路由(score_router,/api/v1/chat/.../score、/health、/score/reverse_infer/...)
  2. M4 挂载记忆 REST 路由(memory_router,/api/v1/memory/... 查看/统计/遗忘/恢复/锁定)
  3. M5 lifespan 注册自研工具 + MCP client 连外部 server(无配置降级)
  4. M6 lifespan 加载 .star 兼容层(star_loader,适配到 EventBus/ToolRegistry)

2026-06-30
变更说明：
  1. M7 加 CORSMiddleware + 挂载 Web 面板 REST(chat/mood/plugin/persona/system)+ 暴露 star_loader 单例
  2. M7e 静态托管 dashboard/dist(生产同源省 CORS;dist 不存在则跳过,dev 用 vite :5173 + proxy)

2026-06-30
变更说明：
  1. M8 挂载代答/roleplay REST 路由(takeover_router / roleplay_router,/api/v1/takeover|roleplay/...)

2026-08-04
变更说明：
  1. 修应用 logging 盲区:import 后调 setup_logging(settings.log_level)(core/logging_config dictConfig)
     原未配置致业务 INFO 被 Python 默认 lastResort 丢弃,docker logs 只有 uvicorn access log

2026-10-25
变更说明：
  1. 接线 TickScheduler(此前 scheduler.py 写好但从未实例化,on_tick 钩子线上不触发):
     每 plugin_tick_interval 秒对活跃 oid 触发 on_tick,
     驱动 time_aware 时辰缓存/proactive_reply 主动搭话;随 lifespan 关闭而 stop
  2. 修活跃源集成 bug(实测 22:21 真发暴露):原只取 mychat:mood:oids,真实私聊未命中
     mood 情感词的会话永不进 tick;且 seed 的 demo 等非数字 oid 会让 onebot int(oid) 报错。
     活跃源改为 最近会话(chat_store.list_recent_sessions) ∪ mood oids 并集(模块级
     tick_object_ids),仅保留可转 QQ 号的数字 oid,非数字跳过并 debug 日志
  3. 挂载表情包库管理/渲染 REST 路由(sticker_router,/api/v1/sticker/list|upload|
     {name}/describe|render,sticker_plus 插件配套)

2026-10-26
变更说明：
  1. 挂载做梦与日记 REST 路由(diary_router,/api/v1/diary/list|{date}|run,
     dream 插件配套:日记查看 + 手动补跑一次做梦)
  2. 挂载世界书 REST 路由(worldbook_router,/api/v1/worldbook/entries CRUD|stats|rebuild,
     docs/09 世界书式记忆配套,面板 Worldbook.vue 消费)
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings
from core.logging_config import setup_logging
from api.rest_score import router as score_router
from api.rest_memory import router as memory_router
from api.rest_chat import router as chat_router
from api.rest_mood import router as mood_router
from api.rest_plugin import router as plugin_router
from api.rest_persona import router as persona_router
from api.rest_system import router as system_router
from api.rest_takeover import router as takeover_router
from api.rest_roleplay import router as roleplay_router
from api.rest_multimodal import router as multimodal_router
from api.rest_tts import router as tts_router
from api.rest_training import router as training_router
from api.rest_sticker import router as sticker_router
from api.rest_diary import router as diary_router   # dream 插件配套:日记查看/手动补跑(2026-10-26)
from api.rest_worldbook import router as worldbook_router   # 世界书条目 CRUD/统计/重建(docs/09,2026-10-26)

# 配置应用 logging(修盲区:原未配置致业务 INFO 被默认 lastResort 丢弃,仅 WARNING+ 出)
# 必须在 create_app 前调用;dictConfig 整合 uvicorn 走同一 handler/格式(详见 core/logging_config.py)
setup_logging(settings.log_level)

logger = logging.getLogger(__name__)


async def tick_object_ids(redis) -> list[str]:
    """on_tick 调度器的活跃对象源(2026-10-25 修集成 bug,单测见 tests/test_tick_object_ids.py)。

    活跃口径 = 最近有消息的会话(chat_store.list_recent_sessions,SCAN mychat:chat:*:blocks)
    ∪ mood 记录对象(list_mood_objects,与衰减循环同源)。
    只保留可转 QQ 号下发的数字 oid:非数字 oid(seed 的 demo/demo2_alice 等)跳过并 debug
    日志——否则下游 onebot.send_text 内 int(oid) 抛 "invalid literal for int()"(虽被
    _deliver 捕获,但主动搭话静默失败)。任一源读取异常降级用另一源,调度器不停摆。"""
    from storage import chat_store
    from mood.service import list_mood_objects
    oids: set[str] = set()
    try:
        # 活跃源 1:最近会话——真实私聊即使从未命中 mood 情感词(apply_emotion delta=0 不写)
        # 也能被 tick 覆盖,不再依赖手动 sadd mychat:mood:oids
        sessions = await chat_store.list_recent_sessions(redis, limit=50)
        oids.update(s.get("object_id", "") for s in sessions)
    except Exception:
        logger.exception("tick 活跃源读取最近会话失败(降级:仅用 mood oids)")
    try:
        # 活跃源 2:mood 记录对象——聊过但近期无 block 的对象仍可被 tick(与衰减口径一致)
        oids.update(await list_mood_objects(redis))
    except Exception:
        logger.exception("tick 活跃源读取 mood oids 失败(降级:仅用最近会话)")
    # isascii+isdigit 双卡:Unicode 上标/全角数字(如 ²/２)能过 isdigit 却过不了 int(),一并排除
    numeric = sorted(o for o in oids if o.isascii() and o.isdigit())
    skipped = sorted(o for o in oids if o and not (o.isascii() and o.isdigit()))
    if skipped:
        logger.debug("tick 跳过非数字 oid(无法作为 QQ 号下发): %s", skipped)
    return numeric


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:
    启动:平台适配器 → Redis 预热 → 人设/mood 种子 → 插件系统 → 后台维护循环(可选)
    关闭:循环 → 插件 → 适配器"""
    # V3.0 纯 OneBot:token 必配(fail-closed),WS 通道由 NapCat 连入被动建立
    if not settings.onebot_ws_token:
        logger.error("ONEBOT_WS_TOKEN 未配置——/ws 将拒绝一切连接(fail-closed),请在 .env 配置")
    from adapter import get_current_adapter
    _adapter = await get_current_adapter()

    # Redis 预热(惰性首连)+ 种子数据初始化
    from storage.redis_client import get_redis
    redis = await get_redis()
    from persona.store import init_default_if_absent
    await init_default_if_absent(redis)         # 默认人设 seed
    from mood.service import seed_default_kinds
    await seed_default_kinds(redis)             # mood 默认 5 档种表(docs/03 §3.2)

    # 插件系统(M2 空载:plugin_dir 无业务插件,仅建 EventBus 供 pipeline 钩子链路;M6 加载 .star)
    from plugins import init_plugins
    await init_plugins(redis)

    # on_tick 调度器(2026-10-25 接线):对活跃 oid 周期触发 on_tick(时辰缓存/主动搭话)。
    # 活跃源见模块级 tick_object_ids(最近会话 ∪ mood oids,仅数字 oid);provider 须为
    # 具名 async 函数,lambda 返回协程不会被 iscoroutinefunction 识别
    from plugins import get_event_bus
    from plugins.scheduler import TickScheduler

    async def _tick_object_ids() -> list[str]:
        return await tick_object_ids(redis)

    _tick_bus = get_event_bus()
    _tick_scheduler = None
    if _tick_bus is not None:   # PLUGIN_ENABLED=false 时 init_plugins 不建 bus(为 None),跳过防空转报错
        _tick_scheduler = TickScheduler(_tick_bus, object_ids_provider=_tick_object_ids,
                                        interval=settings.plugin_tick_interval)
        _tick_scheduler.start()
        logger.info("TickScheduler 已启动(interval=%ss,驱动 on_tick:时辰缓存/主动搭话)",
                    settings.plugin_tick_interval)

    # M6 .star 兼容层:加载 .star 插件(适配到 EventBus/ToolRegistry;无 .star 则空载)
    star_loader = None
    if settings.star_enable:
        from plugins import get_event_bus
        from plugins.star_compat.star_loader import StarLoader
        from tools import get_tool_registry
        from core.config import PROJECT_ROOT
        _bus = get_event_bus()
        if _bus is not None:
            star_loader = StarLoader(_bus, get_tool_registry(), redis, settings)
            await star_loader.load_dir(PROJECT_ROOT / settings.star_dir)

    # M7 暴露 StarLoader 单例(供 rest_plugin 调 reload_file;star_enable=False 时登记 None)
    from plugins.star_compat import set_star_loader
    set_star_loader(star_loader)

    # M5 工具系统:注册自研工具(get_persona/write_memory/reverse_infer_trigger/web_search)
    # + MCP client 连外部 server(无配置则降级,只用自研工具)
    from tools import get_tool_registry, register_builtin_tools
    from mcp_client import MCPClient, parse_mcp_servers
    registry = get_tool_registry()
    register_builtin_tools(registry, web_search_enable=settings.web_search_enable)
    mcp_servers = parse_mcp_servers(settings.mcp_servers) if settings.mcp_enable else []
    mcp_client = MCPClient()
    if mcp_servers:
        await mcp_client.connect_all(mcp_servers, registry)

    # 后台维护循环(审查#1 双栈去重:V3.0 与 V2.0 共用 Redis,衰减/遗忘只允许一栈跑。
    # BACKGROUND_MAINTENANCE 默认 False——V2.0 已在跑;V2.0 停转 V3.0 单栈时置 True)
    _bg_tasks: list[asyncio.Task] = []
    # NapCat 掉线监控(2026-09-15:QQ 登录态失效静默丢 8 天数据的教训;独立于后台维护开关。
    # 两级探测=WS 连接态 + WebUI QQ 登录态,offline 时 WARNING 日志 + 面板红色横幅)
    if settings.napcat_watch_enabled:
        from onebot.watch import start_watch_loop
        _bg_tasks.append(start_watch_loop(redis))
        logger.info("NapCat 掉线监控已启动(interval=%ss,webui_probe=%s)",
                    settings.napcat_watch_interval_sec,
                    bool(settings.napcat_webui_base and settings.napcat_webui_token))
    if settings.background_maintenance_enable:
        from mood.decay import start_decay_loop
        _bg_tasks.append(start_decay_loop(redis))
        # 记忆衰减循环(用进废退:forget_tick 后台定时跑,软遗忘+上限淘汰+物理清理+睡眠巩固)
        from memory.coordinator import start_forget_loop
        _bg_tasks.append(start_forget_loop())
    else:
        logger.info("后台维护循环未启用(BACKGROUND_MAINTENANCE=false;共用 Redis 场景由 V2.0 栈执行)")

    yield

    # 关闭:tick 调度器 → 后台循环 → MCP client → 插件 → 适配器
    if _tick_scheduler is not None:
        await _tick_scheduler.stop()
    for t in _bg_tasks:
        t.cancel()
    for t in _bg_tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
    if mcp_servers:
        await mcp_client.close_all()
    if star_loader is not None:
        await star_loader.unload_all()
    from plugins import shutdown_plugins
    await shutdown_plugins()
    # V3.0 适配器关闭(onebot 断 WS)
    from adapter import get_current_adapter, reset_adapter
    try:
        await (await get_current_adapter()).close()
    except Exception:
        logger.exception("adapter close 失败(忽略)")
    reset_adapter()


def create_app() -> FastAPI:
    """应用工厂:创建并配置 FastAPI 实例"""
    app = FastAPI(
        title="MyChat V3.0 Server",
        version="2.0.0",
        lifespan=lifespan,
    )

    # M7 Web 面板 CORS:允许 dashboard dev origin(cors_origins 配置,空则默认 localhost:5173)
    from fastapi.middleware.cors import CORSMiddleware
    _raw_origins = (settings.cors_origins or "").strip()
    _origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or [
        "http://localhost:5173", "http://127.0.0.1:5173"]
    app.add_middleware(CORSMiddleware, allow_origins=_origins,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    async def health():
        """健康检查端点(部署存活探测)。附带 QQ 凭证配置状态便于排障(不暴露值)"""
        return {
            "status": "ok",
            "service": "mychat-server-v3",
            "onebot_self_id": settings.onebot_self_id or "",
            "onebot_connected": __import__("onebot.ws_client", fromlist=["is_connected"]).is_connected(),
        }

    # V3.0 纯 OneBot(2026-08-17 精简):唯一入站 = OneBot 反向WS(/ws,NapCat 真人号连入)
    from onebot.ws_client import router as onebot_router
    app.include_router(onebot_router)
    logger.info("已挂载 OneBot 反向WS路由 /ws(self_id=%s)", settings.onebot_self_id)
    # 挂载评分/反推 REST 路由(M3,/api/v1/chat/.../score、/health、/score/reverse_infer/...)
    app.include_router(score_router)
    # 挂载记忆 REST 路由(M4,/api/v1/memory/... 查看/统计/遗忘/恢复/锁定)
    app.include_router(memory_router)
    # M7 挂载 Web 面板 REST 路由(chat 历史/mood 心情/plugin 插件/persona 人设/system 系统)
    app.include_router(chat_router)
    app.include_router(mood_router)
    app.include_router(plugin_router)
    app.include_router(persona_router)
    app.include_router(system_router)
    # M8 挂载代答/roleplay REST 路由(/api/v1/takeover/...、/api/v1/roleplay/...)
    app.include_router(takeover_router)
    app.include_router(roleplay_router)
    # M-vision 挂载图像理解 REST 路由(POST /api/v1/multimodal/vision 上传图→GLM 描述)
    app.include_router(multimodal_router)
    # M-tts 挂载 TTS 预览 REST 路由(POST /api/v1/tts/preview 音色试听,2026-08-04)
    app.include_router(tts_router)
    app.include_router(training_router)   # 训练前置工具(盲测基准/数据导出,2026-09-12)
    app.include_router(sticker_router)   # sticker_plus 配套:表情包库管理/文字表情渲染(2026-10-25)
    app.include_router(diary_router)   # dream 插件配套:做梦与日记查看/手动补跑(2026-10-26)
    app.include_router(worldbook_router)   # 世界书条目 CRUD/统计/重建(docs/09,2026-10-26)
    # M7e 静态托管前端构建产物 + SPA history mode 兜底(修子路由刷新 404);dist 不存在则跳过(dev 走 vite proxy)
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    from core.config import PROJECT_ROOT
    _dist = PROJECT_ROOT / "dashboard" / "dist"
    if _dist.is_dir():
        _dist_resolved = _dist.resolve()

        @app.get("/{full_path:path}")
        async def spa_serve(full_path: str):
            """SPA 静态托管 + history mode 兜底(替代 StaticFiles mount)。
            API/health/qq 路由由上方 include_router 先声明优先匹配,不被吞。
            dist 下真实文件(/assets/*.js 等)→ FileResponse 该文件;否则 → index.html(Vue Router 接管刷新/深链)。
            path traversal 防护:解析后必须仍在 _dist 下。"""
            target = (_dist / full_path).resolve()
            try:
                target.relative_to(_dist_resolved)
            except ValueError:
                raise HTTPException(status_code=404)
            if full_path and target.is_file():
                return FileResponse(str(target))
            return FileResponse(str(_dist / "index.html"))
    return app


app = create_app()
