from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import aiohttp


LOGGER = logging.getLogger(__name__)
DEFAULT_BASE_URLS = [
    "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws",
    "https://services.runescape.com/m=hiscore_oldschool/index_lite.ws",
]

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


@dataclass(slots=True)
class HiscoresEntry:
    rank: int
    level: int | None
    xp_or_score: int


class HiscoresClient:
    """OSRS hiscores client using one shared aiohttp session."""

    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self.min_interval_seconds = float(os.getenv("HISCORES_MIN_INTERVAL_SECONDS", "5"))
        self.base_urls = _load_base_urls()

    async def __aenter__(self) -> "HiscoresClient":
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=20)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "Accept": "text/plain,*/*;q=0.8",
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; OSRS-Discord-Bot/1.0; "
                        "+https://github.com/discord.py)"
                    ),
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
        """Fetch and parse all lite hiscores in a single request."""

        clean_rsn = rsn.strip()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                text = await self._fetch_text(clean_rsn)
                return self.parse_lite_response(clean_rsn, text)
            except TemporaryHiscoresError as error:
                last_error = error
                if attempt == 2:
                    break
                await asyncio.sleep(10 * (attempt + 1))

        if last_error:
            raise last_error
        raise RuntimeError("Hiscores request failed unexpectedly")

    async def _fetch_text(self, rsn: str) -> str:
        async with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.min_interval_seconds:
                await asyncio.sleep(self.min_interval_seconds - elapsed)

            errors: list[str] = []
            for base_url in self.base_urls:
                async with self._session().get(base_url, params={"player": rsn}) as response:
                    self._last_request_at = time.monotonic()
                    if response.status == 404:
                        raise ValueError(f"No hiscores found for RSN '{rsn}'")
                    response.raise_for_status()
                    text = await response.text()

                if not _looks_like_html(text):
                    return text

                errors.append(base_url)

            raise TemporaryHiscoresError(
                "OSRS hiscores returned HTML instead of stats from every configured endpoint "
                f"({', '.join(errors)}). Railway's IP is likely being served a block/error page."
            )

    @staticmethod
    def parse_lite_response(rsn: str, text: str) -> dict[str, Any]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise ValueError(f"Empty hiscores response for RSN '{rsn}'")
        if _looks_like_html(text):
            raise TemporaryHiscoresError(
                "OSRS hiscores returned an HTML page instead of stats. "
                "This is usually a temporary Jagex block, rate limit, or hiscores outage."
            )
        if "," not in lines[0]:
            raise ValueError(f"Unexpected hiscores response for RSN '{rsn}': {lines[0][:80]}")

        data: dict[str, Any] = {"rsn": rsn, "skills": {}, "activities": {}, "bosses": {}}

        for name, line in zip(SKILLS, lines[: len(SKILLS)]):
            rank, level, xp = _parse_csv_ints(line, expected=3)
            data["skills"][name] = {"rank": rank, "level": level, "xp": xp}

        start = len(SKILLS)
        for name, line in zip(ACTIVITIES, lines[start : start + len(ACTIVITIES)]):
            rank, score = _parse_csv_ints(line, expected=2)
            data["activities"][name] = {"rank": rank, "score": score}

        start += len(ACTIVITIES)
        for name, line in zip(BOSSES, lines[start : start + len(BOSSES)]):
            rank, score = _parse_csv_ints(line, expected=2)
            data["bosses"][name] = {"rank": rank, "score": score}

        return data


def _parse_csv_ints(line: str, expected: int) -> tuple[int, ...]:
    values = tuple(int(part) for part in line.split(",")[:expected])
    if len(values) != expected:
        raise ValueError(f"Unexpected hiscores line: {line}")
    return values


class TemporaryHiscoresError(ValueError):
    """Raised when Jagex returns a temporary non-hiscores response."""


def _looks_like_html(text: str) -> bool:
    start = text.lstrip().lower()
    return start.startswith("<!doctype html") or start.startswith("<html")


def _load_base_urls() -> list[str]:
    raw = os.getenv("HISCORES_BASE_URLS", "").strip()
    if not raw:
        return DEFAULT_BASE_URLS
    return [url.strip() for url in raw.split(",") if url.strip()]


def resolve_boss_name(raw: str) -> str | None:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return BOSS_ALIASES.get(key) or (key if key in BOSSES else None)


def display_name(key: str) -> str:
    return key.replace("_", " ").title().replace("Tztok", "TzTok").replace("Tzkal", "TzKal")
