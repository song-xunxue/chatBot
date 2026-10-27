"""
世界书迁移脚本(docs/09 验收#4)
存量四级记忆(long_term/core/episodic)→ 世界书条目,幂等(先删自动来源条目再按当前数据全量
重建,重复执行结果一致),支持 --dry-run(只统计不写)。
对照输出:各来源迁移条数(含遗忘→disabled),worldbook 条目总量前后对照。
用法:
  C:/Users/26904/anaconda3/envs/qingxun/python.exe V3.0-local/server/scripts/migrate_worldbook.py [--dry-run]
  [--oid 1145077465](缺省扫全部对象)

日期: 2026-10-26

2026-10-26
变更说明:
  1. 初版:dry-run 统计对照 + 实迁移(委托 worldbook_store.rebuild_auto,manual 条目保留)
"""
import argparse
import asyncio
import sys
from pathlib import Path

# server/app 加入 sys.path(与 tests/conftest.py 一致,使 core/memory/storage 可同级导入;幂等防重复插入)
_APP_DIR = str(Path(__file__).resolve().parent.parent / "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="migrate legacy memories to worldbook entries")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写")
    parser.add_argument("--oid", default="", help="只迁移指定对象(缺省扫全部)")
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    from memory import store as mem_store, worldbook_store
    from storage.redis_client import get_redis

    redis = await get_redis()
    oids = [args.oid] if args.oid else await mem_store.list_objects(redis)
    if not oids:
        print("没有可迁移的对象(未发现 mychat:mem:*:long 键)")
        return 0

    # 迁移前对照:存量记忆数 + 现有 worldbook 条目数
    print("=" * 60)
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}世界书迁移:对象 {oids}")
    total_mem = total_core = total_epi = total_forgotten = 0
    for oid in oids:
        items = await mem_store.get_all_long_term(redis, oid, include_forgotten=True)
        total_mem += len(items)
        total_forgotten += sum(1 for m in items if m.forgotten)
        total_core += len(await mem_store.get_core(redis, oid))
        total_epi += await mem_store.count_episodic(redis, oid)
    before = len(await worldbook_store.list_entries(redis))
    print(f"存量记忆:long_term={total_mem}(遗忘 {total_forgotten}) core={total_core} "
          f"episodic={total_epi}")
    print(f"worldbook 条目(迁移前): {before}")

    result = await worldbook_store.rebuild_auto(redis, oids, dry_run=args.dry_run)

    if args.dry_run:
        print(f"[DRY-RUN] 预计:新建/启用 {result['created']} 条,停用(遗忘态) {result['disabled']} 条")
        print(f"[DRY-RUN] worldbook 条目(迁移后预估): {before} (不变,dry-run 不写)")
    else:
        after = len(await worldbook_store.list_entries(redis))
        print(f"迁移完成:新建/启用 {result['created']} 条,停用(遗忘态) {result['disabled']} 条")
        print(f"worldbook 条目(迁移后): {after} (前={before};manual 条目保留不受影响)")
        print("回滚:清空自动条目可重跑 POST /api/v1/worldbook/rebuild,或直接切回 MEMORY_MODE=legacy")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
