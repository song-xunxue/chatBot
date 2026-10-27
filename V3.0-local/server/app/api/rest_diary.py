"""
做梦与日记 REST 接口(dream 插件配套)
日记查看 + 手动补跑。存储走 plugins/dream/storage.py(文件+Redis 索引/缓存),
生成走 plugins/dream/service.run_dream(素材→LLM→落盘→事件记忆→mood 偏移)。

路由(prefix /api/v1,全部 X-Access-Token 鉴权,惯例同 rest_sticker.py):
  GET   /diary/list?limit=30   日记摘要列表(按日期倒序)[{date,tone,excerpt}]
  GET   /diary/{date}          单日全量 entry(格式非法 400,查无 404)
  POST  /diary/run             手动跑一次做梦(body {date 可选默认今天, object_id 可选默认最近会话})

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:3 端点;手动跑不走 done 键门槛可重复补做(文件覆盖、事件记忆靠去重);
     object_id 缺省取最近会话兜底(做梦不发 QQ 消息,不需数字 QQ 号过滤);插件未加载时
     参数回退 service.DEFAULT_PARAMS
  2. oid 口径收紧(审查修复):显式与兜底解析出的 object_id 一律按 tick_object_ids
     同款过滤——纯数字 QQ 号才做,default/demo 等幽灵会话 400(其日记会污染
     文件+事件记忆+mood 三处数据)
"""
import logging
import re
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException

from api._auth import verify_token
from plugins import get_plugin_manager
from plugins.dream import service as dream_service
from plugins.dream import storage as dream_storage
from storage import chat_store
from storage.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["diary"])

# 合法日期串(严格 YYYY-MM-DD,再过 strptime 校验真实日历日)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(raw) -> date:
    """校验并解析 YYYY-MM-DD;格式非法/非真实日期 → 400"""
    s = str(raw or "").strip()
    if not _DATE_RE.match(s):
        raise HTTPException(status_code=400, detail="日期格式须为 YYYY-MM-DD")
    try:
        # strptime:严格日历校验(如 2026-02-30 会抛 ValueError)
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as e:
        raise HTTPException(status_code=400, detail="日期非法(须为真实日期)") from e


def _valid_dream_oid(cand: str) -> bool:
    """真实对话对象判定(对齐 main.tick_object_ids 口径):纯数字 QQ 号。
    default/demo 等幽灵会话不做梦——否则会给它们写日记文件+source=diary 事件记忆
    +mood 偏移,污染三处数据"""
    return bool(cand) and cand != "default" and cand.isascii() and cand.isdigit()


async def _resolve_object_id(redis, raw_oid: str) -> str:
    """object_id 兜底:显式传入优先;缺省取最近会话中首个合法 oid。
    显式传入非数字/幽灵会话 → 400(带提示);取不到 → 400"""
    oid = str(raw_oid or "").strip()
    if oid:
        if not _valid_dream_oid(oid):
            raise HTTPException(status_code=400, detail="object_id 须为真实 QQ 号(default 等占位会话不做梦)")
        return oid
    sessions = await chat_store.list_recent_sessions(redis, limit=50)
    for s in sessions:
        cand = str(s.get("object_id", "") or "").strip()
        if _valid_dream_oid(cand):
            return cand
    raise HTTPException(status_code=400, detail="无法确定 object_id,请显式传入")


async def _dream_params(oid: str) -> dict:
    """取 dream 插件参数:插件已加载走 manager.get_params(config_schema 默认+按对象覆盖合并);
    未加载(插件系统关/未发现)回退 service.DEFAULT_PARAMS(REST 手动跑不依赖插件开关)"""
    params = dict(dream_service.DEFAULT_PARAMS)
    manager = get_plugin_manager()
    if manager is not None and manager.get_manifest("dream") is not None:
        try:
            params.update(await manager.get_params("dream", oid))
        except Exception:
            logger.warning("dream 取插件参数失败,回退默认参数", exc_info=True)
    return params


@router.get("/diary/list", dependencies=[Depends(verify_token)])
async def diary_list(limit: int = 30):
    """日记摘要列表(按日期倒序):[{date, tone, excerpt}],供面板日记列表页"""
    redis = await get_redis()
    return {"items": await dream_storage.load_summaries(redis, limit=limit)}


@router.get("/diary/{date}", dependencies=[Depends(verify_token)])
async def diary_detail(date: str):
    """单日日记全量 entry(dream/diary/mood_curve/key_events/dream_tone/...)。
    格式非法 → 400;查无(缓存与文件都没有)→ 404。
    注意须声明在 GET /diary/list 之后(更具体的静态段路由先注册优先匹配)"""
    _parse_date(date)
    redis = await get_redis()
    entry = await dream_storage.load_entry(redis, date)
    if entry is None:
        raise HTTPException(status_code=404, detail="该日期没有日记")
    return entry


@router.post("/diary/run", dependencies=[Depends(verify_token)])
async def diary_run(body: dict = Body(...)):
    """手动跑一次做梦(调试/补做用)。body {date 可选(YYYY-MM-DD,默认今天),
    object_id 可选(默认最近会话)}。不走 done 键门槛,可重复补做:日记文件覆盖写,
    事件记忆靠 coordinator 去重不写重。生成失败(无素材/LLM 不可用)→ 503;
    date 非法/未来日期 → 400"""
    redis = await get_redis()
    raw_date = body.get("date")
    today = dream_service._now().date()
    if raw_date in (None, ""):
        target = today
    else:
        target = _parse_date(raw_date)
    if target > today:
        raise HTTPException(status_code=400, detail="日期不能是未来(还没发生的事做不了梦)")
    oid = await _resolve_object_id(redis, str(body.get("object_id", "") or ""))
    params = await _dream_params(oid)
    try:
        entry = await dream_service.run_dream(redis, oid, target, params)
    except Exception as e:
        # service 内部各段已软失败,此处兜底网络层异常转 503,不让 500 裸奔
        logger.exception("dream 手动跑异常 oid=%s date=%s", oid, target)
        raise HTTPException(status_code=503, detail=f"生成失败(服务内部异常): {e}") from e
    if entry is None:
        raise HTTPException(status_code=503, detail="生成失败(无素材或LLM不可用)")
    return entry
