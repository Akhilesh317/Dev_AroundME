"""
Chat repository for SQLite (conversations + messages).

Usage:
    from chat_repository import create_conversation, add_message, list_messages

    cid = create_conversation(title="Demo")
    add_message(cid, role="user", text="Hello")
    add_message(cid, role="assistant", text="Hi! How can I help?")
    msgs = list_messages(cid)
"""

import json
import time
import random
import string
from typing import Any, Dict, List, Optional, TypedDict, Literal

from db_conn import get_conn

Role = Literal["user", "assistant", "system", "tool"]

class MessageRow(TypedDict, total=False):
    id: str
    role: Role
    text: str
    contentJson: Optional[Dict[str, Any]]
    createdAt: int
    parentId: Optional[str]

def now_ms() -> int:
    return int(time.time() * 1000)

def cuid(prefix: str = "c") -> str:
    # Compact collision-safe-ish ID for our purposes
    rnd = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}_{int(time.time()*1000):x}{rnd}"

# -----------------------------
# Conversations
# -----------------------------

def create_conversation(title: str = "New conversation", user_id: Optional[str] = None) -> str:
    cid = cuid("cv")
    ts = now_ms()
    with get_conn() as con:
        con.execute(
            """
            INSERT INTO conversations (id, user_id, title, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (cid, user_id, title, ts, ts),
        )
    return cid

def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as con:
        cur = con.execute(
            "SELECT id, user_id, title, status, created_at, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

def update_conversation_title(conversation_id: str, title: str) -> None:
    with get_conn() as con:
        con.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now_ms(), conversation_id),
        )

# -----------------------------
# Messages
# -----------------------------

def add_message(
    conversation_id: str,
    role: Role,
    text: str,
    content_json: Optional[Dict[str, Any]] = None,
    parent_id: Optional[str] = None,
) -> str:
    mid = cuid("m")
    ts = now_ms()
    with get_conn() as con:
        con.execute(
            """
            INSERT INTO messages (id, conversation_id, role, text, content_json, created_at, parent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mid,
                conversation_id,
                role,
                text,
                json.dumps(content_json) if content_json is not None else None,
                ts,
                parent_id,
            ),
        )
    return mid

def list_messages(
    conversation_id: str,
    limit: int = 30,
    before_ms: Optional[int] = None,
) -> List[MessageRow]:
    sql = [
        "SELECT id, role, text, content_json, created_at, parent_id",
        "FROM messages",
        "WHERE conversation_id = ?",
    ]
    params: List[Any] = [conversation_id]

    if before_ms is not None:
        sql.append("AND created_at < ?")
        params.append(before_ms)

    sql.append("ORDER BY created_at DESC LIMIT ?")
    params.append(limit)

    query = " ".join(sql)

    with get_conn() as con:
        rows = con.execute(query, tuple(params)).fetchall()

    out: List[MessageRow] = []
    for r in rows:
        content = None
        if r["content_json"]:
            try:
                content = json.loads(r["content_json"])
            except Exception:
                content = None
        out.append(
            MessageRow(
                id=r["id"],
                role=r["role"],
                text=r["text"],
                contentJson=content,
                createdAt=r["created_at"],
                parentId=r["parent_id"],
            )
        )
    return out

# -----------------------------
# Quick demo (manual run)
# -----------------------------

if __name__ == "__main__":
    cid = create_conversation("Repo self-test")
    print("Created conversation:", cid)
    add_message(cid, "user", "Hi AroundMe")
    add_message(cid, "assistant", "Hello! Ready to search places when tools are wired.")
    msgs = list_messages(cid)
    print("Messages:")
    for m in msgs:
        print(m)
