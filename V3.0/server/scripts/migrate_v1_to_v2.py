"""
V1.0 → V2.0 聊天记录字段迁移脚本(docs/02 §13)

V1.0 用扁平 List(mychat:chat:{oid}),V2.0 用 block 三层(会话→blocks→messages)。
本脚本把 V1.0 List 历史一次性迁移到 V2.0 block 结构:

迁移规则(docs/02 §13):
  1. 遍历每个 object_id 的 V1.0 mychat:chat:{oid} List;
  2. 按相邻消息 ts 间隔 > block_silence_min(默认 10min)切分 block;
  3. 每条消息 mid 重写为 UUID(弃 V1.0 List 索引),挂入对应 block;
  4. score 四元组(score_base/mood_at_score/mood_bias/score)历史消息无法追溯,统一留空;
  5. roleplay List(mychat:chat_roleplay:{oid})同理迁到隔离前缀 block 三层。

字段映射:
  - V1.0 role(user/assistant/system)→ V2.0 sender:assistant→ai(V2.0 _SENDER_TO_ROLE 反向,
    ai 映射回 assistant),user/system 不变。
  - V1.0 roleplay role(user/assistant)→ V2.0 roleplay role(直接保留)。

用法:
  # dry-run(默认,只打印迁移计划不写)
  python scripts/migrate_v1_to_v2.py --v1-redis redis://<v1-host>:6379/0 --v2-redis redis://<v2-host>:6379/0
  # 实跑
  python scripts/migrate_v1_to_v2.py ... --apply

说明:V2.0 默认部署用独立新 redis(mychat-redis-v2),无 V1.0 数据需迁,故通常无需运行本脚本。
      仅当要保留 V1.0 旧对话历史时,把 --v1-redis 指向旧 redis(V1.0 的 mychat-redis)执行。

作者: 李文煜
日期: 2026-07-01
"""
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# 让脚本能 import storage.chat_store 的键构造函数(脚本位于 server/scripts/,app 在 server/app/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from redis.asyncio import Redis  # 异步 Redis 客户端

# V1.0 → V2.0 sender 映射(V2.0 sender:user/ai/proxy/system;ai 对应 LLM assistant)
_ROLE_TO_SENDER = {"user": "user", "assistant": "ai", "system": "system"}
# 静默分组阈值(分钟),与 config.block_silence_min 默认一致;超时则切新 block
SILENCE_MIN = 10


# —— V2.0 Redis 键构造(镜像 storage/chat_store.py,保持 schema 一致)——
def blocks_key(oid: str) -> str:
    return f"mychat:chat:{oid}:blocks"


def block_key(bid: str) -> str:
    return f"mychat:block:{bid}"


def msgs_key(bid: str) -> str:
    return f"mychat:block:{bid}:msgs"


def msg_key(mid: str) -> str:
    return f"mychat:msg:{mid}"


def active_key(oid: str) -> str:
    return f"mychat:chat:{oid}:active_block"


def rp_blocks_key(oid: str) -> str:
    return f"mychat:block_roleplay:{oid}:blocks"


def rp_block_key(bid: str) -> str:
    return f"mychat:block_roleplay:{bid}"


def rp_msgs_key(bid: str) -> str:
    return f"mychat:block_roleplay:{bid}:msgs"


def rp_msg_key(mid: str) -> str:
    return f"mychat:msg_roleplay:{mid}"


def rp_active_key(oid: str) -> str:
    return f"mychat:roleplay:{oid}:active_block"


def _gen_mid() -> str:
    return uuid.uuid4().hex


async def _scan_v1_object_ids(redis: Redis) -> list[str]:
    """扫 V1.0 mychat:chat:{oid} List 键,排除 V2.0 的 :blocks/:active_block 后缀键"""
    oids = []
    async for key in redis.scan_iter(match="mychat:chat:*"):
        k = key if isinstance(key, str) else key.decode()
        if k.endswith(":blocks") or k.endswith(":active_block"):
            continue  # V2.0 block 键,非 V1.0 List
        if await redis.type(k) != "list":
            continue  # 只迁 List 类型(V1.0)
        oids.append(k.split(":")[2])  # mychat:chat:{oid} → oid
    return sorted(set(oids))


async def _scan_v1_roleplay_ids(redis: Redis) -> list[str]:
    """扫 V1.0 mychat:chat_roleplay:{oid} List 键"""
    oids = []
    async for key in redis.scan_iter(match="mychat:chat_roleplay:*"):
        k = key if isinstance(key, str) else key.decode()
        if await redis.type(k) != "list":
            continue
        oids.append(k.split(":")[2])
    return sorted(set(oids))


def _split_blocks(items: list[dict]) -> list[list[dict]]:
    """按相邻 ts 间隔 > SILENCE_MIN 切 block(每段一个 block)。items 需先按 ts 正序"""
    if not items:
        return []
    blocks = [[items[0]]]
    for prev, cur in zip(items, items[1:]):
        gap = int(cur.get("ts", 0) or 0) - int(prev.get("ts", 0) or 0)
        if gap > SILENCE_MIN * 60_000:
            blocks.append([cur])  # 静默超阈值,开新 block
        else:
            blocks[-1].append(cur)
    return blocks


async def _migrate_live(redis: Redis, oid: str, *, apply: bool) -> dict:
    """迁单个 object_id 的 V1.0 List → V2.0 block 三层。
    按相邻 ts 间隔切 block,每条消息 mid 重写为 UUID,score 四元组留空(历史无追溯)。"""
    raw_items = await redis.lrange(f"mychat:chat:{oid}", 0, -1)
    items = []
    for raw in raw_items:
        try:
            items.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
    items.sort(key=lambda d: int(d.get("ts", 0) or 0))
    blocks = _split_blocks(items)
    stats = {"oid": oid, "messages": len(items), "blocks": len(blocks)}
    if not apply or not items:
        return stats
    last_bid = ""
    pipe = redis.pipeline()
    for idx, seg in enumerate(blocks):
        bid = _gen_mid()
        if idx == len(blocks) - 1:
            last_bid = bid
        start_ts = int(seg[0].get("ts", 0) or 0)
        end_ts = int(seg[-1].get("ts", 0) or 0)
        is_last = idx == len(blocks) - 1
        pipe.hset(block_key(bid), mapping={
            "block_id": bid, "object_id": oid,
            "start_ts": start_ts, "end_ts": end_ts,
            "status": "open" if is_last else "closed",
            "source": "live", "summary": "",
            "close_reason": "" if is_last else "silence",
        })
        pipe.zadd(blocks_key(oid), {bid: start_ts})
        for d in seg:
            mid = _gen_mid()
            sender = _ROLE_TO_SENDER.get(str(d.get("role", "")), "user")
            pipe.hset(msg_key(mid), mapping={
                "mid": mid, "block_id": bid, "object_id": oid,
                "sender": sender, "content": str(d.get("content", "")),
                "rich": "", "ts": int(d.get("ts", 0) or 0),
                "source": "live", "status": "active",
                "score_base": "", "mood_at_score": "", "mood_bias": "", "score": "",
            })
            pipe.zadd(msgs_key(bid), {mid: int(d.get("ts", 0) or 0)})
    if last_bid:
        pipe.set(active_key(oid), last_bid)
    await pipe.execute()
    return stats


async def _migrate_roleplay(redis: Redis, oid: str, *, apply: bool) -> dict:
    """迁单个 object_id 的 V1.0 roleplay List → V2.0 roleplay block 三层(单 block 容纳所有样本)"""
    raw_items = await redis.lrange(f"mychat:chat_roleplay:{oid}", 0, -1)
    items = []
    for raw in raw_items:
        try:
            items.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
    items.sort(key=lambda d: int(d.get("ts", 0) or 0))
    stats = {"oid": oid, "samples": len(items)}
    if not apply or not items:
        return stats
    bid = _gen_mid()
    start_ts = int(items[0].get("ts", 0) or 0)
    end_ts = int(items[-1].get("ts", 0) or 0)
    pipe = redis.pipeline()
    pipe.hset(rp_block_key(bid), mapping={
        "block_id": bid, "object_id": oid,
        "start_ts": start_ts, "end_ts": end_ts,
        "status": "open", "source": "roleplay", "summary": "", "close_reason": "",
    })
    pipe.zadd(rp_blocks_key(oid), {bid: start_ts})
    for d in items:
        mid = _gen_mid()
        pipe.hset(rp_msg_key(mid), mapping={
            "mid": mid, "block_id": bid, "object_id": oid,
            "role": str(d.get("role", "")), "content": str(d.get("content", "")),
            "ts": int(d.get("ts", 0) or 0), "source": "roleplay", "status": "active",
        })
        pipe.zadd(rp_msgs_key(bid), {mid: int(d.get("ts", 0) or 0)})
    pipe.set(rp_active_key(oid), bid)
    await pipe.execute()
    return stats


async def main() -> int:
    parser = argparse.ArgumentParser(description="V1.0 → V2.0 聊天记录迁移(docs/02 §13)")
    parser.add_argument("--v1-redis", required=True, help="V1.0 redis URL(源,如 redis://10.0.0.1:6379/0)")
    parser.add_argument("--v2-redis", required=True, help="V2.0 redis URL(目标)")
    parser.add_argument("--apply", action="store_true", help="实际写入(默认 dry-run 只打印计划)")
    args = parser.parse_args()

    # 同一脚本连两个 redis(读 V1,写 V2);若同实例则两 URL 指同库亦可
    v1 = Redis.from_url(args.v1_redis, decode_responses=True)
    v2 = Redis.from_url(args.v2_redis, decode_responses=True)
    mode = "APPLY(实写)" if args.apply else "DRY-RUN(只打印,加 --apply 实跑)"

    print(f"===== V1.0 → V2.0 迁移 [{mode}] =====")
    live_oids = await _scan_v1_object_ids(v1)
    rp_oids = await _scan_v1_roleplay_ids(v1)
    print(f"V1.0 live 会话数:{len(live_oids)}  roleplay 会话数:{len(rp_oids)}")

    total_msgs = 0
    for oid in live_oids:
        st = await _migrate_live(v2, oid, apply=args.apply)
        total_msgs += st["messages"]
        print(f"  [live]  oid={oid}  消息={st['messages']}  blocks={st['blocks']}")
    total_rp = 0
    for oid in rp_oids:
        st = await _migrate_roleplay(v2, oid, apply=args.apply)
        total_rp += st["samples"]
        print(f"  [roleplay] oid={oid}  样本={st['samples']}")

    print(f"===== 合计:live 消息 {total_msgs} 条,roleplay 样本 {total_rp} 条 =====")
    if not args.apply:
        print("提示:本次为 DRY-RUN 未写入。确认无误后加 --apply 实跑。")
    await v1.aclose()
    await v2.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
