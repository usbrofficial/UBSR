"""SQLite storage for profiles, personas, posts, comments and messages."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

from ubsr.models import Activity, Comment, Conversation, Message, Persona, Post, Profile

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    handle TEXT NOT NULL,
    bio TEXT DEFAULT '',
    avatar_path TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS personas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    handle TEXT NOT NULL UNIQUE,
    bio TEXT DEFAULT '',
    personality TEXT DEFAULT '',
    style TEXT DEFAULT '',
    appearance TEXT DEFAULT '',
    interests TEXT DEFAULT '[]',
    palette TEXT DEFAULT '[]',
    avatar_path TEXT,
    follower_count INTEGER DEFAULT 0,
    follows_me INTEGER DEFAULT 0,
    followed INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    is_seed INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_type TEXT NOT NULL,
    author_id INTEGER NOT NULL DEFAULT 0,
    caption TEXT DEFAULT '',
    image_path TEXT,
    image_prompt TEXT DEFAULT '',
    like_count INTEGER DEFAULT 0,
    liked_by_me INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC);
CREATE TABLE IF NOT EXISTS post_likes (
    post_id INTEGER NOT NULL,
    persona_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (post_id, persona_id)
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    author_type TEXT NOT NULL,
    author_id INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id, created_at);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id INTEGER NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    last_message_at REAL,
    unread INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    sender TEXT NOT NULL,
    text TEXT DEFAULT '',
    image_path TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    persona_id INTEGER NOT NULL,
    post_id INTEGER,
    text TEXT DEFAULT '',
    created_at REAL NOT NULL,
    seen INTEGER DEFAULT 0
);
"""


class Database:
    """Thread-safe wrapper around a single SQLite connection."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # low level -------------------------------------------------------
    def _exec(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def _one(self, sql: str, params: Iterable = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    # profile ---------------------------------------------------------
    def get_profile(self) -> Optional[Profile]:
        row = self._one("SELECT * FROM profile WHERE id = 1")
        return Profile.from_row(row) if row else None

    def save_profile(self, name: str, handle: str, bio: str, avatar_path: Optional[str]) -> Profile:
        existing = self._one("SELECT created_at FROM profile WHERE id = 1")
        created = existing["created_at"] if existing else time.time()
        self._exec(
            "INSERT INTO profile (id, name, handle, bio, avatar_path, created_at) VALUES (1, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, handle=excluded.handle, bio=excluded.bio, "
            "avatar_path=excluded.avatar_path",
            (name, handle, bio, avatar_path, created),
        )
        return self.get_profile()

    # personas --------------------------------------------------------
    def persona_count(self) -> int:
        return self._one("SELECT COUNT(*) AS n FROM personas")["n"]

    def add_persona(self, data: dict, is_seed: bool = False) -> Persona:
        handle = data["handle"].lstrip("@").lower()
        cur = self._exec(
            "INSERT INTO personas (name, handle, bio, personality, style, appearance, interests, palette, "
            "avatar_path, follower_count, follows_me, followed, notes, is_seed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data["name"],
                handle,
                data.get("bio", ""),
                data.get("personality", ""),
                data.get("style", ""),
                data.get("appearance", ""),
                json.dumps(data.get("interests", [])),
                json.dumps(data.get("palette", [])),
                data.get("avatar_path"),
                int(data.get("follower_count", 0)),
                int(bool(data.get("follows_me", False))),
                int(bool(data.get("followed", False))),
                data.get("notes", ""),
                int(is_seed),
                data.get("created_at", time.time()),
            ),
        )
        return self.get_persona(cur.lastrowid)

    def get_persona(self, persona_id: int) -> Optional[Persona]:
        row = self._one("SELECT * FROM personas WHERE id = ?", (persona_id,))
        return Persona.from_row(row) if row else None

    def get_persona_by_handle(self, handle: str) -> Optional[Persona]:
        row = self._one("SELECT * FROM personas WHERE handle = ?", (handle.lstrip("@").lower(),))
        return Persona.from_row(row) if row else None

    def list_personas(self, search: str = "") -> list[Persona]:
        if search:
            like = f"%{search.strip().lstrip('@').lower()}%"
            rows = self._query(
                "SELECT * FROM personas WHERE lower(name) LIKE ? OR handle LIKE ? OR lower(bio) LIKE ? "
                "ORDER BY followed DESC, follower_count DESC",
                (like, like, like),
            )
        else:
            rows = self._query("SELECT * FROM personas ORDER BY followed DESC, follower_count DESC")
        return [Persona.from_row(r) for r in rows]

    def all_handles(self) -> list[str]:
        return [r["handle"] for r in self._query("SELECT handle FROM personas")]

    def set_followed(self, persona_id: int, followed: bool) -> None:
        self._exec("UPDATE personas SET followed = ? WHERE id = ?", (int(followed), persona_id))

    def set_follows_me(self, persona_id: int, follows: bool) -> None:
        self._exec("UPDATE personas SET follows_me = ? WHERE id = ?", (int(follows), persona_id))

    def set_persona_avatar(self, persona_id: int, path: Optional[str]) -> None:
        self._exec("UPDATE personas SET avatar_path = ? WHERE id = ?", (path, persona_id))

    def update_persona_notes(self, persona_id: int, notes: str) -> None:
        self._exec("UPDATE personas SET notes = ? WHERE id = ?", (notes[:4000], persona_id))

    def bump_followers(self, persona_id: int, delta: int) -> None:
        self._exec(
            "UPDATE personas SET follower_count = MAX(0, follower_count + ?) WHERE id = ?",
            (delta, persona_id),
        )

    def delete_persona(self, persona_id: int) -> None:
        with self._lock:
            conv = self._one("SELECT id FROM conversations WHERE persona_id = ?", (persona_id,))
            if conv:
                self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv["id"],))
                self._conn.execute("DELETE FROM conversations WHERE id = ?", (conv["id"],))
            post_ids = [r["id"] for r in self._query(
                "SELECT id FROM posts WHERE author_type = 'persona' AND author_id = ?", (persona_id,))]
            for pid in post_ids:
                self._conn.execute("DELETE FROM comments WHERE post_id = ?", (pid,))
                self._conn.execute("DELETE FROM post_likes WHERE post_id = ?", (pid,))
            self._conn.execute("DELETE FROM posts WHERE author_type = 'persona' AND author_id = ?", (persona_id,))
            self._conn.execute("DELETE FROM comments WHERE author_type = 'persona' AND author_id = ?", (persona_id,))
            self._conn.execute("DELETE FROM post_likes WHERE persona_id = ?", (persona_id,))
            self._conn.execute("DELETE FROM activity WHERE persona_id = ?", (persona_id,))
            self._conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
            self._conn.commit()

    # posts -----------------------------------------------------------
    _POST_SELECT = (
        "SELECT p.*, (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count FROM posts p "
    )

    def add_post(self, author_type: str, author_id: int, caption: str, image_path: Optional[str],
                 image_prompt: str = "", like_count: int = 0, created_at: Optional[float] = None) -> Post:
        cur = self._exec(
            "INSERT INTO posts (author_type, author_id, caption, image_path, image_prompt, like_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (author_type, author_id, caption, image_path, image_prompt, like_count, created_at or time.time()),
        )
        return self.get_post(cur.lastrowid)

    def get_post(self, post_id: int) -> Optional[Post]:
        row = self._one(self._POST_SELECT + "WHERE p.id = ?", (post_id,))
        return Post.from_row(row) if row else None

    def list_feed(self, limit: int = 60, offset: int = 0, followed_only: bool = False) -> list[Post]:
        sql = self._POST_SELECT
        if followed_only:
            sql += ("WHERE p.author_type = 'me' OR p.author_id IN (SELECT id FROM personas WHERE followed = 1) ")
        sql += "ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
        return [Post.from_row(r) for r in self._query(sql, (limit, offset))]

    def list_posts_by(self, author_type: str, author_id: int, limit: int = 100) -> list[Post]:
        rows = self._query(
            self._POST_SELECT + "WHERE p.author_type = ? AND p.author_id = ? ORDER BY p.created_at DESC LIMIT ?",
            (author_type, author_id, limit),
        )
        return [Post.from_row(r) for r in rows]

    def count_posts_by(self, author_type: str, author_id: int) -> int:
        return self._one(
            "SELECT COUNT(*) AS n FROM posts WHERE author_type = ? AND author_id = ?", (author_type, author_id)
        )["n"]

    def delete_post(self, post_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
            self._conn.execute("DELETE FROM post_likes WHERE post_id = ?", (post_id,))
            self._conn.execute("DELETE FROM activity WHERE post_id = ?", (post_id,))
            self._conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            self._conn.commit()

    def set_liked_by_me(self, post_id: int, liked: bool) -> Post:
        post = self.get_post(post_id)
        if post and post.liked_by_me != liked:
            self._exec(
                "UPDATE posts SET liked_by_me = ?, like_count = MAX(0, like_count + ?) WHERE id = ?",
                (int(liked), 1 if liked else -1, post_id),
            )
        return self.get_post(post_id)

    def add_persona_like(self, post_id: int, persona_id: int) -> bool:
        """Returns True if this was a new like."""
        with self._lock:
            exists = self._one(
                "SELECT 1 FROM post_likes WHERE post_id = ? AND persona_id = ?", (post_id, persona_id)
            )
            if exists:
                return False
            self._conn.execute(
                "INSERT INTO post_likes (post_id, persona_id, created_at) VALUES (?, ?, ?)",
                (post_id, persona_id, time.time()),
            )
            self._conn.execute("UPDATE posts SET like_count = like_count + 1 WHERE id = ?", (post_id,))
            self._conn.commit()
            return True

    def post_likers(self, post_id: int) -> list[int]:
        return [r["persona_id"] for r in self._query(
            "SELECT persona_id FROM post_likes WHERE post_id = ? ORDER BY created_at DESC", (post_id,))]

    # comments --------------------------------------------------------
    def add_comment(self, post_id: int, author_type: str, author_id: int, text: str) -> Comment:
        cur = self._exec(
            "INSERT INTO comments (post_id, author_type, author_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (post_id, author_type, author_id, text.strip(), time.time()),
        )
        row = self._one("SELECT * FROM comments WHERE id = ?", (cur.lastrowid,))
        return Comment.from_row(row)

    def list_comments(self, post_id: int) -> list[Comment]:
        rows = self._query("SELECT * FROM comments WHERE post_id = ? ORDER BY created_at ASC", (post_id,))
        return [Comment.from_row(r) for r in rows]

    def persona_commented(self, post_id: int, persona_id: int) -> bool:
        return self._one(
            "SELECT 1 FROM comments WHERE post_id = ? AND author_type = 'persona' AND author_id = ?",
            (post_id, persona_id),
        ) is not None

    # conversations & messages ----------------------------------------
    def get_or_create_conversation(self, persona_id: int) -> Conversation:
        row = self._one("SELECT * FROM conversations WHERE persona_id = ?", (persona_id,))
        if not row:
            now = time.time()
            self._exec(
                "INSERT INTO conversations (persona_id, created_at, last_message_at, unread) VALUES (?, ?, ?, 0)",
                (persona_id, now, now),
            )
            row = self._one("SELECT * FROM conversations WHERE persona_id = ?", (persona_id,))
        return Conversation.from_row(row)

    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        row = self._one(
            "SELECT c.*, (SELECT text FROM messages m WHERE m.conversation_id = c.id "
            "ORDER BY m.created_at DESC LIMIT 1) AS last_text FROM conversations c WHERE c.id = ?",
            (conversation_id,),
        )
        return Conversation.from_row(row) if row else None

    def list_conversations(self) -> list[Conversation]:
        rows = self._query(
            "SELECT c.*, (SELECT text FROM messages m WHERE m.conversation_id = c.id "
            "ORDER BY m.created_at DESC LIMIT 1) AS last_text FROM conversations c "
            "WHERE EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id) "
            "ORDER BY c.last_message_at DESC"
        )
        return [Conversation.from_row(r) for r in rows]

    def add_message(self, conversation_id: int, sender: str, text: str,
                    image_path: Optional[str] = None) -> Message:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, sender, text, image_path, created_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, sender, text.strip(), image_path, now),
            )
            unread_delta = 1 if sender == "persona" else 0
            self._conn.execute(
                "UPDATE conversations SET last_message_at = ?, unread = unread + ? WHERE id = ?",
                (now, unread_delta, conversation_id),
            )
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return Message.from_row(row)

    def list_messages(self, conversation_id: int, limit: int = 500) -> list[Message]:
        rows = self._query(
            "SELECT * FROM (SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?) "
            "ORDER BY created_at ASC",
            (conversation_id, limit),
        )
        return [Message.from_row(r) for r in rows]

    def mark_conversation_read(self, conversation_id: int) -> None:
        self._exec("UPDATE conversations SET unread = 0 WHERE id = ?", (conversation_id,))

    def total_unread(self) -> int:
        return self._one("SELECT COALESCE(SUM(unread), 0) AS n FROM conversations")["n"]

    def delete_conversation(self, conversation_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            self._conn.commit()

    # activity --------------------------------------------------------
    def add_activity(self, kind: str, persona_id: int, post_id: Optional[int] = None, text: str = "") -> Activity:
        cur = self._exec(
            "INSERT INTO activity (kind, persona_id, post_id, text, created_at, seen) VALUES (?, ?, ?, ?, ?, 0)",
            (kind, persona_id, post_id, text, time.time()),
        )
        return Activity.from_row(self._one("SELECT * FROM activity WHERE id = ?", (cur.lastrowid,)))

    def list_activity(self, limit: int = 100) -> list[Activity]:
        rows = self._query("SELECT * FROM activity ORDER BY created_at DESC LIMIT ?", (limit,))
        return [Activity.from_row(r) for r in rows]

    def unseen_activity(self) -> int:
        return self._one("SELECT COUNT(*) AS n FROM activity WHERE seen = 0")["n"]

    def mark_activity_seen(self) -> None:
        self._exec("UPDATE activity SET seen = 1 WHERE seen = 0")

    # bulk ------------------------------------------------------------
    def wipe_everything(self) -> None:
        with self._lock:
            for table in ("messages", "conversations", "activity", "post_likes", "comments", "posts",
                          "personas", "profile"):
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.commit()
