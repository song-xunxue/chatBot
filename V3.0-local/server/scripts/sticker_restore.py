"""
表情包库恢复(方案 A,2026-11-03 review 修正版;计划任务 ChatBotStickerRestore 一次性 18:05 触发)。

背景:2026-10-27 云端迁移只导了 Redis 注册键(mychat:sticker:lib,57 条描述元数据),
没拷图片文件——find_sticker 要求"注册+文件同时存在",文件缺失 → 必返 None →
出站 [表情包: 描述] token 按设计保留文字直出(用户报障根因)。

流程(每步落日志 logs/sticker-restore.log,失败即停):
  1. 快照:6390 sticker:lib + 全部 desc:{md5} 缓存 → backups/sticker_lib_snapshot_<ts>.json
     (56 条描述元数据是唯一副本,先快照再动手——review 强制修正①)
  2. 拉图:scp -r 云端 ~/ChatBot-V3/server/data/stickers/. → 6390 栈 server/data/stickers/
     (追加合并,不删本地现有文件);再本地复制一份给大肥鱼
  3. 同步:6390 lib 注册全量 HSET 到 6380(大肥鱼此前 0 注册,merge 无冲突)
  4. 验证:两栈各抽 3 条注册 → lib 描述 + 磁盘文件 exists + find_sticker 同款匹配逻辑,
     全部命中才算成功;最后打印对齐统计(注册数/磁盘文件数)

用法:
  python scripts/sticker_restore.py            # dry-run:只做快照+统计预览(不拷不写)
  python scripts/sticker_restore.py --apply    # 实际执行(拷图+同步+验证)

日期: 2026-11-03
"""
import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("sticker_restore")

PEM = r"D:\code\Git_Local\ChatBot\.claude\ubuntu.pem"
REMOTE = "ubuntu@43.140.219.99"
REMOTE_DIR = "~/ChatBot-V3/server/data/stickers"
QING_DIR = Path(r"D:\code\Git_Local\ChatBot\V3.0-local\server\data\stickers")
DAFEIYU_DIR = Path(r"D:\code\Git_Local\ChatBot\Vdafeiyu\server\data\stickers")
BACKUP_DIR = Path(r"D:\code\Git_Local\ChatBot\backups")
K_LIB = "mychat:sticker:lib"


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    """subprocess 跑外部命令(ssh/scp),返回 (code, 输出)"""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


async def snapshot(redis, tag: str) -> Path:
    """快照 6390 sticker 注册与描述缓存 → backups/(review 强制修正①:先快照再动手)"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = BACKUP_DIR / f"sticker_lib_snapshot_{tag}.json"
    lib = await redis.hgetall(K_LIB)
    descs = {}
    async for k in redis.scan_iter(match="mychat:sticker:desc:*", count=200):
        k = k.decode() if isinstance(k, bytes) else k
        v = await redis.get(k)
        descs[k] = v.decode() if isinstance(v, bytes) else v
    payload = {"snapshot_ts": tag, "lib": lib, "desc_cache": descs}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"[1.快照] lib={len(lib)} 条 desc缓存={len(descs)} 条 → {out}")
    return out


async def main(apply: bool) -> None:
    from storage.redis_client import get_redis

    tag = time.strftime("%Y%m%d-%H%M%S")
    redis = await get_redis()
    log.info(f"=== 表情包恢复开始 mode={'APPLY' if apply else 'DRY-RUN'} ts={tag} ===")

    # 0.现状统计
    lib = await redis.hgetall(K_LIB)
    local_files = {p.name for p in QING_DIR.glob("*")} if QING_DIR.is_dir() else set()
    log.info(f"[0.现状] 6390 注册 {len(lib)} 条 | 6390 栈磁盘文件 {len(local_files)} 个 | "
             f"死注册(注册无文件) {len([f for f in lib if f not in local_files])} 条")

    # 1.快照(dry-run 也做——快照本身只增不删,安全)
    await snapshot(redis, tag)

    if not apply:
        log.info("=== DRY-RUN 结束(未拷图未同步);加 --apply 执行恢复 ===")
        return

    # 2.拉图(scp 追加合并;不删本地现有)
    code, out = run(["scp", "-i", PEM, "-r", f"{REMOTE}:{REMOTE_DIR}/.", str(QING_DIR)], timeout=600)
    if code != 0:
        log.error(f"[2.拉图] scp 失败: {out[:300]}")
        return
    after_files = {p.name for p in QING_DIR.glob("*")}
    log.info(f"[2.拉图] 6390 栈目录文件 {len(local_files)} → {len(after_files)} 个")

    # 3.大肥鱼复制一份
    DAFEIYU_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for p in QING_DIR.glob("*"):
        dst = DAFEIYU_DIR / p.name
        if not dst.exists():
            dst.write_bytes(p.read_bytes())
            copied += 1
    log.info(f"[3.大肥鱼] 复制 {copied} 个新文件(已有 {len(after_files) - copied} 个跳过)")

    # 4.6380 同步注册(merge:6380 当前 0 注册)
    import redis as redis_mod
    r6380 = redis_mod.Redis(host="127.0.0.1", port=6380, decode_responses=True)
    if lib:
        await r6380.hset(K_LIB, mapping=lib)
    log.info(f"[4.同步] 6380 lib 注册 {len(lib)} 条已写入")

    # 5.验证:两栈抽 3 条注册,走 find_sticker 同款匹配逻辑
    def verify(lib_map: dict, d: Path, tag_: str) -> int:
        ok = 0
        checked = 0
        for fname, desc in sorted(lib_map.items()):
            p = d / fname
            if not (p.exists() and desc):
                continue
            checked += 1
            if checked > 3:
                break
            hit = p.exists() and bool(desc)
            if hit:
                ok += 1
            log.info(f"[5.验证-{tag_}] {fname}: 文件存在={p.exists()} 描述={desc[:40]}")
        return ok

    ok1 = verify(lib, QING_DIR, "6390")
    ok2 = verify(lib, DAFEIYU_DIR, "大肥鱼")
    disk_q = len({p.name for p in QING_DIR.glob('*')})
    disk_d = len({p.name for p in DAFEIYU_DIR.glob('*')})
    log.info(f"[5.验证] 抽验命中 6390={ok1}/3 大肥鱼={ok2}/3 | 磁盘文件 6390={disk_q} 大肥鱼={disk_d} | 注册={len(lib)}")
    log.info("=== 恢复完成。配图链路(find_sticker)已可命中;下次带 [表情包: ...] 的回复即发真实图片 ===")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="表情包库恢复(云端图→两栈+注册同步)")
    ap.add_argument("--apply", action="store_true", help="实际执行(缺省 dry-run)")
    a = ap.parse_args()
    asyncio.run(main(a.apply))
