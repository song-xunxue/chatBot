"""
训练前置工具 REST 接口(2026-09-12 前置工作 A2/B1)
- POST /training/{oid}/benchmark  人设盲测基准(A/B provider 同上下文对比,固定裁判)
- POST /training/{oid}/export     训练数据导出(SFT + DPO 偏好对,LLaMA-Factory 格式)
鉴权 verify_token(同其余端点)。详见 docs/04 调研报告路线图阶段 A/B。

作者: 李文煜
日期: 2026-09-12
"""
from fastapi import APIRouter, Body, Depends

from api._auth import verify_token
from storage.redis_client import get_redis
from training import benchmark as benchmark_mod
from training import export as export_mod

router = APIRouter(prefix="/api/v1", tags=["training"])


@router.post("/training/{oid}/benchmark", dependencies=[Depends(verify_token)])
async def benchmark(oid: str, body: dict = Body(default={})):
    """人设盲测基准。body: {provider_a, provider_b, n?=20, judge_provider?=""}。
    取最近 n 条用户消息做上下文,两 provider 各生成,固定裁判(评分链路)打分。
    注意:本地 provider 经 frp 生成较慢,n=20 全程约数分钟,面板请耐心等待。"""
    provider_a = (body.get("provider_a") or "").strip()
    provider_b = (body.get("provider_b") or "").strip()
    if not provider_a or not provider_b:
        return {"error": "bad_request", "message": "provider_a 与 provider_b 必填"}
    try:
        n = int(body.get("n") or 20)
    except (TypeError, ValueError):
        n = 20
    redis = await get_redis()
    return await benchmark_mod.benchmark_persona(
        redis, oid, provider_a=provider_a, provider_b=provider_b,
        n=n, judge_provider=(body.get("judge_provider") or "").strip())


@router.post("/training/{oid}/export", dependencies=[Depends(verify_token)])
async def export_data(oid: str, body: dict = Body(default={})):
    """训练数据导出。body: {min_score?=85}。产出 LLaMA-Factory 格式:
    qingxun_sft_*.jsonl(pos/manual/correction/roleplay)+ qingxun_dpo_*.jsonl(纠正偏好对),
    写入 server/data/training/(容器挂卷,可 docker cp 取出)。返回统计。"""
    try:
        min_score = int(body.get("min_score") or 85)
    except (TypeError, ValueError):
        min_score = 85
    redis = await get_redis()
    return await export_mod.export_training_data(redis, oid, min_score=min_score)
