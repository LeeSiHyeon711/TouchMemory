"""도메인 모델 — Pydantic v2 (FEAT-01 범위)."""
from enum import Enum

from pydantic import BaseModel


class RemindType(str, Enum):
    none = "none"
    once = "once"
    daily = "daily"


class EventType(str, Enum):
    register = "register"
    view = "view"
    complete = "complete"
    notify = "notify"


class Channel(str, Enum):
    discord = "discord"
    claude_code = "claude_code"
    system = "system"


class MemoryItem(BaseModel):
    id: int | None = None
    content: str
    project_tag: str | None = None
    is_done: bool = False
    persistent_reminder: bool = False
    remind_type: RemindType = RemindType.none
    remind_date: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MemoryItemCreate(BaseModel):
    content: str
    project_tag: str | None = None
    persistent_reminder: bool = False
    remind_type: RemindType = RemindType.none
    remind_date: str | None = None


class MemoryItemUpdate(BaseModel):
    content: str | None = None
    project_tag: str | None = None
    is_done: bool | None = None
    persistent_reminder: bool | None = None
    remind_type: RemindType | None = None
    remind_date: str | None = None


class UsageEvent(BaseModel):
    id: int | None = None
    event_type: EventType
    item_id: int | None = None
    channel: Channel
    created_at: str | None = None
