import os
import asyncio
import sqlite3
import aiohttp
import discord

from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# ==============================
# LOAD ENV
# ==============================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# ==============================
# BOT SETUP
# ==============================
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

tree = bot.tree

# ==============================
# DATABASE
# ==============================
conn = sqlite3.connect("clan.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    rsn TEXT NOT NULL
)
""")

conn.commit()

# ==============================
# ROLE TIERS
# ==============================
ROLE_TIERS = {
    1000: "Sapphire Member",
    1500: "Emerald Member",
    1750: "Ruby Member",
    1900: "Diamond Member",
    2100: "Dragonstone Member",
    2200: "Onyx Member",
    2277: "Zenyte Member",
}

# ==============================
# OSRS API
# ==============================
HISCORES_URL = (
    "https://secure.runescape.com/"
    "m=hiscore_oldschool/index_lite.ws?player="
)

# ==============================
# DATABASE FUNCTIONS
# ==============================
def add_player(discord_id, rsn):

    cursor.execute(
        "INSERT OR REPLACE INTO players VALUES (?, ?)",
        (discord_id, rsn)
    )

    conn.commit()


def get_players():

    cursor.execute("SELECT discord_id, rsn FROM players")

    return cursor.fetchall()

# ==============================
# GET TOTAL LEVEL
# ==============================
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

    except:
        return None
# ==================================================
# ROLE SYNC SYSTEM
# ==================================================
async def sync_roles(member, total_level):

    earned_roles = []

    for required_level, role_name in ROLE_TIERS.items():

        role = discord.utils.get(
            member.guild.roles,
            name=role_name
        )

        if role and total_level >= required_level:
            earned_roles.append(role)

    # Remove old progression roles
    for role in member.roles:

        if (
            role.name in ROLE_TIERS.values()
            and role not in earned_roles
        ):

            await member.remove_roles(role)

    # Add earned roles
    for role in earned_roles:

        if role not in member.roles:

            await member.add_roles(role)

# ==================================================
# /register
# ==================================================
@tree.command(
    name="register",
    description="Register your OSRS account"
)
@app_commands.describe(
    rsn="Your Old School RuneScape username"
)
async def register(
    interaction: discord.Interaction,
    rsn: str
):

    add_player(interaction.user.id, rsn)

    await interaction.response.send_message(
        f"✅ Registered RSN: {rsn}",
        ephemeral=True
    )

# ==================================================
# /stats
# ==================================================
@tree.command(
    name="stats",
    description="Check OSRS total level"
)
@app_commands.describe(
    rsn="OSRS username"
)
async def stats(
    interaction: discord.Interaction,
    rsn: str
):

    await interaction.response.defer()

    level = await get_total_level(rsn)

    if level is None:

        await interaction.followup.send(
            "❌ Player not found"
        )

        return

    embed = discord.Embed(
        title=f"{rsn}",
        description=f"🏆 Total Level: {level}",
        color=discord.Color.green()
    )

    await interaction.followup.send(embed=embed)

# ==================================================
# /leaderboard
# ==================================================
@tree.command(
    name="leaderboard",
    description="View clan leaderboard"
)
async def leaderboard(
    interaction: discord.Interaction
):

    await interaction.response.defer()

    leaderboard_data = []

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

        await interaction.followup.send(
            "No players found."
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

    await interaction.followup.send(embed=embed)

# ==================================================
# /sync
# ==================================================
@tree.command(
    name="sync",
    description="Admin: Sync all player roles"
)
async def sync(
    interaction: discord.Interaction
):

    # Discord admins only
    if not interaction.user.guild_permissions.administrator:

        await interaction.response.send_message(
            "❌ Admin only",
            ephemeral=True
        )

        return

    await interaction.response.send_message(
        "🔄 Syncing clan..."
    )

    guild = interaction.guild

    for discord_id, rsn in get_players():

        member = guild.get_member(discord_id)

        if not member:
            continue

        level = await get_total_level(rsn)

        if level is None:
            continue

        await sync_roles(member, level)

        await asyncio.sleep(1)

    await interaction.followup.send(
        "✅ Clan sync complete"
    )

# ==================================================
# AUTO SYNC LOOP
# ==================================================
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

# ==================================================
# BOT READY EVENT
# ==================================================
@bot.event
async def on_ready():

    print(f"✅ Logged in as {bot.user}")

    try:

        guild = discord.Object(id=GUILD_ID)

        # Clears old cached commands
        bot.tree.clear_commands(guild=guild)

        # Sync slash commands
        synced = await bot.tree.sync(
            guild=guild
        )

        print(
            f"✅ Synced {len(synced)} slash command(s)"
        )

    except Exception as e:

        print(f"❌ Slash sync failed: {e}")

    # Start auto sync loop
    if not auto_sync.is_running():
        auto_sync.start()

# ==================================================
# RUN BOT
# ==================================================
bot.run(TOKEN)
# ==============================
bot.run(TOKEN)
