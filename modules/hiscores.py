from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import aiohttp


LOGGER = logging.getLogger(__name__)
WISE_OLD_MAN_BASE_URL = "https://api.wiseoldman.net/v2"

SKILLS = [
    "overall",
    "attack",
    "defence",
    "strength",
    "hitpoints",
    "ranged",
    "prayer",
    "magic",
    "cooking",
    "woodcutting",
    "fletching",
    "fishing",
    "firemaking",
    "crafting",
    "smithing",
    "mining",
    "herblore",
    "agility",
    "thieving",
    "slayer",
    "farming",
    "runecraft",
    "hunter",
    "construction",
]

ACTIVITIES = [
    "league_points",
    "deadman_points",
    "bounty_hunter_hunter",
    "bounty_hunter_rogue",
    "bounty_hunter_hunter_legacy",
    "bounty_hunter_rogue_legacy",
    "clue_all",
    "clue_beginner",
    "clue_easy",
    "clue_medium",
    "clue_hard",
    "clue_elite",
    "clue_master",
    "last_man_standing",
    "pvp_arena",
    "soul_wars_zeal",
    "rifts_closed",
    "colosseum_glory",
    "collections_logged",
]

BOSSES = [
    "abyssal_sire",
    "alchemical_hydra",
    "amoxliatl",
    "araxxor",
    "artio",
    "barrows_chests",
    "bryophyta",
    "callisto",
    "calvarion",
    "cerberus",
    "chambers_of_xeric",
    "chambers_of_xeric_challenge_mode",
    "chaos_elemental",
    "chaos_fanatic",
    "commander_zilyana",
    "corporeal_beast",
    "crazy_archaeologist",
    "dagannoth_prime",
    "dagannoth_rex",
    "dagannoth_supreme",
    "deranged_archaeologist",
    "duke_sucellus",
    "general_graardor",
    "giant_mole",
    "grotesque_guardians",
    "hespori",
    "kalphite_queen",
    "king_black_dragon",
    "kraken",
    "kreearra",
    "kril_tsutsaroth",
    "lunar_chests",
    "mimic",
    "nex",
    "nightmare",
    "phosanis_nightmare",
    "obor",
    "phantom_muspah",
    "sarachnis",
    "scorpia",
    "scurrius",
    "skotizo",
    "sol_heredit",
    "spindel",
    "tempoross",
    "the_gauntlet",
    "the_corrupted_gauntlet",
    "the_hueycoatl",
    "the_leviathan",
    "the_royal_titans",
    "the_whisperer",
    "theatre_of_blood",
    "theatre_of_blood_hard_mode",
    "thermonuclear_smoke_devil",
    "tombs_of_amascut",
    "tombs_of_amascut_expert",
    "tzkal_zuk",
    "tztok_jad",
    "vardorvis",
    "venenatis",
    "vetion",
    "vorkath",
    "wintertodt",
    "zalcano",
    "zulrah",
]

BOSS_ALIASES = {
    "cox": "chambers_of_xeric",
    "cm": "chambers_of_xeric_challenge_mode",
    "tob": "theatre_of_blood",
    "hmt": "theatre_of_blood_hard_mode",
    "toa": "tombs_of_amascut",
    "toaexpert": "tombs_of_amascut_expert",
    "vork": "vorkath",
    "muspah": "phantom_muspah",
    "cg": "the_corrupted_gauntlet",
    "gauntlet": "the_gauntlet",
    "lev": "the_leviathan",
    "kbd": "king_black_dragon",
    "kq": "kalphite_queen",
    "bandos": "general_graardor",
    "arma": "kreearra",
    "zammy": "kril_tsutsaroth",
    "sara": "commander_zilyana",
}

WOM_SKILL_KEYS = {
    "runecraft": "runecrafting",
}

WOM_ACTIVITY_KEYS = {
    "clue_all": "clue_scrolls_all",
    "clue_beginner": "clue_scrolls_beginner",
    "clue_easy": "clue_scrolls_easy",
    "clue_medium": "clue_scrolls_medium",
    "clue_hard": "clue_scrolls_hard",
    "clue_elite": "clue_scrolls_elite",
    "clue_master": "clue_scrolls_master",
    "rifts_closed": "guardians_of_the_rift",
}

WOM_BOSS_KEYS = {
    "the_corrupted_gauntlet": "corrupted_gauntlet",
}


class HiscoresClient:
    """Wise Old Man client using one shared aiohttp session.

    The rest of the bot expects a Jagex-hiscores-like dictionary. This class
    asks Wise Old Man to track/update a player, then normalizes the latest
    snapshot into the bot's existing skills/activities/bosses shape.
    """

    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self.min_interval_seconds = float(os.getenv("WOM_MIN_INTERVAL_SECONDS", "2"))
        self.base_url = os.getenv("WOM_BASE_URL", WISE_OLD_MAN_BASE_URL).rstrip("/")

    async def __aenter__(self) -> "HiscoresClient":
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "OSRS-Discord-Bot/1.0 using WiseOldMan API",
                },
            )
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    def _session(self) -> aiohttp.ClientSession:
        if not self.session:
            raise RuntimeError("HiscoresClient session is not open")
        return self.session

    async def fetch_player(self, rsn: str) -> dict[str, Any]:
        clean_rsn = rsn.strip()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                payload = await self._track_player(clean_rsn)
                return self.parse_wom_player(clean_rsn, payload)
            except TemporaryHiscoresError as error:
                last_error = error
                if attempt == 2:
                    break
                await asyncio.sleep(5 * (attempt + 1))

        if last_error:
            raise last_error
        raise RuntimeError("Wise Old Man request failed unexpectedly")

    async def _track_player(self, rsn: str) -> dict[str, Any]:
        async with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.min_interval_seconds:
                await asyncio.sleep(self.min_interval_seconds - elapsed)

            url = f"{self.base_url}/players/track"
            async with self._session().post(url, json={"username": rsn}) as response:
                self._last_request_at = time.monotonic()
                if response.status == 404:
                    raise ValueError(f"No Wise Old Man player found for RSN '{rsn}'")
                if response.status == 429:
                    raise TemporaryHiscoresError("Wise Old Man rate limited the bot. Try again shortly.")
                if response.status >= 500:
                    raise TemporaryHiscoresError(f"Wise Old Man returned HTTP {response.status}. Try again shortly.")
                if response.status >= 400:
                    details = await response.text()
                    raise ValueError(f"Wise Old Man rejected RSN '{rsn}': {details[:200]}")
                return await response.json()

    @staticmethod
    def parse_wom_player(rsn: str, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = payload.get("latestSnapshot") or payload.get("latest_snapshot")
        if not snapshot and payload.get("data"):
            snapshot = payload
        if not snapshot or "data" not in snapshot:
            raise ValueError(f"Wise Old Man response did not include latest stats for RSN '{rsn}'")

        snapshot_data = snapshot["data"]
        wom_skills = snapshot_data.get("skills", {})
        wom_activities = snapshot_data.get("activities", {})
        wom_bosses = snapshot_data.get("bosses", {})
        data: dict[str, Any] = {
            "rsn": payload.get("displayName") or payload.get("username") or rsn,
            "skills": {},
            "activities": {},
            "bosses": {},
        }

        for name in SKILLS:
            metric = wom_skills.get(WOM_SKILL_KEYS.get(name, name), {})
            data["skills"][name] = {
                "rank": _int_value(metric.get("rank"), -1),
                "level": _int_value(metric.get("level"), 1 if name != "overall" else 0),
                "xp": _int_value(metric.get("experience"), 0),
            }

        for name in ACTIVITIES:
            metric = wom_activities.get(WOM_ACTIVITY_KEYS.get(name, name), {})
            data["activities"][name] = {
                "rank": _int_value(metric.get("rank"), -1),
                "score": _int_value(metric.get("score"), -1),
            }

        for name in BOSSES:
            metric = wom_bosses.get(WOM_BOSS_KEYS.get(name, name), {})
            data["bosses"][name] = {
                "rank": _int_value(metric.get("rank"), -1),
                "score": _int_value(metric.get("kills", metric.get("score")), -1),
            }

        return data


class TemporaryHiscoresError(ValueError):
    """Raised when Wise Old Man returns a temporary response."""


def _int_value(value: Any, default: int) -> int:
    if value is None:
        return default
    return int(value)


def resolve_boss_name(raw: str) -> str | None:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return BOSS_ALIASES.get(key) or (key if key in BOSSES else None)


def display_name(key: str) -> str:
    return key.replace("_", " ").title().replace("Tztok", "TzTok").replace("Tzkal", "TzKal")
