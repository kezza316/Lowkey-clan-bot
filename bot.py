import os
import asyncio
import sqlite3
import aiohttp
import discord

from discord.ext import commands, tasks
from dotenv import load_dotenv

# ==========================================
# LOAD ENV VARIABLES
# ==========================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# ==========================================
# DISCORD INTENTS
# ==========================================
intents = discord.Intents.default()

intents.members = True
intents.message_content = True

# ==========================================
# BOT SETUP
# ==========================================
bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ==========================================
# DATABASE
# ==========================================
conn = sqlite3.connect("clan.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    rsn TEXT NOT NULL
)
""")

conn.commit()

# ==========================================
# ROLE TIERS
# ==========================================
ROLE_TIERS = {
    750: "Red Topaz Member",
    1000: "Sapphire Member",
    1500: "Emerald Member",
    1750: "Ruby Member",
    1900: "Diamond Member",
    2100: "Dragonstone Member",
    2200: "Onyx Member",
    2277: "Zenyte Member",
}

# ==========================================
# OSRS HISCORES API
# ==========================================
HISCORES_URL = (
    "https://secure.runescape.com/"
    "m=hiscore_oldschool/index_lite.ws?player="
)

# ==========================================
# DATABASE FUNCTIONS
# ==========================================
def add_player(discord_id, rsn):

    cursor.execute(
        "INSERT OR REPLACE INTO players VALUES (?, ?)",
        (discord_id, rsn)
    )

    conn.commit()


def get_players():

    cursor.execute(
        "SELECT discord_id, rsn FROM players"
    )

    return cursor.fetchall()

# ==========================================
# GET TOTAL LEVEL
# ==========================================
async def get_total_level(rsn):

    url = HISCORES_URL + rsn.replace(" ", "%20")

    try:

        async with aiohttp.ClientSession() as session:

            async with session.get(url) as response:

                if response.status != 200:
                    return None

                data = await response.text()

        first_line = data.splitlines()[0]

        rank, level, xp = first_line.split(",")

        return int(level)

    except Exception as e:

        print(f"OSRS API Error: {e}")

        return None

# ==========================================
# ROLE SYNC SYSTEM
# ==========================================
async def sync_roles(member, total_level):

    earned_roles = []

    for required_level, role_name in ROLE_TIERS.items():

        role = discord.utils.get(
            member.guild.roles,
            name=role_name
        )

        if role and total_level >= required_level:
            earned_roles.append(role)

    # Remove old roles
    for role in member.roles:

        if (
            role.name in ROLE_TIERS.values()
            and role not in earned_roles
        ):

            await member.remove_roles(role)

    # Add new roles
    for role in earned_roles:

        if role not in member.roles:

            await member.add_roles(role)

# ==========================================
# BOT READY
# ==========================================
@bot.event
async def on_ready():

    print("============================")
    print(f"✅ Logged in as {bot.user}")
    print("============================")

    if not auto_sync.is_running():
        auto_sync.start()

# ==========================================
# !register
# ==========================================
@bot.command()
async def register(ctx, *, rsn):

    add_player(ctx.author.id, rsn)

    await ctx.send(
        f"✅ Registered RSN: {rsn}"
    )

# ==========================================
# !stats
# ==========================================
@bot.command()
async def stats(ctx, *, rsn):

    level = await get_total_level(rsn)

    if level is None:

        await ctx.send(
            "❌ Player not found"
        )

        return

    embed = discord.Embed(
        title=rsn,
        description=f"🏆 Total Level: {level}",
        color=discord.Color.green()
    )

    await ctx.send(embed=embed)

# ==========================================
# !leaderboard
# ==========================================
@bot.command()
async def leaderboard(ctx):

    leaderboard_data = []

    await ctx.send("📊 Building leaderboard...")

    for discord_id, rsn in get_players():

        level = await get_total_level(rsn)

        if level is None:
            continue

        leaderboard_data.append((rsn, level))

        await asyncio.sleep(1)

    leaderboard_data.sort(
        key=lambda x: x[1],
        reverse=True
    )

    if not leaderboard_data:

        await ctx.send(
            "No registered players."
        )

        return

    description = ""

    for index, (rsn, level) in enumerate(
        leaderboard_data[:10],
        start=1
    ):

        description += (
            f"**#{index}** • "
            f"{rsn} → 🏆 {level}\n"
        )

    embed = discord.Embed(
        title="🏆 Clan Leaderboard",
        description=description,
        color=discord.Color.gold()
    )

    await ctx.send(embed=embed)

# ==========================================
# !sync
# ==========================================
@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):

    await ctx.send("🔄 Syncing clan...")

    guild = bot.get_guild(GUILD_ID)

    for discord_id, rsn in get_players():

        member = guild.get_member(discord_id)

        if not member:
            continue

        level = await get_total_level(rsn)

        if level is None:
            continue

        await sync_roles(member, level)

        await asyncio.sleep(1)

    await ctx.send(
        "✅ Clan sync complete"
    )

# ==========================================
# AUTO ROLE SYNC LOOP
# ==========================================
@tasks.loop(minutes=30)
async def auto_sync():

    guild = bot.get_guild(GUILD_ID)

    if not guild:
        return

    for discord_id, rsn in get_players():

        member = guild.get_member(discord_id)

        if not member:
            continue

        level = await get_total_level(rsn)

        if level is None:
            continue

        await sync_roles(member, level)

        await asyncio.sleep(1)

# ==========================================
# RUN BOT
# ==========================================
bot.run(TOKEN)
