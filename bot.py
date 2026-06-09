import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from modules.cache import StatsCache
from modules.commands import OSRSCommands
from modules.database import Database
from modules.hiscores import HiscoresClient
from modules.roles import RoleManager


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def main() -> None:
    load_dotenv()
    logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    bot = commands.Bot(
        command_prefix=os.getenv("COMMAND_PREFIX", "!"),
        intents=intents,
        help_command=None,
    )

    db = Database(os.getenv("DATABASE_PATH", "osrs_bot.sqlite3"))
    await db.connect()
    await db.migrate()

    hiscores = HiscoresClient()
    cache = StatsCache(db, hiscores, interval_minutes=30)
    roles = RoleManager(db)

    bot.db = db  # type: ignore[attr-defined]
    bot.hiscores = hiscores  # type: ignore[attr-defined]
    bot.stats_cache = cache  # type: ignore[attr-defined]
    bot.role_manager = roles  # type: ignore[attr-defined]

    @bot.event
    async def on_ready() -> None:
        assert bot.user is not None
        logging.info("Logged in as %s (%s)", bot.user, bot.user.id)
        cache.start(bot, roles)

    async with hiscores:
        await bot.add_cog(OSRSCommands(bot, db, cache, roles))
        try:
            await bot.start(required_env("DISCORD_TOKEN"))
        finally:
            cache.stop()
            await bot.close()
            await db.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
