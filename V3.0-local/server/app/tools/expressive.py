"""
表达类工具(2026-11-08,用户拍板的「能力工具化」第一批):
把「发语音」「发表情包」从配置驱动的被动路径升级为 tool-loop 里模型可自主调用的工具。

动机:用户说「念给我听/来张表情包」时,模型在 tool-loop 里看不到对应能力(旧工具清单
只有 get_persona/write_memory/reverse_infer_trigger/web_search),只能文字回复——
能力与插件钩子耦合、模型不可见。挂进既有 ToolRegistry 后 tool-loop 立即可见,pipeline 零改动。

设计要点:
  - SendVoiceTool:文本 → get_tts().synthesize(当前 provider:BreezeBlue/GPTSoVITS/...) →
    adapter.send_voice。护栏全在 provider 内(BreezeBlue 截断/每日上限);失败返回错误说明给
    模型(模型可改用文字回复),绝不阻塞主流程。
  - SendStickerTool:先 find_sticker 预检(命中才发——未命中若直接走 send_text 的 token
    字面回退,会把「[表情包: xxx]」文字发给用户);未命中时用字符 bigram 重叠在库内模糊
    取最高分(≥0.25 才发,review 修正②的阈值思路);仍无匹配则明确告知模型库里没有。
  - 发送均经既有出站路径(adapter.send_voice / send_text 的 token 翻译),零新链路。
  - 语音 voice 走 resolve_voice(面板克隆 uri/预设);emotion 首版关闭(BreezeBlue 后续可接
    voice instruction prompting)。

日期: 2026-11-08
"""
import logging

from tools.base import Tool

logger = logging.getLogger(__name__)


def _bigram_overlap(a: str, b: str) -> float:
    """字符 bigram 重叠率(交并比;中文场景字符级 bigram 足够)。任一方太短返回 0。"""
    a, b = a.strip(), b.strip()
    if len(a) < 2 or len(b) < 2:
        return 0.0
    ga = {a[i:i + 2] for i in range(len(a) - 1)}
    gb = {b[i:i + 2] for i in range(len(b) - 1)}
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


class SendVoiceTool(Tool):
    """把要说的话用语音发给当前聊天对象(BreezeBlue 云端音色/GPT-SoVITS 本地)"""
    name = "send_voice"
    description = (
        "用你的声音把一段话以语音消息发给对方。当对方表达想听你的声音、要求「念给我听/发语音/"
        "说给我听」,或你觉得这条内容特别适合语音表达(如晚安、情话)时调用。"
        "调用后语音会直接发出,无需再在文本里重复这段话;合成失败会返回原因,届时改用文字回复。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要用语音说的话(口语化,30字内最佳)"},
        },
        "required": ["text"],
    }

    async def execute(self, args: dict, ctx) -> str:
        text = (args.get("text") or "").strip()
        if not text:
            return "(text 为空,未发送语音)"
        try:
            from modality.tts import get_tts, resolve_voice
            from adapter import get_current_adapter

            tts = get_tts()
            voice = await resolve_voice(ctx.redis, ctx.object_id, "")
            audio = await tts.synthesize(text, voice or "")
            if not audio:
                return "(语音未配置(provider 降级 stub),请改用文字回复)"
            adapter = await get_current_adapter()
            await adapter.send_voice(ctx.object_id, audio)
            logger.info("send_voice 工具发送成功 oid=%s %d bytes", ctx.object_id, len(audio))
            return f"(已把这段话用语音发给对方:「{text[:60]}」)——不要在文字回复里再重复这句话"
        except Exception as e:
            logger.warning("send_voice 工具失败 oid=%s: %s", ctx.object_id, e)
            return f"(语音发送失败:{e};请改用文字回复,不要向对方提及失败细节)"


class SendStickerTool(Tool):
    """发一张表情包(真实图片)给当前聊天对象"""
    name = "send_sticker"
    description = (
        "从你的表情包库里选一张真实图片发给对方,表达情绪/活跃气氛。"
        "description 用简短中文描述想要的画面(如「两个小人拥抱」「猫猫开心点头」),"
        "库会做语义近似匹配;库里没有接近的图会返回提示,届时改用文字表达情绪即可。"
        "调用后图片直接发出,无需再在文本里写 [表情包: ...]。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "想要的表情包画面描述(简短中文)"},
        },
        "required": ["description"],
    }

    # 模糊匹配阈值(bigram 交并比;review 修正②:零分不配图防乱配)
    FUZZY_THRESHOLD = 0.25

    async def execute(self, args: dict, ctx) -> str:
        desc = (args.get("description") or "").strip()
        if not desc:
            return "(description 为空,未发送)"
        from storage import sticker_store
        from storage.redis_client import get_redis
        redis = ctx.redis
        if redis is None:
            from storage.redis_client import get_redis as _gr
            redis = await _gr()
        path = await sticker_store.find_sticker(redis, desc)
        if path is None:
            # 精确(双向子串)未命中 → 库内 bigram 模糊取最高分
            lib = await redis.hgetall(sticker_store._K_LIB)
            lib = {k.decode() if isinstance(k, bytes) else k:
                   (v.decode() if isinstance(v, bytes) else v)
                   for k, v in lib.items()}
            best_name, best_score = "", 0.0
            for fname, fdesc in lib.items():
                if not fdesc:
                    continue
                score = _bigram_overlap(desc, fdesc)
                if score > best_score:
                    best_name, best_score = fname, score
            if not best_name or best_score < self.FUZZY_THRESHOLD:
                return (f"(表情包库里没有接近「{desc}」的图,不要虚构;请改用文字/颜文字表达情绪)")
            path = sticker_store.STICKER_DIR / best_name
            desc = lib[best_name]
        from adapter import get_current_adapter
        adapter = await get_current_adapter()
        await adapter.send_text(ctx.object_id, f"[表情包: {desc}]")
        logger.info("send_sticker 工具发送成功 oid=%s -> %s", ctx.object_id, path.name)
        return f"(已把表情包发给对方:{desc[:50]})——不要在文字回复里再写 [表情包: ...]"
