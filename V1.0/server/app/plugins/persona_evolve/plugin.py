"""
persona_evolve 插件（人性化·人格反推）
on_delete：删除 = 不符合人格的负样本，累积到 samples；
达 threshold 时生成"人格进化提案"(raw samples)写入 Redis，待 M7 面板人工确认。
设计原则(风险清单)：不自动改写人设，仅产出提案，避免人格漂移失控。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 创建 persona_evolve：负样本累积 + 阈值提案(不自动改写)
"""
import json

from plugins.base import Plugin, HookResult

_SAMPLES_KEY = "mychat:persona_evolve:samples:{oid}"    # 待处理负样本队列
_PROPOSAL_KEY = "mychat:persona_evolve:proposal:{oid}"  # 已生成提案(待人工确认)


class PersonaEvolvePlugin(Plugin):
    """人格反推：累积删除负样本，达阈值产出进化提案"""

    async def on_delete(self, ctx):
        params = await self.get_params(ctx.object_id)
        threshold = int(params.get("threshold", 5))
        redis = self.pctx.redis
        payload = ctx.plugin_meta.get("deleted_payload") or {}
        sample = {
            "text": payload.get("text") or ctx.reply_text or "",
            "reason": payload.get("reason", "out_of_character"),
        }
        samples = await self._load(redis, ctx.object_id)
        samples.append(sample)
        if len(samples) >= threshold:
            # 达阈值：产出提案，清空样本队列（提案待 M7 面板人工确认后才落库改人设）
            await redis.set(_PROPOSAL_KEY.format(oid=ctx.object_id),
                            json.dumps({"samples": samples}, ensure_ascii=False))
            await redis.delete(_SAMPLES_KEY.format(oid=ctx.object_id))
            ctx.plugin_meta["evolve_proposed"] = True
        else:
            await redis.set(_SAMPLES_KEY.format(oid=ctx.object_id),
                            json.dumps(samples, ensure_ascii=False))
        return HookResult.CONTINUE

    @staticmethod
    async def _load(redis, oid) -> list:
        raw = await redis.get(_SAMPLES_KEY.format(oid=oid))
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
