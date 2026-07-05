"""매일 지정 시각 능동 알림 스케줄러 (FEAT-04 범위).

정규 스케줄(tasks.loop)과 on_ready 보정 발송이 동일한 `asyncio.Lock`으로
직렬화되어 동시 발송을 막는다(설계서 8-3). 발송 상태(`last_digest_date`)는
프로세스 로컬이 아니라 API(settings)에 저장돼 있으므로, 매 발송 시도마다
API에서 다시 읽어 판정한다(봇이 SQLite에 직접 접근하지 않는다, FEAT-04 10절).
"""
import logging
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

import asyncio
import discord
from discord.ext import tasks

from .api_client import APIConnectionError, APIRequestError, TouchMemoryAPI

logger = logging.getLogger(__name__)


def _format_digest_item(item: dict) -> str:
    status = "✅" if item["is_done"] else "⬜"
    persistent = "🔁" if item.get("persistent_reminder") else ""
    return f"{status}{persistent} `#{item['id']}` {item['content']}"


def format_digest_message(digest: dict) -> discord.Embed:
    """digest 조회 결과를 Embed로 포맷한다. `/오늘요약`도 이 함수를 재사용한다."""
    embed = discord.Embed(title=f"오늘의 요약 ({digest['date']})")
    if digest["total"] == 0:
        embed.description = "오늘 다시 볼 항목이 없습니다."
        return embed
    for group in digest["groups"]:
        tag = group["project_tag"] or "미분류"
        lines = [_format_digest_item(item) for item in group["items"]]
        embed.add_field(name=tag, value="\n".join(lines), inline=False)
    return embed


def _parse_time(value: str, tz: str) -> dt_time:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.time().replace(tzinfo=ZoneInfo(tz))


class DigestScheduler:
    def __init__(self, bot: discord.Client, api: TouchMemoryAPI, tz: str):
        self.bot = bot
        self.api = api
        self.tz = tz
        self.notify_channel_id: str | None = None
        self._lock = asyncio.Lock()
        self._loop_task: tasks.Loop | None = None

    def start(self, notify_time: str, notify_channel_id: str | None) -> None:
        """루프 등록/재등록. 시각 변경 시에도 이 메서드로 재적용(재시작)한다."""
        self.notify_channel_id = notify_channel_id
        if self._loop_task is not None:
            self._loop_task.cancel()

        parsed = _parse_time(notify_time, self.tz)
        scheduler = self

        @tasks.loop(time=parsed)
        async def _loop():
            await scheduler.send_daily_digest()

        self._loop_task = _loop
        self._loop_task.start()

    def set_channel(self, notify_channel_id: str) -> None:
        self.notify_channel_id = notify_channel_id

    async def apply_time_change(self, new_time: str) -> None:
        self.start(new_time, self.notify_channel_id)

    async def send_daily_digest(self, force: bool = False) -> bool:
        async with self._lock:
            today = datetime.now(ZoneInfo(self.tz)).date().isoformat()

            if not force:
                try:
                    settings = await self.api.get_settings()
                except (APIConnectionError, APIRequestError):
                    logger.warning("설정 조회 실패로 발송을 건너뜁니다.", exc_info=True)
                    return False
                if settings.get("last_digest_date") == today:
                    return False

            if not self.notify_channel_id:
                logger.warning("notify_channel_id가 설정되지 않아 발송을 건너뜁니다.")
                return False

            channel = self.bot.get_channel(int(self.notify_channel_id))
            if channel is None:
                logger.warning(
                    "channel_id=%s 채널을 찾을 수 없어 발송을 건너뜁니다.",
                    self.notify_channel_id,
                )
                return False

            try:
                digest = await self.api.get_today_digest()
            except (APIConnectionError, APIRequestError):
                logger.warning("digest 조회 실패로 발송을 건너뜁니다.", exc_info=True)
                return False

            try:
                await channel.send(embed=format_digest_message(digest))
            except Exception:
                logger.warning(
                    "채널 발송 실패로 last_digest_date를 갱신하지 않습니다.", exc_info=True
                )
                return False

            # 발송 성공 시 순서 고정: (a) last_digest_date 먼저 (b) notify 이벤트는 best-effort
            try:
                await self.api.patch_settings(last_digest_date=today)
            except (APIConnectionError, APIRequestError):
                logger.warning(
                    "last_digest_date 갱신 실패(다음 보정에서 재시도될 수 있음)", exc_info=True
                )
                return False

            try:
                await self.api.post_event(event_type="notify")
            except (APIConnectionError, APIRequestError):
                logger.warning("notify 이벤트 기록 실패(무시 가능)", exc_info=True)

            return True

    async def catch_up_on_ready(self) -> bool:
        try:
            settings = await self.api.get_settings()
        except (APIConnectionError, APIRequestError):
            logger.warning("설정 조회 실패로 보정 발송을 건너뜁니다.", exc_info=True)
            return False

        today = datetime.now(ZoneInfo(self.tz)).date().isoformat()
        if settings.get("last_digest_date") == today:
            return False

        notify_time_str = settings.get("notify_time")
        if not notify_time_str:
            return False
        try:
            notify_time = datetime.strptime(notify_time_str, "%H:%M").time()
        except ValueError:
            logger.warning("notify_time 형식 오류로 보정 발송을 건너뜁니다: %s", notify_time_str)
            return False

        now = datetime.now(ZoneInfo(self.tz))
        if now.time() < notify_time:
            return False

        return await self.send_daily_digest()
