"""
QQ 掉线期历史消息回填(2026-09-15 数据恢复专项)

背景:接管号 1145077465 登录态 09-08 前后失效,至 09-15 重登期间的消息未落库(WS 连着但
QQ 离线,事件流不达服务器)。QQNT 重登后同步了完整好友聊天历史,经 NapCat HTTP 接口
get_friend_msg_history 拉取(~/ChatBot-V3 服务器 /tmp/hist_all.json,241 条去重后),
本脚本把它们按既有语义灌回 Redis。

落库语义(与 takeover.record_manual_reply / ws_client 静默直录完全对齐):
  - 用户消息(2690468347 发)  → sender=user  source=live
  - 小号消息(1145077465 发,全为手动) → sender=proxy source=manual;
    文本非占位 → pos 样本队列 source='manual' score=100(黄金标准,同 _collect_sample 格式)
  - 占位约定: image→[图片] face→[表情] record→[语音] forward→[转发] file→[文件] video→[视频]

块结构(关键):open_or_get_block 对旧 ts 恒并入当前块(ts-end_ts 为负不触发拆块),直接灌
会把全部历史塞进 09-15 活跃块——故先摘 active 指针,时间正序灌入让 5h 静默间隔自然分块,
结束后恢复原 active(真最新块),回填尾巴块手工置 closed(不走 close_block,防 end_ts 拉到 now)。

去重:与库内已有消息 (sender, content, |Δts|<120s) 匹配则跳过(09-07 测试 2 条 + 今日已录消息)。

用法(服务器上):
  docker cp /tmp/hist_all.json mychat-server-v3:/tmp/
  docker cp backfill_qq_history.py mychat-server-v3:/tmp/
  sudo docker exec mychat-server-v3 python /tmp/backfill_qq_history.py

作者: 李文煜
日期: 2026-09-15
"""
import asyncio
import json
import sys

sys.path.insert(0, "/app/server")   # 容器内应用代码根(main.py/storage/ 所在)

from core.config import settings          # noqa: E402
from storage import chat_store            # noqa: E402
from storage.redis_client import get_redis  # noqa: E402

OID = "2690468347"          # 用户主号(会话 object_id)
BOT_QQ = 1145077465         # 接管号(小号自己发的=手动回复)
HIST_PATH = "/tmp/hist_all.json"

# 纯媒体占位(与 score/service._PLACEHOLDER_TEXTS 一致;占位不入金样本)
PLACEHOLDERS = {"[语音]", "[图片]", "[表情]", "[转发]", "[文件]", "[视频]", "[非文本消息]"}
# 段类型 → 占位文本(与 ws_client._MEDIA_PLACEHOLDERS 对齐)
SEG_PLACEHOLDER = {"image": "[图片]", "face": "[表情]", "record": "[语音]",
                   "forward": "[转发]", "file": "[文件]", "video": "[视频]"}
DEDUP_WINDOW_MS = 120_000   # 同 sender 同内容 2 分钟内视为重复

K_BLOCKS = f"mychat:chat:{OID}:blocks"
K_ACTIVE = f"mychat:chat:{OID}:active_block"
K_POS = f"mychat:score:pos:{OID}"


def extract_content(msg: dict) -> str:
    """提取消息可入库文本:文本段拼接优先;纯媒体给占位(同 ws_client 约定)。"""
    segs = msg.get("message") or []
    texts = [str(s.get("data", {}).get("text", "") or "")
             for s in segs if isinstance(s, dict) and s.get("type") == "text"]
    text = "\n".join(t for t in texts if t).strip()
    if text:
        return text
    for s in segs:
        if isinstance(s, dict) and s.get("type") in SEG_PLACEHOLDER:
            return SEG_PLACEHOLDER[s["type"]]
    return "[非文本消息]" if segs else ""


async def load_existing(redis) -> list[tuple[str, str, int]]:
    """读库内全部已有消息,构建去重基准 (sender, content, ts)。"""
    existing: list[tuple[str, str, int]] = []
    for bid in await redis.zrange(K_BLOCKS, 0, -1):
        for mid in await redis.zrange(f"mychat:block:{bid}:msgs", 0, -1):
            h = await redis.hgetall(f"mychat:msg:{mid}")
            if h.get("sender") and h.get("ts"):
                existing.append((h["sender"], h["content"], int(h["ts"])))
    return existing


async def main() -> None:
    hist = json.load(open(HIST_PATH, encoding="utf-8"))
    hist.sort(key=lambda m: m["time"])          # 时间正序(分块正确性前提)
    redis = await get_redis()

    existing = await load_existing(redis)
    blocks_before = await redis.zcard(K_BLOCKS)
    pos_before = await redis.llen(K_POS)

    # 1) 摘 active 指针(防旧 ts 全并进当前块);记原值收尾恢复
    orig_active = await redis.get(K_ACTIVE)
    if orig_active:
        await redis.delete(K_ACTIVE)

    ins_user = ins_manual = samples = skipped_empty = skipped_dup = 0
    try:
        for m in hist:
            ts = int(m["time"]) * 1000
            content = extract_content(m)
            if not content:
                skipped_empty += 1
                continue
            from_user = m.get("user_id") != BOT_QQ
            sender = "user" if from_user else "proxy"
            source = "live" if from_user else "manual"
            # 去重:库内已有(09-07 测试/今日新录)
            if any(e[0] == sender and e[1] == content and abs(e[2] - ts) < DEDUP_WINDOW_MS
                   for e in existing):
                skipped_dup += 1
                continue
            mid = await chat_store.append_message(
                redis, OID, sender=sender, content=content, source=source, ts=ts)
            if from_user:
                ins_user += 1
                continue
            ins_manual += 1
            # 手动回复=黄金正样本(占位除外);格式同 score.service._collect_sample
            if content not in PLACEHOLDERS:
                payload = json.dumps({"mid": mid, "text": content, "score": 100,
                                      "ts": ts, "source": "manual"}, ensure_ascii=False)
                pipe = redis.pipeline()
                pipe.lpush(K_POS, payload)
                pipe.ltrim(K_POS, 0, settings.score_sample_keep - 1)
                await pipe.execute()
                samples += 1
    finally:
        # 2) 收尾:回填尾巴块置 closed(手工 hset,不走 close_block——它会写 end_ts=now 且删 active)
        cur_active = await redis.get(K_ACTIVE)
        if cur_active and cur_active != orig_active:
            await redis.hset(f"mychat:block:{cur_active}",
                             mapping={"status": "closed", "close_reason": "backfill"})
        # 3) 恢复原 active 指针(真最新块,后续新消息正确续写)
        if orig_active:
            await redis.set(K_ACTIVE, orig_active)

    print("=" * 60)
    print(f"插入: 用户消息 {ins_user} 条 / 手动回复 {ins_manual} 条")
    print(f"金样本(pos,source=manual): +{samples}")
    print(f"跳过: 空内容 {skipped_empty} / 与库内重复 {skipped_dup}")
    print(f"blocks: {blocks_before} -> {await redis.zcard(K_BLOCKS)}")
    print(f"pos 样本队列: {pos_before} -> {await redis.llen(K_POS)} (保留上限 score_sample_keep={settings.score_sample_keep})")


asyncio.run(main())
