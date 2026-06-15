from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import aiohttp


LOGGER = logging.getLogger(__name__)
BASE_URL = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={player}"

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

    async def __aenter__(self) -> "HiscoresClient":
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=20)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "OSRS-Discord-Bot/1.0"},
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

        url = BASE_URL.format(player=quote(rsn.strip()))
        async with self._session().get(url) as response:
            if response.status == 404:
                raise ValueError(f"No hiscores found for RSN '{rsn}'")
            response.raise_for_status()
            text = await response.text()

        await asyncio.sleep(0)  # Let command bursts yield between players.
        return self.parse_lite_response(rsn, text)

    @staticmethod
    def parse_lite_response(rsn: str, text: str) -> dict[str, Any]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
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


def resolve_boss_name(raw: str) -> str | None:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return BOSS_ALIASES.get(key) or (key if key in BOSSES else None)


def display_name(key: str) -> str:
    return key.replace("_", " ").title().replace("Tztok", "TzTok").replace("Tzkal", "TzKal")
