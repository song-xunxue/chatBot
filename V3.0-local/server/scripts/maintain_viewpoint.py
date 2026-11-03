"""
维护脚本:清洗存量记忆里的系统腔称呼「用户/TA」→「他」(2026-11-03 视角修复配套)。
背景:人设卡 user_alias 为空时,encoder 旧版提炼 prompt 兜底"用户",产出过
"用户提示自己一直熬夜"类记忆;记忆 content 会注入 system prompt(legacy 全量模式)
并被世界书条目直搬——系统词污染她的口吻。代码层已修(encoder 称呼铁律+worldbook
normalize_viewpoint),本脚本负责存量数据一次性清洗。

清洗范围(只动 content/summary 文本,不动 tags/embedding/评分/时间):
  1. long_term: mychat:mem:{oid}:long (Hash, field=mid → MemoryItem JSON)
  2. core:      mychat:mem:{oid}:core (String, CoreFact JSON 数组)
  3. episodic:  mychat:mem:{oid}:episodic (ZSet, member=EpisodicEntry JSON)
  4. reflect:   mychat:mem:{oid}:reflect (List, {"reflection","ts"} JSON)
世界书条目不在此脚本范围——sync_* 已接 normalize_viewpoint,跑一次
rebuild_auto(幂等,manual 条目不动)即全部洗净。

用法(conda mychat,server 目录下):
  python -m scripts.maintain_viewpoint --oid <QQ号>            # dry-run 只预览
  python -m scripts.maintain_viewpoint --oid <QQ号> --apply    # 实际写入
  python -m scripts.maintain_viewpoint --oid <QQ号> --alias 主人 --apply
幂等:替换后不含目标词,重复执行第二轮 diff=0。

日期: 2026-11-03
"""
import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))   # server/app 进 sys.path(app 内部平级导入口径)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("maintain_viewpoint")

_WORD_RE = re.compile(r"用户|TA")


def _sub(text: str, alias: str) -> tuple[str, int]:
    """单段文本替换,返回(新文本, 替换次数);空串原样"""
    if not text:
        return text, 0
    out, n = _WORD_RE.subn(alias, text)
    return out, n


async def maintain(oid: str, alias: str, apply: bool) -> None:
    from storage.redis_client import get_redis
    import time as _t

    redis = await get_redis()
    total = {"long": 0, "core": 0, "episodic": 0, "reflect": 0}

    # 1.long_term(Hash: field=mid → MemoryItem JSON)
    long_key = f"mychat:mem:{oid}:long"
    for mid, raw in (await redis.hgetall(long_key)).items():
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        new, n = _sub(str(d.get("content", "") or ""), alias)
        if n:
            d["content"] = new
            if apply:
                await redis.hset(long_key, mid, json.dumps(d, ensure_ascii=False))
            total["long"] += n
            log.info(f"  [long/{mid}] x{n}: {str(d.get('content'))[:60]}")

    # 2.core(String: CoreFact JSON 数组)
    core_key = f"mychat:mem:{oid}:core"
    raw = await redis.get(core_key)
    if raw:
        try:
            facts = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            facts = []
        changed = False
        for f in facts if isinstance(facts, list) else []:
            new, n = _sub(str(f.get("content", "") or ""), alias)
            if n:
                f["content"] = new
                total["core"] += n
                changed = True
                log.info(f"  [core/{f.get('key', '?')}] x{n}: {new[:60]}")
        if changed and apply:
            await redis.set(core_key, json.dumps(facts, ensure_ascii=False))

    # 3.episodic(ZSet: member=EpisodicEntry JSON;member 含 summary,替换后需 rem+add 保 score)
    epi_key = f"mychat:mem:{oid}:episodic"
    for member, score in await redis.zrange(epi_key, 0, -1, withscores=True):
        try:
            d = json.loads(member)
        except (json.JSONDecodeError, TypeError):
            continue
        new, n = _sub(str(d.get("summary", "") or ""), alias)
        if n:
            d["summary"] = new
            if apply:
                await redis.zrem(epi_key, member)
                await redis.zadd(epi_key, {json.dumps(d, ensure_ascii=False): score})
            total["episodic"] += n
            log.info(f"  [epi/{d.get('id', '?')}] x{n}: {new[:60]}")

    # 4.reflect(List: {"reflection","ts"} JSON)
    ref_key = f"mychat:mem:{oid}:reflect"
    items = await redis.lrange(ref_key, 0, -1)
    for i, raw in enumerate(items):
        try:
            d = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        new, n = _sub(str(d.get("reflection", "") or ""), alias)
        if n:
            d["reflection"] = new
            if apply:
                await redis.lset(ref_key, i, json.dumps(d, ensure_ascii=False))
            total["reflect"] += n
            log.info(f"  [reflect#{i}] x{n}: {new[:60]}")

    mode = "APPLY(已写入)" if apply else "DRY-RUN(未写入,加 --apply 生效)"
    log.info(f"[{oid}] 替换统计 long={total['long']} core={total['core']} "
             f"episodic={total['episodic']} reflect={total['reflect']}  {mode} {_t.strftime('%H:%M:%S')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="清洗存量记忆的「用户/TA」系统腔称呼")
    ap.add_argument("--oid", required=True, help="对象 QQ 号")
    ap.add_argument("--alias", default="他", help="替换成的称呼(默认「他」;人设卡 user_alias 有值可传它)")
    ap.add_argument("--apply", action="store_true", help="实际写入(缺省 dry-run 只预览)")
    args = ap.parse_args()
    asyncio.run(maintain(args.oid, args.alias, args.apply))


if __name__ == "__main__":
    main()
