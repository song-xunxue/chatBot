"""
训练数据导出管线(前置工作 B1,2026-09-12)
把 V3.0 评分系统沉淀的对话资产导出为 LLaMA-Factory 训练格式,供后续
QLoRA SFT + DPO(人设微调进参数,详见 docs/04 调研报告)。

数据来源与格式:
  - SFT 集(alpaca JSONL,含 system + history 多轮字段):
      chosen 回复 = ① score ≥ min_score 的 ai 回复(pos 样本口径)
                  ② source=manual 手动回复(管理员黄金示范)
                  ③ corrected 纠正文本(管理员理想回复,黄金标准)
                  ④ roleplay 训练剧本中 score ≥ min_score 的 assistant 条目
  - DPO 偏好对(LLaMA-Factory sharegpt 偏好格式):
      correction 消息天然产出同上下文偏好对——
      chosen = corrected(理想回复) / rejected = 原 content(被纠正回复)
  - system = render_system_prompt(persona) 静态人设(含输出契约;不含记忆/心情动态)

输出:server/data/training/qingxun_{sft|dpo}_{yyyyMMdd_HHmmss}.jsonl + latest 统计。

作者: 李文煜
日期: 2026-09-12
"""
import json
import logging
import time
from pathlib import Path

from core.config import PROJECT_ROOT
from storage import chat_store

logger = logging.getLogger(__name__)

_MAX_HISTORY_PAIRS = 10      # 每条样本携带的最大前文轮数(控序列长度,QLoRA cutoff 2048 内)


def _training_dir() -> Path:
    """训练数据目录(项目根/server/data/training,懒建;容器内即挂卷的 /app/server/data)"""
    d = PROJECT_ROOT / "server" / "data" / "training"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_jsonl(path: Path, items: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


async def export_training_data(redis, oid: str, *, min_score: int = 85) -> dict:
    """导出该会话的 SFT 集 + DPO 偏好对(LLaMA-Factory 格式 JSONL)。
    返回 {sft, dpo, by_source, files}。"""
    from takeover.service import _resolve_persona
    from persona.renderer import render_system_prompt

    min_score = max(0, min(100, int(min_score)))
    card = await _resolve_persona(redis, oid)
    system_prompt = render_system_prompt(card)

    sft: list[dict] = []
    dpo: list[dict] = []
    by_source = {"pos": 0, "manual": 0, "correction": 0, "roleplay": 0, "dpo_pairs": 0}

    def _sft_item(kind: str, user_text: str, output: str, history: list[list[str]]):
        by_source[kind] = by_source.get(kind, 0) + 1
        sft.append({"instruction": user_text, "input": "", "output": output,
                    "system": system_prompt, "history": history[-_MAX_HISTORY_PAIRS:]})

    def _dpo_item(user_text: str, chosen: str, rejected: str, history: list[list[str]]):
        by_source["dpo_pairs"] += 1
        convs = [{"from": "system", "value": system_prompt}]
        for u, a in history[-_MAX_HISTORY_PAIRS:]:
            convs.append({"from": "human", "value": u})
            convs.append({"from": "gpt", "value": a})
        convs.append({"from": "human", "value": user_text})
        dpo.append({"conversations": convs,
                    "chosen": {"from": "gpt", "value": chosen},
                    "rejected": {"from": "gpt", "value": rejected}})

    def _score_of(m: dict) -> int | None:
        raw = m.get("score", "")
        if raw in ("", None):
            return None
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None

    # —— live 真实对话:SFT(pos/manual/correction) + DPO(correction 对) ——
    msgs = await chat_store.list_messages(redis, oid, limit=2000)
    history: list[list[str]] = []
    pending_user = ""
    for m in msgs:
        if m.get("status") in ("deleted", "recalled"):
            continue
        sender = m.get("sender", "")
        content = (m.get("content", "") or "").strip()
        if not content:
            continue
        if sender == "user":
            pending_user = content
            continue
        if sender not in ("ai", "proxy"):
            continue
        corrected = (m.get("corrected", "") or "").strip()
        target, kind = None, ""
        if corrected:
            # 纠正回复:黄金 SFT 样本 + 同上下文 DPO 偏好对(chosen=纠正/rejected=原回复)
            target, kind = corrected, "correction"
            if pending_user:
                _dpo_item(pending_user, corrected, content, history)
        elif m.get("source") == "manual":
            target, kind = content, "manual"
        else:
            sc = _score_of(m)
            if sc is not None and sc >= min_score:
                target, kind = content, "pos"
        if target and pending_user:
            _sft_item(kind, pending_user, target, history)
        # 前文滚动:无论是否入选,真实对话继续(历史用实际发出的话)
        if pending_user:
            history.append([pending_user, content])
            pending_user = ""

    # —— roleplay 训练剧本:assistant 高分条目入 SFT ——
    try:
        blocks = await chat_store.list_roleplay_blocks(redis, oid)
        for b in blocks:
            rmsgs = await chat_store.list_roleplay(redis, oid, block_id=b.get("block_id", ""))
            rp_history: list[list[str]] = []
            rp_user = ""
            for m in rmsgs:
                role = m.get("role", "")
                content = (m.get("content", "") or "").strip()
                if not content or role == "system":
                    continue   # 旁白不入训练(同 roleplay_extract 铁律)
                if role == "user":
                    rp_user = content
                    continue
                sc = _score_of(m)
                if rp_user and sc is not None and sc >= min_score:
                    _sft_item("roleplay", rp_user, content, rp_history)
                if rp_user:
                    rp_history.append([rp_user, content])
                    rp_user = ""
    except Exception:
        logger.exception("roleplay 训练样本导出失败 oid=%s(不影响 live 部分产物)", oid)

    # —— 写文件 ——
    stamp = time.strftime("%Y%m%d_%H%M%S")
    sft_path = _training_dir() / f"qingxun_sft_{stamp}.jsonl"
    dpo_path = _training_dir() / f"qingxun_dpo_{stamp}.jsonl"
    _write_jsonl(sft_path, sft)
    _write_jsonl(dpo_path, dpo)
    return {"sft": len(sft), "dpo": len(dpo), "by_source": by_source,
            "files": [str(sft_path), str(dpo_path)],
            "min_score": min_score, "oid": oid}
