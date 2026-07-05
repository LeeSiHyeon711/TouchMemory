"""raw SQL 기반 CRUD Repository (FEAT-01 범위).

각 함수는 열린 conn을 인자로 받는다. 쓰기 성공 시 commit, 예외 시 rollback 후 재전파.
커넥션을 열거나 닫지 않는다(설계서 8-4 — close 책임은 호출측).
"""
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import load_settings
from .models import (
    Channel,
    EventType,
    MemoryItem,
    MemoryItemCreate,
    MemoryItemUpdate,
)


def _now() -> str:
    tz = load_settings().tz
    return datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds")


def _row_to_item(row: sqlite3.Row) -> MemoryItem:
    return MemoryItem(**dict(row))


def create_item(conn: sqlite3.Connection, data: MemoryItemCreate) -> MemoryItem:
    now = _now()
    try:
        cur = conn.execute(
            """
            INSERT INTO memory_items
                (content, project_tag, is_done, persistent_reminder,
                 remind_type, remind_date, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (
                data.content,
                data.project_tag,
                int(data.persistent_reminder),
                data.remind_type.value,
                data.remind_date,
                now,
                now,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    item = get_item(conn, cur.lastrowid)
    assert item is not None
    return item


def get_item(conn: sqlite3.Connection, item_id: int) -> MemoryItem | None:
    row = conn.execute(
        "SELECT * FROM memory_items WHERE id = ?", (item_id,)
    ).fetchone()
    return _row_to_item(row) if row else None


def list_items(
    conn: sqlite3.Connection,
    *,
    project: str | None = None,
    status: str = "all",
    today: str | None = None,
) -> list[MemoryItem]:
    clauses: list[str] = []
    params: list[object] = []

    if project is not None:
        clauses.append("project_tag = ?")
        params.append(project)

    if status == "todo":
        clauses.append("is_done = 0")
    elif status == "done":
        clauses.append("is_done = 1")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM memory_items {where} ORDER BY id", params
    ).fetchall()
    return [_row_to_item(row) for row in rows]


def update_item(
    conn: sqlite3.Connection, item_id: int, patch: MemoryItemUpdate
) -> MemoryItem | None:
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        return get_item(conn, item_id)

    set_clauses = []
    params: list[object] = []
    for key, value in fields.items():
        if key in ("is_done", "persistent_reminder"):
            value = int(value)
        elif key == "remind_type":
            value = value.value if hasattr(value, "value") else value
        set_clauses.append(f"{key} = ?")
        params.append(value)

    set_clauses.append("updated_at = ?")
    params.append(_now())
    params.append(item_id)

    try:
        conn.execute(
            f"UPDATE memory_items SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_item(conn, item_id)


def delete_item(conn: sqlite3.Connection, item_id: int) -> bool:
    try:
        cur = conn.execute("DELETE FROM memory_items WHERE id = ?", (item_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return cur.rowcount > 0


def add_event(
    conn: sqlite3.Connection,
    event_type: EventType,
    channel: Channel,
    item_id: int | None = None,
) -> None:
    try:
        conn.execute(
            """
            INSERT INTO usage_events (event_type, item_id, channel, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_type.value, item_id, channel.value, _now()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
