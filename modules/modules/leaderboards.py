from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord

from modules.hiscores import display_name


LeaderboardValue = Callable[[dict[str, Any]], int]


def make_leaderboard_embed(
    title: str,
    cached_rows: list[dict[str, Any]],
    value_getter: LeaderboardValue,
    value_label: str,
    limit: int = 10,
) -> discord.Embed:
    ranked = []
    for row in cached_rows:
        data = row.get("data")
        if not data:
            continue
        value = value_getter(data)
        if value > -1:
            ranked.append((row["rsn"], value, row["discord_id"]))

    ranked.sort(key=lambda item: item[1], reverse=True)
    embed = discord.Embed(title=title, color=discord.Color.green())
    if not ranked:
        embed.description = "No cached stats yet. Run `!sync` or wait for the next cache refresh."
        return embed

    lines = []
    for index, (rsn, value, discord_id) in enumerate(ranked[:limit], start=1):
        lines.append(f"**{index}. {rsn}** - {value:,} {value_label} (<@{discord_id}>)")

    embed.description = "\n".join(lines)
    return embed


def total_level(data: dict[str, Any]) -> int:
    return data.get("skills", {}).get("overall", {}).get("level", -1)


def boss_kc(boss: str) -> LeaderboardValue:
    def getter(data: dict[str, Any]) -> int:
        return data.get("bosses", {}).get(boss, {}).get("score", -1)

    return getter


def pvm_score(data: dict[str, Any]) -> int:
    return sum(max(0, boss.get("score", 0)) for boss in data.get("bosses", {}).values())


def raid_score(data: dict[str, Any]) -> int:
    bosses = data.get("bosses", {})
    raid_keys = [
        "chambers_of_xeric",
        "chambers_of_xeric_challenge_mode",
        "theatre_of_blood",
        "theatre_of_blood_hard_mode",
        "tombs_of_amascut",
        "tombs_of_amascut_expert",
    ]
    return sum(max(0, bosses.get(key, {}).get("score", 0)) for key in raid_keys)


def boss_title(boss: str) -> str:
    return f"{display_name(boss)} Leaderboard"
