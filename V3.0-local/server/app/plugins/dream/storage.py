"""
日记/梦的落盘存储(文件 + Redis 索引/缓存)
DIARY_DIR 只在本模块定义一次;其它模块一律 `from plugins.dream import storage as dream_storage`
后用 `dream_storage.DIARY_DIR` 属性访问,方便测试 monkeypatch 换临时目录。
文件布局:DIARY_DIR/<YYYY-MM-DD>.json(entry 全量,ensure_ascii=False + indent=2,原子写);
Redis:索引 mychat:diary:index(ZSET,member=日期串,score=YYYYMMDD 整数)+ 缓存 mychat:diary:{date}
(String 存 entry JSON,TTL=keep_days 天+1 天宽限)。文件读写异常一律 log + 降级,不外抛。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:save_entry(落盘+ZADD+SET EX)/load_entry(缓存→文件→None)/list_dates(倒序)/
     load_summaries({date,tone,excerpt})/cleanup(过期文件+索引+缓存三清)

2026-10-27
变更说明:
  1. low 项修复:原子写失败即删 .tmp 不留残骸;cleanup 增第 3 步扫 *.json.tmp 残骸
     (此前 tmp 无任何清理路径,进程被杀一次即永久残留)
"""
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from redis.asyncio import Redis

from core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# 日记目录(项目根/server/data/diary,与 stickers/training 同级;persona/store.py 同款拼法)
DIARY_DIR: Path = PROJECT_ROOT / "server" / "data" / "diary"

# Redis 键:日期索引(ZSET)与单日缓存(String)
_K_INDEX = "mychat:diary:index"
_K_ENTRY = "mychat:diary:{date}"

# 合法日记文件名(YYYY-MM-DD.json),cleanup 时跳过奇怪文件
_DATE_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date_score(date_str: str) -> int:
    """日期串(YYYY-MM-DD)→ ZSET score(YYYYMMDD 整数,支持按日期范围清理)"""
    return int(date_str.replace("-", ""))


def _s(x) -> str:
    """Redis 返回值宽容转 str:真实客户端 decode_responses=True 返回 str,
    fakeredis(测试用)返回 bytes——统一解一层,两边都能跑(chat_store 同款防御)"""
    return x.decode() if isinstance(x, bytes) else x


def _entry_path(date_str: str) -> Path:
    """单日日记文件路径"""
    return DIARY_DIR / f"{date_str}.json"


def _write_json_atomic(path: Path, data: dict) -> None:
    """原子写:先写 .tmp 再 os.replace,防进程中断留下半截 JSON 被读到;
    写失败即删 .tmp 不留残骸(进程被杀遗留的由 cleanup 兜底扫除)"""
    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            # ensure_ascii=False 中文原样落盘;indent=2 便于人直接打开看
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)   # unlink 失败(如文件被占用)也不再放大异常
        except OSError:
            pass
        raise


async def save_entry(redis: Redis, entry: dict, keep_days: int) -> None:
    """落盘 + ZADD 索引 + SET 缓存(TTL=keep_days*86400+86400 宽限一天)。
    落盘失败只 log 不外抛(索引/缓存也不写,保证三者一致:有索引必有文件)。"""
    date_str = str(entry.get("date", "") or "")
    if not _DATE_FILE_RE.match(date_str):
        logger.warning("diary save_entry 缺 date/格式非法(date=%r),跳过保存", date_str)
        return
    try:
        _write_json_atomic(_entry_path(date_str), entry)
    except Exception:
        logger.exception("diary 落盘失败 date=%s(软失败)", date_str)
        return
    ttl = int(keep_days) * 86400 + 86400
    payload = json.dumps(entry, ensure_ascii=False)
    # 索引 member=日期串、score=YYYYMMDD;缓存 String 带 TTL,与文件内容一致
    await redis.zadd(_K_INDEX, {date_str: _date_score(date_str)})
    await redis.set(_K_ENTRY.format(date=date_str), payload, ex=ttl)


async def load_entry(redis: Redis, date_str: str) -> dict | None:
    """读单日 entry:缓存 → 文件 → None。缓存损坏回退文件;文件读失败只 log 返 None。
    (缓存 miss 且文件命中时不回填缓存——面板读频率低,文件读足够,免得造无 TTL 的常驻键)"""
    raw = await redis.get(_K_ENTRY.format(date=date_str))
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            logger.warning("diary 缓存非对象 date=%s,回退读文件", date_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning("diary 缓存损坏 date=%s,回退读文件", date_str)
    try:
        path = _entry_path(date_str)
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.exception("diary 读文件失败 date=%s(返回 None)", date_str)
        return None


async def list_dates(redis: Redis, limit: int = 30) -> list[str]:
    """按日期倒序列已存日记日期(ZREVRANGE;limit clamp 到 [1,365] 防面板传 0/负数/巨数)"""
    try:
        limit = max(1, min(365, int(limit)))
    except (TypeError, ValueError):
        limit = 30
    return [_s(d) for d in await redis.zrevrange(_K_INDEX, 0, limit - 1)]


async def load_summaries(redis: Redis, limit: int = 30) -> list[dict]:
    """按日期倒序逐日读 entry,产出摘要列表 [{"date","tone","excerpt"}]。
    excerpt=diary 前 60 字,超长加"…";读不到的日期跳过(文件被手动删时不挡列表)。"""
    out: list[dict] = []
    for date_str in await list_dates(redis, limit=limit):
        entry = await load_entry(redis, date_str)
        if not entry:
            continue
        diary = str(entry.get("diary", "") or "")
        excerpt = diary[:60] + ("…" if len(diary) > 60 else "")
        out.append({"date": date_str, "tone": entry.get("dream_tone", ""), "excerpt": excerpt})
    return out


async def cleanup(redis: Redis, keep_days: int, today: date | None = None) -> None:
    """清理过期日记(今天-keep_days 之前):删过期文件 + ZREMRANGEBYSCORE 索引 + DEL 对应缓存。
    三类清理各自软失败(只 log);today 可注入便于测试,缺省用当前日期。"""
    try:
        try:
            # 下限兜底 7 天(审查修复):keep_days 被写成 0/负数时 cutoff>=今天,
            # 一次清理会物理删光全部历史日记(文件 unlink 不可逆)
            keep_days = max(7, int(keep_days))
        except (TypeError, ValueError):
            keep_days = 90
        cutoff = (today or datetime.now().date()) - timedelta(days=keep_days)
        cutoff_score = int(cutoff.strftime("%Y%m%d"))
        removed = 0
        # 过期口径:日期严格小于 cutoff(=今天-keep_days),cutoff 当天保留
        # 1)先取索引里的过期成员(供删缓存),再 ZREMRANGEBYSCORE 清索引
        expired = [_s(d) for d in await redis.zrangebyscore(_K_INDEX, "-inf", cutoff_score - 1)]
        if expired:
            pipe = redis.pipeline()
            for d in expired:
                pipe.delete(_K_ENTRY.format(date=d))   # 同步删对应缓存键
            pipe.zremrangebyscore(_K_INDEX, "-inf", cutoff_score - 1)
            await pipe.execute()
            removed += len(expired)
        # 2)删过期文件(索引可能已失联的孤儿文件一并按文件名日期判)
        try:
            if DIARY_DIR.is_dir():
                for path in DIARY_DIR.glob("*.json"):
                    stem = path.stem
                    if _DATE_FILE_RE.match(stem) and _date_score(stem) < cutoff_score:
                        path.unlink(missing_ok=True)
                        removed += 1
        except Exception:
            logger.exception("diary cleanup 删文件失败(索引/缓存已清,继续)")
        # 3)扫 .json.tmp 残骸:原子写中途进程被杀遗留的半截文件,不可用,直接删
        #   (low 项修复:此前 tmp 无任何清理路径,失败一次就永久残留)
        try:
            if DIARY_DIR.is_dir():
                for path in DIARY_DIR.glob("*.json.tmp"):
                    path.unlink(missing_ok=True)
                    removed += 1
        except Exception:
            logger.exception("diary cleanup 扫 .tmp 残骸失败(软失败,继续)")
        if removed:
            logger.info("diary cleanup 已清理 %d 条过期日记(cutoff=%s)", removed, cutoff.strftime("%Y-%m-%d"))
    except Exception:
        logger.exception("diary cleanup 失败(软失败,不影响做梦主流程)")
