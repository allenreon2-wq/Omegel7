# ============================================================
#   Anonymous Chat Bot — database.py
#   Full async SQLite layer (aiosqlite)
# ============================================================

import aiosqlite
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from config import DB_PATH, REPORT_BAN_THRESHOLD

log = logging.getLogger(__name__)

# ── ensure data/ directory exists ───────────────────────────
os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)


# ════════════════════════════════════════════════════════════
#  Schema
# ════════════════════════════════════════════════════════════
SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    last_name       TEXT,
    gender          TEXT    DEFAULT 'random',
    interests       TEXT    DEFAULT '',
    country         TEXT    DEFAULT '',
    karma           INTEGER DEFAULT 0,
    total_chats     INTEGER DEFAULT 0,
    is_banned       INTEGER DEFAULT 0,
    ban_reason      TEXT,
    joined_at       TEXT    DEFAULT (datetime('now')),
    last_seen       TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS active_chats (
    chat_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id        INTEGER NOT NULL,
    user2_id        INTEGER NOT NULL,
    started_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user1_id) REFERENCES users(user_id),
    FOREIGN KEY (user2_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS chat_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user1_id        INTEGER NOT NULL,
    user2_id        INTEGER NOT NULL,
    started_at      TEXT,
    ended_at        TEXT    DEFAULT (datetime('now')),
    messages_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS banned_users (
    user_id         INTEGER PRIMARY KEY,
    reason          TEXT,
    banned_by       INTEGER,
    banned_at       TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id)   REFERENCES users(user_id),
    FOREIGN KEY (banned_by) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id     INTEGER NOT NULL,
    reported_id     INTEGER NOT NULL,
    reason          TEXT    DEFAULT 'No reason given',
    created_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (reporter_id) REFERENCES users(user_id),
    FOREIGN KEY (reported_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS statistics (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    total_users     INTEGER DEFAULT 0,
    total_chats     INTEGER DEFAULT 0,
    active_chats    INTEGER DEFAULT 0,
    messages_today  INTEGER DEFAULT 0,
    last_reset      TEXT    DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO statistics (id) VALUES (1);

CREATE TABLE IF NOT EXISTS blocked_pairs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    blocked_id  INTEGER NOT NULL,
    UNIQUE(user_id, blocked_id)
);
"""

# ════════════════════════════════════════════════════════════
#  Database class
# ════════════════════════════════════════════════════════════
class Database:
    def __init__(self):
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    # ── lifecycle ───────────────────────────────────────────
    async def connect(self):
        self._db = await aiosqlite.connect(DB_PATH)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        log.info("✅  Database connected: %s", DB_PATH)

    async def close(self):
        if self._db:
            await self._db.close()

    # ── internal helpers ────────────────────────────────────
    async def _exec(self, sql: str, params: tuple = ()):
        async with self._lock:
            await self._db.execute(sql, params)
            await self._db.commit()

    async def _fetchone(self, sql: str, params: tuple = ()):
        async with self._db.execute(sql, params) as cur:
            return await cur.fetchone()

    async def _fetchall(self, sql: str, params: tuple = ()):
        async with self._db.execute(sql, params) as cur:
            return await cur.fetchall()

    # ════════════════════════════════════════════════════════
    #  USER operations
    # ════════════════════════════════════════════════════════
    async def register_user(self, user_id: int, username: str,
                            first_name: str, last_name: str):
        await self._exec(
            """INSERT OR IGNORE INTO users
               (user_id, username, first_name, last_name)
               VALUES (?, ?, ?, ?)""",
            (user_id, username, first_name or "", last_name or "")
        )
        await self._exec(
            """UPDATE users SET username=?, first_name=?, last_name=?,
               last_seen=datetime('now') WHERE user_id=?""",
            (username, first_name or "", last_name or "", user_id)
        )
        await self._exec(
            "UPDATE statistics SET total_users = (SELECT COUNT(*) FROM users) WHERE id=1"
        )

    async def get_user(self, user_id: int):
        return await self._fetchone(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        )

    async def update_user_profile(self, user_id: int, **kwargs):
        valid = {"gender", "interests", "country", "karma"}
        sets  = ", ".join(f"{k}=?" for k in kwargs if k in valid)
        vals  = [v for k, v in kwargs.items() if k in valid]
        if sets:
            await self._exec(f"UPDATE users SET {sets} WHERE user_id=?", (*vals, user_id))

    async def update_karma(self, user_id: int, delta: int):
        await self._exec(
            "UPDATE users SET karma = karma + ? WHERE user_id=?",
            (delta, user_id)
        )

    async def get_user_count(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) as c FROM users")
        return row["c"] if row else 0

    async def touch_last_seen(self, user_id: int):
        await self._exec(
            "UPDATE users SET last_seen=datetime('now') WHERE user_id=?",
            (user_id,)
        )

    # ════════════════════════════════════════════════════════
    #  CHAT operations
    # ════════════════════════════════════════════════════════
    async def create_chat(self, user1_id: int, user2_id: int) -> int:
        async with self._lock:
            cur = await self._db.execute(
                "INSERT INTO active_chats (user1_id, user2_id) VALUES (?, ?)",
                (user1_id, user2_id)
            )
            await self._db.commit()
            await self._db.execute(
                "UPDATE statistics SET total_chats=total_chats+1, "
                "active_chats=(SELECT COUNT(*) FROM active_chats) WHERE id=1"
            )
            await self._db.commit()
            return cur.lastrowid

    async def get_partner(self, user_id: int) -> Optional[int]:
        row = await self._fetchone(
            "SELECT user1_id, user2_id FROM active_chats "
            "WHERE user1_id=? OR user2_id=?",
            (user_id, user_id)
        )
        if not row:
            return None
        return row["user2_id"] if row["user1_id"] == user_id else row["user1_id"]

    async def get_chat_row(self, user_id: int):
        return await self._fetchone(
            "SELECT * FROM active_chats WHERE user1_id=? OR user2_id=?",
            (user_id, user_id)
        )

    async def end_chat(self, user_id: int):
        row = await self.get_chat_row(user_id)
        if not row:
            return
        # archive
        await self._exec(
            "INSERT INTO chat_history (user1_id, user2_id, started_at) "
            "VALUES (?, ?, ?)",
            (row["user1_id"], row["user2_id"], row["started_at"])
        )
        await self._exec(
            "DELETE FROM active_chats WHERE chat_id=?", (row["chat_id"],)
        )
        # reward both users karma
        for uid in (row["user1_id"], row["user2_id"]):
            await self.update_karma(uid, 2)
            await self._exec(
                "UPDATE users SET total_chats=total_chats+1 WHERE user_id=?",
                (uid,)
            )
        await self._exec(
            "UPDATE statistics SET "
            "active_chats=(SELECT COUNT(*) FROM active_chats) WHERE id=1"
        )

    async def is_in_chat(self, user_id: int) -> bool:
        return await self.get_partner(user_id) is not None

    # past partners (to avoid re-matching)
    async def get_past_partners(self, user_id: int) -> set:
        rows = await self._fetchall(
            "SELECT user1_id, user2_id FROM chat_history "
            "WHERE user1_id=? OR user2_id=?",
            (user_id, user_id)
        )
        partners = set()
        for r in rows:
            partners.add(r["user2_id"] if r["user1_id"] == user_id else r["user1_id"])
        return partners

    # ════════════════════════════════════════════════════════
    #  BAN / BLOCK operations
    # ════════════════════════════════════════════════════════
    async def ban_user(self, user_id: int, reason: str, banned_by: int):
        await self._exec(
            "INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by) "
            "VALUES (?, ?, ?)",
            (user_id, reason, banned_by)
        )
        await self._exec(
            "UPDATE users SET is_banned=1, ban_reason=? WHERE user_id=?",
            (reason, user_id)
        )

    async def unban_user(self, user_id: int):
        await self._exec("DELETE FROM banned_users WHERE user_id=?", (user_id,))
        await self._exec(
            "UPDATE users SET is_banned=0, ban_reason=NULL WHERE user_id=?",
            (user_id,)
        )

    async def is_banned(self, user_id: int) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM banned_users WHERE user_id=?", (user_id,)
        )
        return row is not None

    async def block_user(self, user_id: int, target_id: int):
        await self._exec(
            "INSERT OR IGNORE INTO blocked_pairs (user_id, blocked_id) VALUES (?, ?)",
            (user_id, target_id)
        )

    async def are_blocked(self, user1: int, user2: int) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM blocked_pairs WHERE "
            "(user_id=? AND blocked_id=?) OR (user_id=? AND blocked_id=?)",
            (user1, user2, user2, user1)
        )
        return row is not None

    # ════════════════════════════════════════════════════════
    #  REPORT operations
    # ════════════════════════════════════════════════════════
    async def add_report(self, reporter_id: int, reported_id: int, reason: str):
        await self._exec(
            "INSERT INTO reports (reporter_id, reported_id, reason) VALUES (?, ?, ?)",
            (reporter_id, reported_id, reason)
        )
        # auto-ban check
        row = await self._fetchone(
            "SELECT COUNT(*) as c FROM reports WHERE reported_id=?",
            (reported_id,)
        )
        if row and row["c"] >= REPORT_BAN_THRESHOLD:
            await self.ban_user(reported_id, "Auto-ban: too many reports", 0)

    async def get_reports(self, reported_id: int = None):
        if reported_id:
            return await self._fetchall(
                "SELECT * FROM reports WHERE reported_id=? ORDER BY created_at DESC",
                (reported_id,)
            )
        return await self._fetchall(
            "SELECT * FROM reports ORDER BY created_at DESC LIMIT 50"
        )

    # ════════════════════════════════════════════════════════
    #  STATISTICS
    # ════════════════════════════════════════════════════════
    async def get_stats(self) -> dict:
        row  = await self._fetchone("SELECT * FROM statistics WHERE id=1")
        users = await self._fetchone("SELECT COUNT(*) as c FROM users")
        chats = await self._fetchone("SELECT COUNT(*) as c FROM active_chats")
        bans  = await self._fetchone("SELECT COUNT(*) as c FROM banned_users")
        rpts  = await self._fetchone("SELECT COUNT(*) as c FROM reports")
        return {
            "total_users":   users["c"]  if users else 0,
            "total_chats":   row["total_chats"] if row else 0,
            "active_chats":  chats["c"]  if chats else 0,
            "banned_users":  bans["c"]   if bans  else 0,
            "total_reports": rpts["c"]   if rpts  else 0,
        }

    async def get_all_user_ids(self) -> list:
        rows = await self._fetchall(
            "SELECT user_id FROM users WHERE is_banned=0"
        )
        return [r["user_id"] for r in rows]

    async def get_banned_list(self):
        return await self._fetchall(
            "SELECT b.user_id, b.reason, b.banned_at, u.username, u.first_name "
            "FROM banned_users b LEFT JOIN users u ON b.user_id=u.user_id "
            "ORDER BY b.banned_at DESC LIMIT 20"
        )
