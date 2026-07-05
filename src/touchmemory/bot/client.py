"""Discord 봇 부트스트랩 및 슬래시 커맨드 4종 (FEAT-03 범위).

모든 데이터 접근은 `api_client.TouchMemoryAPI`를 통해서만 이뤄지며
(SQLite 직접 접근 금지, FEAT-03 10절) 능동 알림 스케줄러·`/설정`(FEAT-04)·
CLI(FEAT-05)·항목 삭제/수정 커맨드는 이 이슈 범위 밖이라 구현하지 않는다.
"""
import logging
import os

import discord
from discord import app_commands

from .api_client import APIConnectionError, APIRequestError, TouchMemoryAPI

logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8787")
GUILD_ID = os.environ.get("GUILD_ID")

_REMIND_TYPES = {"none", "once", "daily"}
_STATUS_MAP = {"전체": "all", "미완료": "todo", "완료": "done"}
_CONNECTION_ERROR_MSG = "데이터 서버에 연결할 수 없습니다."

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)
api = TouchMemoryAPI(API_BASE_URL)


def _guild_object() -> discord.Object | None:
    return discord.Object(id=int(GUILD_ID)) if GUILD_ID else None


@bot.event
async def on_ready():
    guild = _guild_object()
    if guild is not None:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        logger.warning("GUILD_ID가 설정되지 않아 전역으로 커맨드를 동기화합니다(반영 지연 가능).")
        await tree.sync()
    logger.info("봇 온라인: %s", bot.user)


def _format_item_line(item: dict) -> str:
    status = "완료" if item["is_done"] else "미완료"
    return f"`#{item['id']}` {item['content']} ({status})"


def _group_by_project(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        tag = item.get("project_tag") or "미분류"
        groups.setdefault(tag, []).append(item)
    return groups


@tree.command(name="기억등록", description="새 기억 항목을 등록합니다")
@app_commands.describe(
    내용="등록할 내용",
    프로젝트="프로젝트 태그(선택)",
    리마인드="none/once/daily 중 하나 (기본 none)",
    날짜="리마인드=once일 때 YYYY-MM-DD",
    지속="지속 리마인드 여부(기본 거짓)",
)
async def cmd_add(
    interaction: discord.Interaction,
    내용: str,
    프로젝트: str | None = None,
    리마인드: str = "none",
    날짜: str | None = None,
    지속: bool = False,
) -> None:
    await interaction.response.defer()
    if 리마인드 not in _REMIND_TYPES:
        await interaction.followup.send(
            f"리마인드 값은 {', '.join(sorted(_REMIND_TYPES))} 중 하나여야 합니다."
        )
        return
    try:
        item = await api.create_item(
            content=내용,
            project_tag=프로젝트,
            persistent_reminder=지속,
            remind_type=리마인드,
            remind_date=날짜,
        )
    except APIConnectionError:
        await interaction.followup.send(_CONNECTION_ERROR_MSG)
        return
    except APIRequestError as exc:
        await interaction.followup.send(str(exc.detail))
        return
    await interaction.followup.send(f"등록 완료: `#{item['id']}` {item['content']}")


@tree.command(name="기억조회", description="등록된 기억 항목을 조회합니다")
@app_commands.describe(프로젝트="프로젝트 태그 필터(선택)", 상태="전체/미완료/완료 중 하나 (기본 전체)")
async def cmd_list(
    interaction: discord.Interaction,
    프로젝트: str | None = None,
    상태: str = "전체",
) -> None:
    await interaction.response.defer()
    status = _STATUS_MAP.get(상태)
    if status is None:
        await interaction.followup.send(
            f"상태 값은 {', '.join(_STATUS_MAP)} 중 하나여야 합니다."
        )
        return
    try:
        items = await api.list_items(project=프로젝트, status=status)
    except APIConnectionError:
        await interaction.followup.send(_CONNECTION_ERROR_MSG)
        return
    except APIRequestError as exc:
        await interaction.followup.send(str(exc.detail))
        return
    if not items:
        await interaction.followup.send("등록된 항목이 없습니다.")
        return
    embed = discord.Embed(title="기억 조회 결과")
    for tag, group_items in _group_by_project(items).items():
        lines = [_format_item_line(item) for item in group_items]
        embed.add_field(name=tag, value="\n".join(lines), inline=False)
    await interaction.followup.send(embed=embed)


@tree.command(name="기억완료", description="기억 항목을 완료 처리합니다")
@app_commands.describe(id="완료 처리할 항목 id")
async def cmd_complete(interaction: discord.Interaction, id: int) -> None:
    await interaction.response.defer()
    try:
        item = await api.complete_item(id)
    except APIConnectionError:
        await interaction.followup.send(_CONNECTION_ERROR_MSG)
        return
    except APIRequestError as exc:
        if exc.status_code == 404:
            await interaction.followup.send("해당 항목을 찾을 수 없습니다.")
        else:
            await interaction.followup.send(str(exc.detail))
        return
    note = " (지속 리마인드는 계속 유지됩니다)" if item.get("persistent_reminder") else ""
    await interaction.followup.send(f"완료 처리: `#{item['id']}` {item['content']}{note}")


@tree.command(name="오늘요약", description="오늘 알림 대상 기억을 요약합니다")
async def cmd_today(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    try:
        digest = await api.get_today_digest()
    except APIConnectionError:
        await interaction.followup.send(_CONNECTION_ERROR_MSG)
        return
    except APIRequestError as exc:
        await interaction.followup.send(str(exc.detail))
        return
    if digest["total"] == 0:
        await interaction.followup.send("오늘 알림 대상 항목이 없습니다.")
        return
    embed = discord.Embed(title=f"오늘의 요약 ({digest['date']})")
    for group in digest["groups"]:
        tag = group["project_tag"] or "미분류"
        lines = [_format_item_line(item) for item in group["items"]]
        embed.add_field(name=tag, value="\n".join(lines), inline=False)
    await interaction.followup.send(embed=embed)


def run_bot() -> None:
    bot.run(DISCORD_TOKEN)
