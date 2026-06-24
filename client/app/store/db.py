"""
本地 SQLite 存储（客户端缓存）
messages：对话历史缓存（增量同步用）；outbox：离线未发送队列（重连补发）。
单连接 + threading.Lock 串行化（UI 线程与 WS 线程都会访问），check_same_thread=False。
单对象保存上限 message_limit，超出清理最旧（Q-04）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建 ChatStore：messages/outbox CRUD + 上限清理
"""
import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Message:
    id: int
    object_id: str
    role: str           # user / assistant
    text: str
    rich: dict          # 富内容（图片/语音/表情包），可为空 dict
    ts: int
    synced: int         # 1=已与服务端同步, 0=待补


class ChatStore:
    """SQLite 本地缓存：消息历史 + 离线 outbox"""

    def __init__(self, db_path: Path, message_limit: int = 500):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._limit = message_limit
        # check_same_thread=False 允许 UI/WS 两线程共用；用 Lock 串行化写
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    rich TEXT NOT NULL DEFAULT '{}',
                    ts INTEGER NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    sent INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_msg_oid_ts ON messages(object_id, ts);
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # —— 消息历史 ——
    def append_message(self, object_id: str, role: str, text: str, ts: int,
                       rich: dict | None = None, synced: int = 1) -> int:
        """追加一条消息；同时按上限清理该对象最旧消息。返回自增 id"""
        rich_json = json.dumps(rich or {}, ensure_ascii=False)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO messages(object_id, role, text, rich, ts, synced) VALUES(?,?,?,?,?,?)",
                (object_id, role, text, rich_json, int(ts), int(synced)),
            )
            self._conn.commit()
            mid = cur.lastrowid
            self._enforce_limit_locked(object_id)
            return mid

    def _enforce_limit_locked(self, object_id: str) -> int:
        """超 message_limit 时删除该对象最旧消息（调用方已持锁）。返回删除条数"""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE object_id=?", (object_id,)
        )
        n = cur.fetchone()[0]
        if n <= self._limit:
            return 0
        cur = self._conn.execute(
            "DELETE FROM messages WHERE id IN (SELECT id FROM messages WHERE object_id=? ORDER BY ts ASC LIMIT ?)",
            (object_id, n - self._limit),
        )
        self._conn.commit()
        return cur.rowcount

    def get_messages(self, object_id: str, limit: int = 200) -> list[Message]:
        """取该对象最近 limit 条消息（按时间升序返回）"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM messages WHERE object_id=? ORDER BY ts DESC LIMIT ?", (object_id, int(limit))
            )
            rows = list(cur.fetchall())
        rows.reverse()
        return [self._row_to_msg(r) for r in rows]

    @staticmethod
    def _row_to_msg(row: sqlite3.Row) -> Message:
        try:
            rich = json.loads(row["rich"]) if row["rich"] else {}
        except (json.JSONDecodeError, TypeError):
            rich = {}
        return Message(
            id=row["id"], object_id=row["object_id"], role=row["role"],
            text=row["text"], rich=rich, ts=row["ts"], synced=row["synced"],
        )

    # —— 离线 outbox（待发用户消息）——
    def enqueue_outbox(self, object_id: str, text: str, ts: int) -> int:
        """离线/未确认发送时入队，重连后补发"""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO outbox(object_id, text, ts) VALUES(?,?,?)", (object_id, text, int(ts))
            )
            self._conn.commit()
            return cur.lastrowid

    def pending_outbox(self, object_id: str | None = None) -> list[sqlite3.Row]:
        """取未发送的 outbox（按入队顺序）"""
        with self._lock:
            if object_id:
                cur = self._conn.execute(
                    "SELECT * FROM outbox WHERE sent=0 AND object_id=? ORDER BY id ASC", (object_id,)
                )
            else:
                cur = self._conn.execute("SELECT * FROM outbox WHERE sent=0 ORDER BY id ASC")
            return list(cur.fetchall())

    def mark_outbox_sent(self, outbox_id: int) -> None:
        with self._lock:
            self._conn.execute("UPDATE outbox SET sent=1 WHERE id=?", (outbox_id,))
            self._conn.commit()
