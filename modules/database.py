from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Player:
    discord_id: int
    rsn: str
    guild_id: int
    created_at: str
    updated_at: str


class Database:
    """Small async SQLite wrapper.

    Players and hiscores cache are intentionally stored in separate tables so
    registration data remains stable even when a stats refresh fails.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None

    def _conn(self) -> aiosqlite.Connection:
        if not self.conn:
            raise RuntimeError("Database is not connected")
        return self.conn

    async def _fetchone(self, query: str, params: tuple[Any, ...]) -> aiosqlite.Row | None:
        cursor = await self._conn().execute(query, params)
        return await cursor.fetchone()

    async def _fetchall(self, query: str, params: tuple[Any, ...]) -> list[aiosqlite.Row]:
        cursor = await self._conn().execute(query, params)
        return await cursor.fetchall()

    async def migrate(self) -> None:
        db = self._conn()
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                discord_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                rsn TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (discord_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS stats_cache (
                discord_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                rsn TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (discord_id, guild_id),
                FOREIGN KEY (discord_id, guild_id)
                    REFERENCES players(discord_id, guild_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_players_guild
                ON players(guild_id);

            CREATE INDEX IF NOT EXISTS idx_stats_cache_guild
                ON stats_cache(guild_id);
            """
        )
        await db.commit()

    async def upsert_player(self, discord_id: int, guild_id: int, rsn: str) -> None:
        now = utc_now_iso()
        await self._conn().execute(
            """
            INSERT INTO players (discord_id, guild_id, rsn, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(discord_id, guild_id) DO UPDATE SET
                rsn = excluded.rsn,
                updated_at = excluded.updated_at
            """,
            (discord_id, guild_id, rsn.strip(), now, now),
        )
        await self._conn().commit()

    async def remove_player(self, discord_id: int, guild_id: int) -> bool:
        cursor = await self._conn().execute(
            "DELETE FROM players WHERE discord_id = ? AND guild_id = ?",
            (discord_id, guild_id),
        )
        await self._conn().commit()
        return cursor.rowcount > 0

    async def get_player(self, discord_id: int, guild_id: int) -> Player | None:
        row = await self._fetchone(
            "SELECT * FROM players WHERE discord_id = ? AND guild_id = ?",
            (discord_id, guild_id),
        )
        return Player(**dict(row)) if row else None

    async def list_players(self, guild_id: int) -> list[Player]:
        rows = await self._fetchall(
            "SELECT * FROM players WHERE guild_id = ? ORDER BY rsn COLLATE NOCASE",
            (guild_id,),
        )
        return [Player(**dict(row)) for row in rows]

    async def upsert_stats(
        self,
        discord_id: int,
        guild_id: int,
        rsn: str,
        data: dict[str, Any],
    ) -> None:
        await self._conn().execute(
            """
            INSERT INTO stats_cache (discord_id, guild_id, rsn, data, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(discord_id, guild_id) DO UPDATE SET
                rsn = excluded.rsn,
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (discord_id, guild_id, rsn, json.dumps(data), utc_now_iso()),
        )
        await self._conn().commit()

    async def get_stats(self, discord_id: int, guild_id: int) -> dict[str, Any] | None:
        row = await self._fetchone(
            "SELECT data FROM stats_cache WHERE discord_id = ? AND guild_id = ?",
            (discord_id, guild_id),
        )
        return json.loads(row["data"]) if row else None

    async def list_cached_stats(self, guild_id: int) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT players.discord_id, players.rsn, stats_cache.data, stats_cache.updated_at
            FROM players
            LEFT JOIN stats_cache
                ON players.discord_id = stats_cache.discord_id
                AND players.guild_id = stats_cache.guild_id
            WHERE players.guild_id = ?
            ORDER BY players.rsn COLLATE NOCASE
            """,
            (guild_id,),
        )
        output: list[dict[str, Any]] = []
        for row in rows:
            data = json.loads(row["data"]) if row["data"] else None
            output.append(
                {
                    "discord_id": row["discord_id"],
                    "rsn": row["rsn"],
                    "data": data,
                    "updated_at": row["updated_at"],
                }
            )
        return output
