"""
数据整理脚本:删除 2026-09-25 之后的所有记忆/会话/评分/日记/状态数据(用户 2026-11-03
明确确认"删除9-25之后的所有记忆、会话等相关数据,我已确认")。
保留 9-25 之前的历史(含云端迁移的早期聊天与记忆)。

范围(按对象 oid 逐一处理,oid 来自 chat blocks 与 mem long 的实际键):
  1. 会话:chat blocks(ZSet score=start_ts>=cutoff 的 block)及各 block 的 msgs/msg 键;
     active_block 若失效则删;timelabel 删
  2. 记忆:long_term(created_ts>=cutoff 的条目+对应 vec 键);core 全清(CoreFact 无时间戳,
     现存内容均为近期对话提炼;备份可恢复);episodic(created_ts>=cutoff);reflect(ts>=cutoff)
  3. 评分:score:pos/neg 整键删(评分与会话绑定,金样本早已落 training 文件)
  4. 状态键:proactive:last / proactive:count:* / dream:done:* / journal:done:* /
     takeover:msgseq
  5. 日记:diary 日期 >=2026-09-25 的文件+索引+缓存(dream/journal 产物属于记忆延伸)
  6. 世界书:不在此脚本——删完记忆后跑一次 rebuild_auto,自动条目按残留记忆重建(manual 保留)

用法(conda mychat,server 目录下):
  python -m scripts.data_prune                 # dry-run 只统计预览
  python -m scripts.data_prune --apply         # 实际删除(不可逆!先确认备份存在)
幂等:第二轮被删范围已空,统计为 0。

日期: 2026-11-03
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("data_prune")

# cutoff:2026-09-25 00:00(本地时区)毫秒时间戳;diary 用 YYYYMMDD 整数口径
CUTOFF_MS = int(datetime(2026, 9, 25).timestamp() * 1000)
CUTOFF_SCORE = 20260925


def _s(x):
    return x.decode() if isinstance(x, bytes) else x


def _load(raw):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def prune_oid(redis, oid: str, apply: bool, diary_dir: Path | None) -> dict:
    """单对象清理:返回统计 dict(dry-run 只统计不写)"""
    st = {"blocks": 0, "msgs": 0, "long": 0, "core": 0, "episodic": 0,
          "reflect": 0, "score": 0, "state": 0, "diary": 0}

    # 1.会话 blocks(score=start_ts 毫秒):先收每个 block 的 mid(删 msgs zset 前收集),
    #   再一并删 msgs zset + msg hash + 索引区间,防孤儿
    bk = f"mychat:chat:{oid}:blocks"
    stale = await redis.zrangebyscore(bk, CUTOFF_MS, "+inf")
    st["blocks"] = len(stale)
    if apply and stale:
        pipe = redis.pipeline()
        orphan_mids: list[str] = []
        for bid in stale:
            mids = [_s(m) for m in await redis.zrange(f"mychat:block:{bid}:msgs", 0, -1)]
            orphan_mids.extend(mids)
            pipe.delete(f"mychat:block:{bid}:msgs")
        if orphan_mids:
            pipe.delete(*(f"mychat:msg:{mid}" for mid in orphan_mids))
            st["msgs"] = len(orphan_mids)
        pipe.zremrangebyscore(bk, CUTOFF_MS, "+inf")
        await pipe.execute()
        # active_block 失效则删(下次消息自动开新块)
        ab = f"mychat:chat:{oid}:active_block"
        if await redis.get(ab) in [_s(b) for b in stale]:
            await redis.delete(ab)

    # 2.long_term(created_ts>=cutoff)
    lk = f"mychat:mem:{oid}:long"
    for mid, raw in (await redis.hgetall(lk)).items():
        d = _load(raw)
        if d and int(d.get("created_ts", 0) or 0) >= CUTOFF_MS:
            st["long"] += 1
            if apply:
                await redis.hdel(lk, mid)
                await redis.delete(f"mychat:mem:{oid}:vec:{mid}")

    # 3.core(无时间戳,全清;备份可恢复)
    ck = f"mychat:mem:{oid}:core"
    if await redis.exists(ck):
        try:
            st["core"] = len(json.loads(await redis.get(ck)))
        except (json.JSONDecodeError, TypeError):
            st["core"] = 1
        if apply:
            await redis.delete(ck)

    # 4.episodic(created_ts>=cutoff)
    ek = f"mychat:mem:{oid}:episodic"
    for member in await redis.zrange(ek, 0, -1):
        d = _load(member)
        if d and int(d.get("created_ts", 0) or 0) >= CUTOFF_MS:
            st["episodic"] += 1
            if apply:
                await redis.zrem(ek, member)

    # 5.reflect(list: {"reflection","ts"})
    rk = f"mychat:mem:{oid}:reflect"
    items = await redis.lrange(rk, 0, -1)
    keep = []
    for raw in items:
        d = _load(raw)
        if d and int(d.get("ts", 0) or 0) >= CUTOFF_MS:
            st["reflect"] += 1
        else:
            keep.append(raw)
    if apply and st["reflect"]:
        await redis.delete(rk)
        if keep:
            await redis.rpush(rk, *keep)

    # 6.评分整键(会话绑定;金样本已落 training)
    for sk in (f"mychat:score:pos:{oid}", f"mychat:score:neg:{oid}"):
        if await redis.exists(sk):
            st["score"] += 1
            if apply:
                await redis.delete(sk)

    # 7.状态键
    state_keys = [f"mychat:proactive:last:{oid}", f"mychat:takeover:msgseq:{oid}",
                  f"mychat:timelabel:{oid}"]
    for pat in (f"mychat:proactive:count:{oid}:*", f"mychat:dream:done:{oid}:*",
                f"mychat:journal:done:{oid}:*"):
        async for k in redis.scan_iter(match=pat, count=200):
            state_keys.append(_s(k))
    st["state"] = len(state_keys)
    if apply and state_keys:
        await redis.delete(*state_keys)

    # 8.diary(文件+索引+缓存;>=2026-09-25 的日期)
    has_diary_index = await redis.exists("mychat:diary:index")
    if has_diary_index or (diary_dir and diary_dir.is_dir()):
        dates = [d for d in
                 [_s(x) for x in await redis.zrange("mychat:diary:index", 0, -1)]
                 if int(d.replace("-", "")) >= CUTOFF_SCORE]
        if diary_dir and diary_dir.is_dir():
            dates = sorted(set(dates) | {p.stem for p in diary_dir.glob("*.json")
                                         if p.stem[:4].isdigit()
                                         and int(p.stem.replace("-", "")) >= CUTOFF_SCORE})
        st["diary"] = len(dates)
        if apply and dates:
            pipe = redis.pipeline()
            for d in dates:
                pipe.zrem("mychat:diary:index", d)
                pipe.delete(f"mychat:diary:{d}")
            await pipe.execute()
            if diary_dir and diary_dir.is_dir():
                for d in dates:
                    (diary_dir / f"{d}.json").unlink(missing_ok=True)

    log.info(f"[{oid}] blocks={st['blocks']}(会话块) msgs 明细随块删 long={st['long']} core={st['core']}(全清) "
             f"episodic={st['episodic']} reflect={st['reflect']} score键={st['score']} "
             f"状态键={st['state']} diary={st['diary']}")
    return st


async def main(apply: bool) -> None:
    from storage.redis_client import get_redis
    from plugins.dream import storage as dream_storage

    redis = await get_redis()
    # oid 来源:chat blocks 与 mem long 的实际键(纯数字,排除 default/demo 幽灵)
    oids = set()
    async for k in redis.scan_iter(match="mychat:chat:*:blocks", count=200):
        oid = k.split(":")[2]
        if oid.isdigit():
            oids.add(oid)
    async for k in redis.scan_iter(match="mychat:mem:*:long", count=200):
        oid = k.split(":")[2]
        if oid.isdigit():
            oids.add(oid)
    log.info(f"cutoff=2026-09-25 00:00({CUTOFF_MS})  对象: {sorted(oids)}  模式: {'APPLY(将实际删除)' if apply else 'DRY-RUN(仅统计)'}")
    diary_dir = dream_storage.DIARY_DIR
    total = 0
    for oid in sorted(oids):
        st = await prune_oid(redis, oid, apply, diary_dir)
        total += sum(st.values())
    log.info(f"合计 {'已删除' if apply else '将删除'} {total} 项"
             + ("" if apply else "  (加 --apply 执行;删前请确认 backups/ 有最新备份)"))
    if apply:
        # 世界书自动条目按残留记忆重建(manual 保留)
        from memory.worldbook_store import rebuild_auto
        real = [o for o in sorted(oids) if o.isdigit()]
        r = await rebuild_auto(redis, real)
        log.info(f"世界书自动条目已按残留记忆重建: {r}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="删除 2026-09-25 之后的记忆/会话等数据(用户已确认)")
    ap.add_argument("--apply", action="store_true", help="实际删除(缺省 dry-run)")
    a = ap.parse_args()
    asyncio.run(main(a.apply))
