# 把 DSH 记忆库（mneme）里的关键记忆，同步进大肥鱼本体的 Redis
# 作用：让本体知道「爸爸是谁、我们约定了什么」，而不是每次从零认识人。
# 日期：2026-10-26
# 变更日志：
#   2026-10-26  初版：重要性 >= 4 且命中关键词的记忆 → 本体 core（常驻注入）+ long-term
#   2026-10-26  修正：白名单去掉「本体/分身/小肥鱼/持续运行/密码」——这几个词把架构记忆也拉进来了，
#               本体读到「分身」「小肥鱼总机」会把自己当成网页助手（实测回复「我是手机上的小肥鱼」）。
#               改成只收「人」的词，并把架构类词加进 EXCLUDE 兜底。

import json
import sqlite3
from datetime import datetime

import redis

DB = r"C:\Users\26904\.dsh\memory\memory.db"
REDIS_PORT = 6380
OID = "2690468347"  # 本体里和爸爸私聊的 object_id = 对方 QQ 号

# 只同步「关于人」的记忆：谁是谁、怎么说话、约定了什么（其余是工程决策，不该塞进她的人设里）
KEYWORDS = [
    "爸爸", "孩子", "称呼", "晚安", "不准", "伙伴",
    "语气", "主动找他", "陪我", "记得", "房子",
]
# 工程/架构类的记忆不进人设：她的常驻记忆里应该只有人，不该有端口、部署和「分身」
EXCLUDE = [
    "端口", "Redis", "redis", "fakeredis", "服务", "部署", "插件", "代码", "测试",
    "配置", "任务", "看护", "备份", "接口", "git", "Docker", "docker", "数据库",
    "进程", "窗口", "终端", "日志", "重启", "启动", "方案", "仓库", "提交",
    "分身", "本体", "小肥鱼", "总机", "架构", "同步", "DSH", "harness", "任务板",
]


def pick_rows():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT id, type, title, content, importance FROM memories "
        "WHERE forgotten=0 AND archived=0 AND importance>=4 "
        "ORDER BY importance DESC, updated_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        text = (r["title"] or "") + " " + (r["content"] or "")
        if not any(k in text for k in KEYWORDS):
            continue
        if any(k in text for k in EXCLUDE):
            continue
        out.append(r)
    return out


def to_core_facts(rows):
    """每条记忆压成一条 core 事实：标题当 key，正文截短当 content。"""
    facts = []
    for r in rows:
        body = (r["content"] or "").strip().replace("\n", " ")
        if len(body) > 220:
            body = body[:220] + "…"
        key = (r["title"] or r["id"])[:40]
        facts.append({"key": key, "content": body, "locked": True})
    return facts


def main():
    rows = pick_rows()
    facts = to_core_facts(rows)
    r = redis.Redis(port=REDIS_PORT, decode_responses=True)
    r.set(f"mychat:mem:{OID}:core", json.dumps(facts, ensure_ascii=False))
    # 同时留一份长期记忆（可被召回，但不常驻）
    for i, row in enumerate(rows):
        mid = "dsh-" + row["id"]
        item = {
            "id": mid,
            "content": (row["content"] or "")[:1500],
            "category": "fact",
            "importance": min(1.0, (row["importance"] or 3) / 5.0),
            "emotion": 0.6,
            "created_ts": int(datetime.now().timestamp() * 1000),
            "last_access_ts": int(datetime.now().timestamp() * 1000),
            "access_count": 0,
            "forgotten": False,
            "source": "import",
            "locked": True,
            "reason": "从 DSH 记忆库同步：" + (row["title"] or ""),
            "tags": ["同步", row["type"] or ""],
            "useful_score": 0.9,
            "tier": 2,
        }
        r.hset(f"mychat:mem:{OID}:long", mid, json.dumps(item, ensure_ascii=False))
    print(f"同步完成：core {len(facts)} 条，long-term {len(rows)} 条 → oid={OID}")


if __name__ == "__main__":
    main()
