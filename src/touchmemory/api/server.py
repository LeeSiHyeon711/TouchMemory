"""FastAPI 중앙 API 서버 (FEAT-02 범위).

커넥션은 요청 단위로 열고 닫는다(설계서 8-4) — get_db 의존성이 응답 후 close를 보장한다.
add_event 실패는 본 작업을 막지 않는다(7절) — 자동 기록은 best-effort로 감싼다.
"""
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request

from .. import repository
from ..config import load_settings
from ..db import get_conn, init_db
from ..digest import TodayDigest, build_today_digest
from ..models import (
    Channel,
    EventType,
    MemoryItem,
    MemoryItemCreate,
    MemoryItemUpdate,
    RemindType,
)

logger = logging.getLogger(__name__)

config = load_settings()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(config.db_path)
    yield


app = FastAPI(title="TouchMemory API", lifespan=lifespan)


def get_db():
    conn = get_conn(config.db_path)
    try:
        yield conn
    finally:
        conn.close()


def _channel(request: Request) -> Channel:
    raw = request.headers.get("X-Channel", "system")
    try:
        return Channel(raw)
    except ValueError:
        return Channel.system


def _today() -> str:
    return datetime.now(ZoneInfo(config.tz)).date().isoformat()


def _is_valid_date(value: str) -> bool:
    if not _DATE_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _validate_once(remind_type: RemindType, remind_date: str | None) -> None:
    if remind_type == RemindType.once and (
        not remind_date or not _is_valid_date(remind_date)
    ):
        raise HTTPException(
            status_code=400,
            detail="remind_type='once'이면 remind_date가 'YYYY-MM-DD' 형식으로 필요합니다.",
        )


def _safe_event(
    conn, event_type: EventType, channel: Channel, item_id: int | None
) -> None:
    try:
        repository.add_event(conn, event_type, channel, item_id)
    except Exception:
        logger.warning(
            "이벤트 기록 실패: event_type=%s item_id=%s", event_type, item_id,
            exc_info=True,
        )


@app.post("/items", response_model=MemoryItem)
def create_item(
    data: MemoryItemCreate, request: Request, conn=Depends(get_db)
) -> MemoryItem:
    _validate_once(data.remind_type, data.remind_date)
    item = repository.create_item(conn, data)
    _safe_event(conn, EventType.register, _channel(request), item.id)
    return item


@app.get("/items", response_model=list[MemoryItem])
def list_items(
    request: Request,
    project: str | None = None,
    status: str = "all",
    today: bool = False,
    conn=Depends(get_db),
) -> list[MemoryItem]:
    items = repository.list_items(conn, project=project, status=status)
    if today:
        digest = build_today_digest(conn, _today())
        digest_ids = {item.id for group in digest.groups for item in group.items}
        items = [item for item in items if item.id in digest_ids]
    _safe_event(conn, EventType.view, _channel(request), None)
    return items


@app.get("/items/{item_id}", response_model=MemoryItem)
def get_item(item_id: int, conn=Depends(get_db)) -> MemoryItem:
    item = repository.get_item(conn, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return item


@app.patch("/items/{item_id}", response_model=MemoryItem)
def update_item(
    item_id: int,
    patch: MemoryItemUpdate,
    request: Request,
    conn=Depends(get_db),
) -> MemoryItem:
    existing = repository.get_item(conn, item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="item not found")

    fields = patch.model_dump(exclude_unset=True)
    final_remind_type = fields.get("remind_type", existing.remind_type)
    final_remind_date = fields.get("remind_date", existing.remind_date)
    _validate_once(final_remind_type, final_remind_date)

    updated = repository.update_item(conn, item_id, patch)
    assert updated is not None
    if not existing.is_done and updated.is_done:
        _safe_event(conn, EventType.complete, _channel(request), item_id)
    return updated


@app.delete("/items/{item_id}")
def delete_item(item_id: int, conn=Depends(get_db)) -> dict[str, bool]:
    deleted = repository.delete_item(conn, item_id)
    return {"deleted": deleted}


@app.get("/digest/today", response_model=TodayDigest)
def get_digest_today(conn=Depends(get_db)) -> TodayDigest:
    return build_today_digest(conn, _today())


@app.post("/events")
def create_event(data: dict, conn=Depends(get_db)) -> dict[str, bool]:
    raw_type = data.get("event_type", EventType.notify.value)
    try:
        event_type = EventType(raw_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"알 수 없는 event_type: {raw_type}")
    item_id = data.get("item_id")
    repository.add_event(conn, event_type, Channel.system, item_id)
    return {"ok": True}


@app.get("/settings")
def get_settings(conn=Depends(get_db)) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


@app.patch("/settings")
def update_settings(patch: dict[str, str], conn=Depends(get_db)) -> dict[str, str]:
    for key, value in patch.items():
        repository.set_setting(conn, key, value)
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}
