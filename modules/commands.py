from __future__ import annotations

import discord
from discord.ext import commands

from modules.cache import StatsCache
from modules.database import Database
from modules.hiscores import display_name, resolve_boss_name
from modules.leaderboards import (
    boss_kc,
    boss_title,
    make_leaderboard_embed,
    pvm_score,
    raid_score,
    total_level,
)
from modules.roles import RoleManager


class OSRSCommands(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        db: Database,
        cache: StatsCache,
        roles: RoleManager,
    ) -> None:
        self.bot = bot
        self.db = db
        self.cache = cache
        self.roles = roles

    @commands.command(name="register")
    @commands.guild_only()
    async def register(self, ctx: commands.Context, *, rsn: str) -> None:
        await self.db.upsert_player(ctx.author.id, ctx.guild.id, rsn)
        data = await self.cache.refresh_player(ctx.guild, ctx.author.id)
        embed = discord.Embed(title="Registered", color=discord.Color.green())
        embed.description = f"Linked <@{ctx.author.id}> to **{rsn.strip()}**."
        if data:
            total = data["skills"]["overall"]["level"]
            embed.add_field(name="Total Level", value=f"{total:,}")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="stats")
    @commands.guild_only()
    async def stats(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        player = await self.db.get_player(member.id, ctx.guild.id)
        if not player:
            await ctx.reply(embed=_error_embed("That member is not registered."), mention_author=False)
            return

        data = await self.db.get_stats(member.id, ctx.guild.id)
        if not data:
            data = await self.cache.refresh_player(ctx.guild, member.id)
        if not data:
            await ctx.reply(embed=_error_embed("No stats are cached for that member yet."), mention_author=False)
            return

        skills = data["skills"]
        embed = discord.Embed(title=f"{player.rsn} Stats", color=discord.Color.blue())
        embed.add_field(name="Total Level", value=f"{skills['overall']['level']:,}")
        embed.add_field(name="Total XP", value=f"{skills['overall']['xp']:,}")
        embed.add_field(name="Combat Core", value=_combat_summary(skills), inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="leaderboard", aliases=["lb"])
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context) -> None:
        rows = await self.db.list_cached_stats(ctx.guild.id)
        embed = make_leaderboard_embed("Total Level Leaderboard", rows, total_level, "total level")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="pvmlb")
    @commands.guild_only()
    async def pvmlb(self, ctx: commands.Context) -> None:
        rows = await self.db.list_cached_stats(ctx.guild.id)
        embed = make_leaderboard_embed("PvM Leaderboard", rows, pvm_score, "boss KC")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="raidlb")
    @commands.guild_only()
    async def raidlb(self, ctx: commands.Context) -> None:
        rows = await self.db.list_cached_stats(ctx.guild.id)
        embed = make_leaderboard_embed("Raid Leaderboard", rows, raid_score, "raid KC")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="bosslb")
    @commands.guild_only()
    async def bosslb(self, ctx: commands.Context, *, boss: str) -> None:
        boss_key = resolve_boss_name(boss)
        if not boss_key:
            await ctx.reply(embed=_error_embed(f"Unknown boss alias: `{boss}`"), mention_author=False)
            return

        rows = await self.db.list_cached_stats(ctx.guild.id)
        embed = make_leaderboard_embed(boss_title(boss_key), rows, boss_kc(boss_key), "KC")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="forceadd")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def forceadd(self, ctx: commands.Context, member: discord.Member, *, rsn: str) -> None:
        await self.db.upsert_player(member.id, ctx.guild.id, rsn)
        await self.cache.refresh_player(ctx.guild, member.id)
        await ctx.reply(
            embed=_ok_embed("Player Added", f"Linked {member.mention} to **{rsn.strip()}**."),
            mention_author=False,
        )

    @commands.command(name="forceremove")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def forceremove(self, ctx: commands.Context, member: discord.Member) -> None:
        removed = await self.db.remove_player(member.id, ctx.guild.id)
        message = f"Removed {member.mention}." if removed else f"{member.mention} was not registered."
        await ctx.reply(embed=_ok_embed("Player Removed", message), mention_author=False)

    @commands.command(name="setrsn")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setrsn(self, ctx: commands.Context, member: discord.Member, *, rsn: str) -> None:
        await self.db.upsert_player(member.id, ctx.guild.id, rsn)
        await self.cache.refresh_player(ctx.guild, member.id)
        await ctx.reply(
            embed=_ok_embed("RSN Updated", f"Set {member.mention}'s RSN to **{rsn.strip()}**."),
            mention_author=False,
        )

    @commands.command(name="tracked")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def tracked(self, ctx: commands.Context) -> None:
        players = await self.db.list_players(ctx.guild.id)
        embed = discord.Embed(title="Tracked Players", color=discord.Color.blurple())
        embed.description = "\n".join(f"<@{p.discord_id}> - **{p.rsn}**" for p in players) or "No players tracked."
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="forcesync")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def forcesync(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        if member:
            await self.cache.refresh_player(ctx.guild, member.id)
            await ctx.reply(embed=_ok_embed("Sync Complete", f"Synced {member.mention}."), mention_author=False)
            return

        ok, failed = await self.cache.refresh_guild(ctx.guild)
        await ctx.reply(embed=_ok_embed("Sync Complete", f"Updated {ok} players. Failed: {failed}."), mention_author=False)

    @commands.command(name="sync")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def sync(self, ctx: commands.Context) -> None:
        ok, failed = await self.cache.refresh_guild(ctx.guild)
        await ctx.reply(embed=_ok_embed("Sync Complete", f"Updated {ok} players. Failed: {failed}."), mention_author=False)

    @register.error
    @bosslb.error
    async def user_input_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(embed=_error_embed(f"Missing argument: `{error.param.name}`"), mention_author=False)
        else:
            raise error

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(embed=_error_embed("You need Manage Server permission for that command."), mention_author=False)
            return
        if isinstance(error, commands.BadArgument):
            await ctx.reply(embed=_error_embed("I could not understand that argument."), mention_author=False)
            return
        raise error


def _combat_summary(skills: dict) -> str:
    names = ["attack", "strength", "defence", "ranged", "magic", "prayer", "hitpoints"]
    return " | ".join(f"{display_name(name)} {skills[name]['level']}" for name in names)


def _error_embed(message: str) -> discord.Embed:
    embed = discord.Embed(title="Error", description=message, color=discord.Color.red())
    return embed


def _ok_embed(title: str, message: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=message, color=discord.Color.green())
    return embed
