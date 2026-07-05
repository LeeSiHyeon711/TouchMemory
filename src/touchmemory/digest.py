"""오늘 발송 대상 판정 — (A)(B)(C)(D) 4그룹 합집합 (FEAT-02 범위).

그룹 D 날짜 비교는 TZ(Asia/Seoul) 로컬 날짜 기준(substr(created_at,1,10))이다.
created_at은 로컬 벽시계+오프셋 ISO8601로 저장되므로 앞 10자가 곧 로컬 날짜다.
SQLite date()는 오프셋을 UTC로 변환해 KST 자정 부근 당일 항목을 '전날'로 오판하므로 사용하지 않는다.
"""
import sqlite3

from pydantic import BaseModel

from .models import MemoryItem


class DigestGroup(BaseModel):
    project_tag: str | None
    items: list[MemoryItem]


class TodayDigest(BaseModel):
    date: str
    total: int
    groups: list[DigestGroup]


def _row_to_item(row: sqlite3.Row) -> MemoryItem:
    return MemoryItem(**dict(row))


def build_today_digest(conn: sqlite3.Connection, today: str) -> TodayDigest:
    rows = conn.execute(
        """
        SELECT * FROM memory_items
        WHERE (remind_type = 'once' AND remind_date <= ? AND is_done = 0)
           OR (remind_type = 'daily' AND is_done = 0)
           OR (persistent_reminder = 1)
           OR (substr(created_at, 1, 10) < ? AND is_done = 0 AND remind_type = 'none')
        """,
        (today, today),
    ).fetchall()

    items_by_id: dict[int, MemoryItem] = {}
    for row in rows:
        item = _row_to_item(row)
        assert item.id is not None
        items_by_id[item.id] = item

    groups_map: dict[str | None, list[MemoryItem]] = {}
    for item in items_by_id.values():
        groups_map.setdefault(item.project_tag, []).append(item)

    groups = [
        DigestGroup(project_tag=tag, items=sorted(items, key=lambda i: i.id))
        for tag, items in sorted(
            groups_map.items(), key=lambda kv: (kv[0] is None, kv[0] or "")
        )
    ]

    return TodayDigest(date=today, total=len(items_by_id), groups=groups)
