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

2026-09-15
变更说明：
    1. 连发合并(burst merge):连续多条 ai/proxy 消息(无 user 间隔)视为一个回复单元,
       "\n" 合并成一条样本——贴合分段发送(多气泡=换行分段)的人设风格;原逐条逻辑下
       burst 只有首条能成样本(126 手动→56 样本的损失主因),其余气泡连 history 都进不了。
       correction 混入 burst 时:merged 用纠正文本,DPO 对 chosen/rejected 均为合并版
       (同上下文整回复对比);混入 live ai 时任一条达 min_score 即整单元入选(pos 口径)。
    2. 占位过滤:合并后输出全为纯媒体占位([图片]等)的手动回复不作样本(对齐
       score.service._PLACEHOLDER_TEXTS 的不入队规则,原版导出会把占位文本当训练目标)
"""
import json
import logging
import time
from pathlib import Path

from core.config import PROJECT_ROOT
from storage import chat_store

logger = logging.getLogger(__name__)

_MAX_HISTORY_PAIRS = 10      # 每条样本携带的最大前文轮数(控序列长度,QLoRA cutoff 2048 内)

# 纯媒体占位(与 score.service._PLACEHOLDER_TEXTS 同步):占位-only 的回复单元不入 SFT
_PLACEHOLDER_TEXTS = {"[语音]", "[图片]", "[表情]", "[转发]", "[文件]", "[视频]", "[非文本消息]"}


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
    # 连发合并(2026-09-15):burst 缓冲连续 ai/proxy 消息,遇下一条 user 或结尾 flush
    msgs = await chat_store.list_messages(redis, oid, limit=2000)
    history: list[list[str]] = []
    state = {"pending_user": ""}       # 闭包可变(nonlocal 替代;flush 函数读写)
    burst: list[dict] = []             # [{content, corrected, source, score}]

    def _flush_burst() -> None:
        """结算一个回复单元:定 kind → 收样本/偏好对 → 前文滚动。"""
        if not burst:
            return
        parts_out = [(b["corrected"] or b["content"]) for b in burst]
        merged = "\n".join(p for p in parts_out if p)
        pending = state["pending_user"]
        if merged and pending:
            any_corrected = any(b["corrected"] for b in burst)
            all_manual = all(b["source"] == "manual" for b in burst)
            if any_corrected:
                kind = "correction"
                # DPO 对:chosen=合并纠正版 / rejected=合并原版(同上下文整回复对比)
                rejected = "\n".join(b["content"] for b in burst if b["content"])
                _dpo_item(pending, merged, rejected, history)
            elif all_manual:
                kind = "manual"
            else:
                # 混入 live ai:任一条达 min_score 即整单元入选(回复单元整体评价)
                kind = ("pos" if any(b["score"] is not None and b["score"] >= min_score
                                     for b in burst) else "")
            # 占位-only 的回复单元不作训练目标([图片]等对风格学习无价值),前文照常滚动
            if kind and not all(p.strip() in _PLACEHOLDER_TEXTS for p in parts_out if p.strip()):
                _sft_item(kind, pending, merged, history)
            # 前文滚动用合并后整单元(多气泡=一条多行 assistant 回合,与 LLM 上下文形态一致)
            history.append([pending, merged])
            state["pending_user"] = ""
        burst.clear()

    for m in msgs:
        if m.get("status") in ("deleted", "recalled"):
            continue
        sender = m.get("sender", "")
        content = (m.get("content", "") or "").strip()
        if not content:
            continue
        if sender == "user":
            _flush_burst()
            state["pending_user"] = content
            continue
        if sender not in ("ai", "proxy"):
            continue
        burst.append({"content": content,
                      "corrected": (m.get("corrected", "") or "").strip(),
                      "source": m.get("source", ""),
                      "score": _score_of(m)})
    _flush_burst()   # 尾部 burst(对话以回复收尾且无人再追问的场景)

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
