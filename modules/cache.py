from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from modules.database import Database
from modules.hiscores import HiscoresClient
from modules.roles import RoleManager


LOGGER = logging.getLogger(__name__)


class StatsCache:
    def __init__(self, db: Database, hiscores: HiscoresClient, interval_minutes: int = 30) -> None:
        self.db = db
        self.hiscores = hiscores
        self.interval_minutes = interval_minutes
        self._bot: commands.Bot | None = None
        self._roles: RoleManager | None = None
        self._lock = asyncio.Lock()
        self.refresh_loop.change_interval(minutes=interval_minutes)

    def start(self, bot: commands.Bot, roles: RoleManager) -> None:
        self._bot = bot
        self._roles = roles
        if not self.refresh_loop.is_running():
            self.refresh_loop.start()

    def stop(self) -> None:
        if self.refresh_loop.is_running():
            self.refresh_loop.cancel()

    async def refresh_player(self, guild: discord.Guild, discord_id: int) -> dict | None:
        player = await self.db.get_player(discord_id, guild.id)
        if not player:
            return None

        # One hiscores request per player: parse everything from the lite endpoint.
        data = await self.hiscores.fetch_player(player.rsn)
        await self.db.upsert_stats(player.discord_id, player.guild_id, player.rsn, data)

        member = guild.get_member(discord_id)
        if not member:
            try:
                member = await guild.fetch_member(discord_id)
            except discord.NotFound:
                LOGGER.info("Stats synced for %s, but the member is no longer in guild %s.", player.rsn, guild.id)
            except discord.Forbidden:
                LOGGER.warning(
                    "Stats synced for %s, but Discord would not let the bot fetch the member. "
                    "Enable the Server Members Intent in the Discord Developer Portal.",
                    player.rsn,
                )
            except discord.HTTPException:
                LOGGER.exception("Stats synced for %s, but fetching the Discord member failed.", player.rsn)

        if member and self._roles:
            try:
                await self._roles.apply_highest_progression_role(member, data)
            except discord.Forbidden:
                LOGGER.warning(
                    "Stats synced for %s, but role update failed in guild %s. "
                    "Check Manage Roles permission and role hierarchy.",
                    player.rsn,
                    guild.id,
                )
            except discord.HTTPException:
                LOGGER.exception("Stats synced for %s, but Discord role update failed.", player.rsn)
        return data

    async def refresh_guild(self, guild: discord.Guild) -> tuple[int, int]:
        async with self._lock:
            players = await self.db.list_players(guild.id)
            ok = 0
            failed = 0
            for player in players:
                try:
                    await self.refresh_player(guild, player.discord_id)
                    ok += 1
                except Exception:
                    failed += 1
                    LOGGER.exception("Failed to refresh %s in guild %s", player.rsn, guild.id)
            return ok, failed

    @tasks.loop(minutes=30)
    async def refresh_loop(self) -> None:
        if not self._bot:
            return
        for guild in self._bot.guilds:
            await self.refresh_guild(guild)

    @refresh_loop.before_loop
    async def before_refresh_loop(self) -> None:
        if self._bot:
            await self._bot.wait_until_ready()


def format_cache_age(updated_at: str | None) -> str:
    if not updated_at:
        return "not cached"
    then = datetime.fromisoformat(updated_at)
    delta = datetime.now(timezone.utc) - then
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes}m ago"
