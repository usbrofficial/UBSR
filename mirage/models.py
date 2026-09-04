"""Plain data records used throughout the app."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


def _loads(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Profile:
    name: str
    handle: str
    bio: str = ""
    avatar_path: Optional[str] = None
    created_at: float = 0.0

    @classmethod
    def from_row(cls, row) -> "Profile":
        return cls(
            name=row["name"],
            handle=row["handle"],
            bio=row["bio"] or "",
            avatar_path=row["avatar_path"],
            created_at=row["created_at"],
        )


@dataclass
class Persona:
    id: int
    name: str
    handle: str
    bio: str
    personality: str
    style: str
    appearance: str
    interests: list = field(default_factory=list)
    palette: list = field(default_factory=list)
    avatar_path: Optional[str] = None
    follower_count: int = 0
    follows_me: bool = False
    followed: bool = False
    notes: str = ""
    is_seed: bool = False
    created_at: float = 0.0

    @classmethod
    def from_row(cls, row) -> "Persona":
        return cls(
            id=row["id"],
            name=row["name"],
            handle=row["handle"],
            bio=row["bio"] or "",
            personality=row["personality"] or "",
            style=row["style"] or "",
            appearance=row["appearance"] or "",
            interests=_loads(row["interests"], []),
            palette=_loads(row["palette"], []),
            avatar_path=row["avatar_path"],
            follower_count=row["follower_count"] or 0,
            follows_me=bool(row["follows_me"]),
            followed=bool(row["followed"]),
            notes=row["notes"] or "",
            is_seed=bool(row["is_seed"]),
            created_at=row["created_at"],
        )


@dataclass
class Post:
    id: int
    author_type: str  # "me" or "persona"
    author_id: int  # 0 for me
    caption: str
    image_path: Optional[str]
    image_prompt: str
    like_count: int
    liked_by_me: bool
    created_at: float
    comment_count: int = 0

    @classmethod
    def from_row(cls, row) -> "Post":
        keys = row.keys()
        return cls(
            id=row["id"],
            author_type=row["author_type"],
            author_id=row["author_id"],
            caption=row["caption"] or "",
            image_path=row["image_path"],
            image_prompt=row["image_prompt"] or "",
            like_count=row["like_count"] or 0,
            liked_by_me=bool(row["liked_by_me"]),
            created_at=row["created_at"],
            comment_count=row["comment_count"] if "comment_count" in keys else 0,
        )

    @property
    def is_mine(self) -> bool:
        return self.author_type == "me"


@dataclass
class Comment:
    id: int
    post_id: int
    author_type: str
    author_id: int
    text: str
    created_at: float

    @classmethod
    def from_row(cls, row) -> "Comment":
        return cls(
            id=row["id"],
            post_id=row["post_id"],
            author_type=row["author_type"],
            author_id=row["author_id"],
            text=row["text"],
            created_at=row["created_at"],
        )


@dataclass
class Conversation:
    id: int
    persona_id: int
    created_at: float
    last_message_at: float
    unread: int
    last_text: str = ""

    @classmethod
    def from_row(cls, row) -> "Conversation":
        keys = row.keys()
        return cls(
            id=row["id"],
            persona_id=row["persona_id"],
            created_at=row["created_at"],
            last_message_at=row["last_message_at"] or row["created_at"],
            unread=row["unread"] or 0,
            last_text=row["last_text"] if "last_text" in keys and row["last_text"] else "",
        )


@dataclass
class Message:
    id: int
    conversation_id: int
    sender: str  # "me" or "persona"
    text: str
    image_path: Optional[str]
    created_at: float

    @classmethod
    def from_row(cls, row) -> "Message":
        return cls(
            id=row["id"],
            conversation_id=row["conversation_id"],
            sender=row["sender"],
            text=row["text"] or "",
            image_path=row["image_path"],
            created_at=row["created_at"],
        )


@dataclass
class Activity:
    id: int
    kind: str  # like, comment, reply, follow, message, post
    persona_id: int
    post_id: Optional[int]
    text: str
    created_at: float
    seen: bool

    @classmethod
    def from_row(cls, row) -> "Activity":
        return cls(
            id=row["id"],
            kind=row["kind"],
            persona_id=row["persona_id"],
            post_id=row["post_id"],
            text=row["text"] or "",
            created_at=row["created_at"],
            seen=bool(row["seen"]),
        )
