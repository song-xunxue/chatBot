"""
记忆批次1存量修正(2026-11-10,P0-3/P0-4 配套一次性脚本)

背景:批次1止血上线前,存量记忆带着旧语义的脏数据(review.md 修正点①②):
  ①core 条目无 source_mid(P0-3 schema 新增字段)——遗忘/删除的 core 联动清理对它们不生效;
  ②auto 档记忆 useful_score 出生=importance(A4 旧默认 init=importance)——
    importance>=0.8 的记忆出生即 T2 永不衰减,与解耦后(init=0.5)的新语义双标准。

动作(先快照后动手,全部可由备份回滚):
  0. 快照备份:受影响键(long hash 全量 + core)落盘 .claude/tmp/stock_fix_backup_<stack>_<ts>.json
  1. core 回填 source_mid:按 content 归一化匹配 long_term(与 coordinator 反查同款逻辑);
     配不上的打印清单留人工审——只补空,不删不改任何条目
  2. useful_score 重置:tier==-1 且非 locked 的 auto 档记忆统一拉回 0.5
     (手动档 tier>=0 与 locked 是用户显式设定,一律不动;forgotten 不影响——
      标志管可见性,分数管恢复后的档位)

用法(栈根目录;--apply 才写,默认 dry-run):
  python scripts/memory_stock_fix.py --port 6390 --stack qingxun           # 6390 dry-run
  python scripts/memory_stock_fix.py --port 6390 --stack qingxun --apply
  python scripts/memory_stock_fix.py --port 6380 --stack dafeiyu --apply

日期: 2026-11-10
"""
import argparse
import io
import json
import sys
import time
from pathlib import Path

import redis

STACK_ROOT = Path(__file__).resolve().parent.parent          # 栈根(server/ 所在)
sys.path.insert(0, str(STACK_ROOT / "server" / "app"))       # 应用代码根(memory/core 所在)

from memory.coordinator import _normalize                    # noqa: E402  与线上反查同一套归一化,防逻辑漂移


def main() -> None:
    ap = argparse.ArgumentParser(description="记忆批次1存量修正(core 回填 source_mid + useful_score 重置)")
    ap.add_argument("--port", type=int, required=True, help="Redis 端口(6390 / 6380)")
    ap.add_argument("--stack", type=str, required=True, help="栈名(用于备份文件命名)")
    ap.add_argument("--apply", action="store_true", help="实际写入(缺省 dry-run 只打印)")
    args = ap.parse_args()

    r = redis.Redis(host="127.0.0.1", port=args.port, db=0,
                    decode_responses=True, socket_timeout=5)   # redis-py 同步客户端;decode_responses 直接回 str
    r.ping()

    # 0.盘点 + 快照备份
    oids = sorted({
        k[len("mychat:mem:"):-len(":long")]
        for k in r.scan_iter(match="mychat:mem:*:long", count=200)   # scan_iter 游标遍历,不阻塞线上
    })
    snapshot = {}
    for oid in oids:
        snapshot[oid] = {
            "long": r.hgetall(f"mychat:mem:{oid}:long"),             # HGETALL 全量(field=mid)
            "core": json.loads(r.get(f"mychat:mem:{oid}:core") or "[]"),
        }
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = STACK_ROOT.parent / ".claude" / "tmp" / f"stock_fix_backup_{args.stack}_{ts}.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(backup_path, "w", encoding="utf-8") as f:
        json.dump({"port": args.port, "ts": ts, "snapshot": snapshot},
                  f, ensure_ascii=False, indent=1)
    print(f"[0] 快照完成 → {backup_path}")

    for oid in oids:
        longs = {mid: json.loads(raw) for mid, raw in snapshot[oid]["long"].items()}
        core = snapshot[oid]["core"]

        # 1.core 回填 source_mid(按归一化 content 匹配 long_term)
        norm_index = {}                                # 归一化 content → mid(重复内容取首个,与反查语义一致)
        for mid, m in longs.items():
            norm_index.setdefault(_normalize(m.get("content", "")), mid)
        patched, unmatched = 0, []
        for cf in core:
            if cf.get("source_mid"):
                continue                               # 已有,不动
            mid = norm_index.get(_normalize(cf.get("content", "")))
            if mid:
                cf["source_mid"] = mid
                patched += 1
            else:
                unmatched.append(cf.get("content", "")[:50])
        if args.apply and patched:
            r.set(f"mychat:mem:{oid}:core", json.dumps(core, ensure_ascii=False))
        print(f"[1] {oid} core 回填: 命中 {patched}/{len(core)}"
              + (f";未命中(人工审): {unmatched}" if unmatched else ""))

        # 2.useful_score 重置(auto 档非 locked 统一 0.5)
        reset = 0
        for mid, m in longs.items():
            if m.get("locked") or m.get("tier", -1) >= 0:
                continue                               # 用户显式设定,不动
            if abs(m.get("useful_score", 0.5) - 0.5) < 1e-6:
                continue                               # 已是 0.5,免写
            m["useful_score"] = 0.5
            if args.apply:
                r.hset(f"mychat:mem:{oid}:long", mid, json.dumps(m, ensure_ascii=False))   # HSET 单条回写
            reset += 1
        print(f"[2] {oid} useful_score 重置: {reset}/{len(longs)}(手动档/locked 跳过)")

    print(f"[done] {'已写入' if args.apply else 'dry-run(加 --apply 生效)'}")


if __name__ == "__main__":
    main()
