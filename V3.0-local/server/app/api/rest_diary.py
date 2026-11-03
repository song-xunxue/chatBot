"""
做梦与日记 REST 接口(dream 插件配套)
日记查看 + 手动补跑 + 管理(2026-11-01 起支持编辑/删除/手写/重提炼)。
存储走 plugins/dream/storage.py(文件+Redis 索引/缓存),
生成走 plugins/dream/service.run_dream / run_journal(素材→LLM→落盘→事件记忆)。

路由(prefix /api/v1,全部 X-Access-Token 鉴权,惯例同 rest_sticker.py):
  GET   /diary/list?limit=30   日记摘要列表(按日期倒序)[{date,tone,kind,excerpt}]
  GET   /diary/{date}          单日全量 entry(格式非法 400,查无 404)
  POST  /diary/run             手动跑一次(body {date? 默认今天, object_id?, kind? dream|journal 默认 dream})
  PUT   /diary/{date}          编辑日记(body {diary?, dream?, key_events?, dream_tone?, regen_memory?=true};
                               白名单字段 merge,保存后可选重新提炼事件记忆)
  DELETE /diary/{date}         删除日记(文件+索引+缓存三清,该日三种来源的日记事件记忆跟随删除)
  POST  /diary                 手写新增日记(body {date, diary, object_id?, key_events?};
                               kind=manual,同日期已有则覆盖,提炼 source=manual 事件记忆)
  POST  /diary/{date}/memory   对已有日记手动重新提炼事件记忆(编辑漏勾 regen 的兜底)

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:3 端点;手动跑不走 done 键门槛可重复补做(文件覆盖、事件记忆靠去重);
     object_id 缺省取最近会话兜底(做梦不发 QQ 消息,不需数字 QQ 号过滤);插件未加载时
     参数回退 service.DEFAULT_PARAMS
  2. oid 口径收紧(审查修复):显式与兜底解析出的 object_id 一律按 tick_object_ids
     同款过滤——纯数字 QQ 号才做,default/demo 等幽灵会话 400(其日记会污染
     文件+事件记忆+mood 三处数据)

2026-11-01
变更说明:
  1. 日记管理批次:dream/journal/manual 三种日记同库(entry.kind 区分,存量缺 kind=dream);
     run 支持 kind=journal 手动补写日常日记;新增 PUT 编辑(白名单字段+可选重提炼)/
     DELETE 删除(存储三清+记忆跟随)/POST 手写(manual,提炼 source=manual)/
     POST memory 手动重提炼;编辑走 service.extract_entry_facts 提炼收口
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
    """手动跑一次(调试/补做用)。body {date 可选(YYYY-MM-DD,默认今天), object_id 可选,
    kind 可选 dream(默认,做梦)|journal(写今天的日常日记)}。不走 done 键门槛,可重复补做:
    日记文件覆盖写,事件记忆走 extract_entry_facts 先删后写不累积。生成失败(无素材/
    LLM 不可用)→ 503;date 非法/未来日期 → 400(kind=journal 写今天,同样不许未来)"""
    redis = await get_redis()
    kind = str(body.get("kind", "") or "dream").strip().lower()
    if kind not in ("dream", "journal"):
        raise HTTPException(status_code=400, detail="kind 只支持 dream|journal")
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
        runner = dream_service.run_dream if kind == "dream" else dream_service.run_journal
        entry = await runner(redis, oid, target, params)
    except Exception as e:
        # service 内部各段已软失败,此处兜底网络层异常转 503,不让 500 裸奔
        logger.exception("diary 手动跑异常 kind=%s oid=%s date=%s", kind, oid, target)
        raise HTTPException(status_code=503, detail=f"生成失败(服务内部异常): {e}") from e
    if entry is None:
        raise HTTPException(status_code=503, detail="生成失败(无素材或LLM不可用)")
    return entry


# ================ 日记管理(2026-11-01:编辑/删除/手写/重提炼) ================

# PUT 可编辑字段白名单(mood_curve/object_id/created_ts 等生成数据与簿记字段不开放)
_EDITABLE_FIELDS = ("diary", "dream", "key_events", "dream_tone")


@router.put("/diary/{date}", dependencies=[Depends(verify_token)])
async def diary_update(date: str, body: dict = Body(...)):
    """编辑单日日记:白名单字段(diary/dream/key_events/dream_tone)merge 进现有 entry
    后保存;regen_memory 默认 true——保存后走 extract_entry_facts 重新提炼该日事件记忆
    (先删旧三种 source 再按 kind 写入,编辑内容即时反映到记忆)。查无 404;
    key_events/dream 非该 kind 的字段传了就存(journal/manual 无 dream 字段时存了也无妨,
    面板不渲染);diary 编辑为空白 → 400(日记不能为空)"""
    _parse_date(date)
    redis = await get_redis()
    entry = await dream_storage.load_entry(redis, date)
    if entry is None:
        raise HTTPException(status_code=404, detail="该日期没有日记")
    entry.setdefault("kind", "dream")   # 存量日记(2026-11-01 前无 kind 字段)编辑时规范化
    changed = False
    for field in _EDITABLE_FIELDS:
        if field not in body:
            continue
        val = body.get(field)
        if field == "key_events":
            if val is not None and not isinstance(val, list):
                raise HTTPException(status_code=400, detail="key_events 须为字符串数组")
            entry[field] = [str(x).strip() for x in (val or []) if str(x).strip()]
        elif field == "diary":
            text = str(val or "").strip()
            if not text:
                raise HTTPException(status_code=400, detail="日记正文不能为空")
            entry[field] = text
        else:
            entry[field] = str(val or "").strip()
        changed = True
    if not changed:
        raise HTTPException(status_code=400, detail="没有可编辑字段(diary/dream/key_events/dream_tone)")
    params = await _dream_params(str(entry.get("object_id", "") or "") or None)
    await dream_storage.save_entry(redis, entry, int(params.get("keep_days") or 90))
    regen = body.get("regen_memory", True)
    regen = False if str(regen).lower() in ("false", "0", "no") else bool(regen)
    if regen:
        await dream_service.extract_entry_facts(redis, str(entry.get("object_id", "") or ""), entry,
                                                int(params.get("keep_days") or 90))
    return entry


@router.delete("/diary/{date}", dependencies=[Depends(verify_token)])
async def diary_delete(date: str):
    """删除单日日记:存储三清(文件+索引+缓存)+该日三种来源(diary/journal/manual)的
    事件记忆跟随删除(记忆与日记保持一致,防"日记删了事实永存")。查无 404"""
    _parse_date(date)
    redis = await get_redis()
    entry = await dream_storage.load_entry(redis, date)
    if entry is None:
        raise HTTPException(status_code=404, detail="该日期没有日记")
    oid = str(entry.get("object_id", "") or "")
    removed = await dream_storage.delete_entry(redis, date)
    if oid:
        # keep_days 给超大值 → cutoff 远早于一切日期,等价于只删"该日"的事实
        from datetime import date as _date
        await dream_service._prune_diary_facts(redis, oid, _date.fromisoformat(date),
                                               99999, sources=dream_service._DIARY_SOURCES)
    return {"deleted": bool(removed), "memory_pruned": bool(oid)}


@router.post("/diary", dependencies=[Depends(verify_token)])
async def diary_create(body: dict = Body(...)):
    """手写新增一篇日记(kind=manual):body {date 必填, diary 必填非空, object_id 可选,
    key_events 可选字符串数组}。同日期已有日记(梦/日常)会被覆盖——响应带 overwritten
    提示;保存即提炼事件记忆(source=manual,日期标签同步落 tags)。object_id 兜底与
    补跑同口径(纯数字 QQ 号);手写的日记同样受 keep_days 过期清理"""
    redis = await get_redis()
    text = str(body.get("diary", "") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="日记正文不能为空")
    target = _parse_date(body.get("date"))
    today = dream_service._now().date()
    if target > today:
        raise HTTPException(status_code=400, detail="日期不能是未来")
    oid = await _resolve_object_id(redis, str(body.get("object_id", "") or ""))
    existing = await dream_storage.load_entry(redis, target.strftime("%Y-%m-%d"))
    params = await _dream_params(oid)
    key_events = body.get("key_events")
    if key_events is not None and not isinstance(key_events, list):
        raise HTTPException(status_code=400, detail="key_events 须为字符串数组")
    entry = await dream_service.save_manual_entry(redis, oid, target, text, params,
                                                  key_events=key_events)
    return {"entry": entry, "overwritten": existing is not None}


@router.post("/diary/{date}/memory", dependencies=[Depends(verify_token)])
async def diary_regen_memory(date: str):
    """对已有日记手动重新提炼事件记忆(编辑保存时漏勾 regen_memory 的兜底入口)。
    走 extract_entry_facts(先删该日旧三种 source 再按 kind 写入)。查无 404"""
    _parse_date(date)
    redis = await get_redis()
    entry = await dream_storage.load_entry(redis, date)
    if entry is None:
        raise HTTPException(status_code=404, detail="该日期没有日记")
    oid = str(entry.get("object_id", "") or "")
    if not oid:
        raise HTTPException(status_code=400, detail="entry 缺 object_id,无法定位记忆归属")
    params = await _dream_params(oid)
    await dream_service.extract_entry_facts(redis, oid, entry, int(params.get("keep_days") or 90))
    return {"ok": True, "kind": str(entry.get("kind", "") or "dream")}
