import os
import asyncio
import aiohttp
import sqlite3
import discord

from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

if not TOKEN:
    raise ValueError("Missing DISCORD_TOKEN")
if not GUILD_ID:
    raise ValueError("Missing GUILD_ID")

# =========================
# OSRS API
# =========================
HISCORES_URL = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player="

# =========================
# ROLE TIERS
# =========================
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

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("clan.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    rsn TEXT NOT NULL
)
""")
conn.commit()


def add_player(discord_id, rsn):
    cursor.execute(
        "INSERT OR REPLACE INTO players (discord_id, rsn) VALUES (?, ?)",
        (discord_id, rsn),
    )
    conn.commit()


def get_players():
    cursor.execute("SELECT discord_id, rsn FROM players")
    return cursor.fetchall()


# =========================
# DISCORD BOT SETUP
# =========================
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# =========================
# OSRS FETCH
# =========================
async def get_total_level(rsn: str):

    url = HISCORES_URL + rsn.replace(" ", "%20")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:

                if r.status != 200:
                    return None

                data = await r.text()

        return int(data.splitlines()[0].split(",")[1])

    except:
        return None


# =========================
# ROLE SYNC
# =========================
async def sync_roles(member: discord.Member, level: int):

    guild = member.guild
    earned_roles = []

    for req, role_name in ROLE_TIERS.items():

        role = discord.utils.get(guild.roles, name=role_name)

        if role and level >= req:
            earned_roles.append(role)

    # remove old roles
    for role in member.roles:
        if role.name in ROLE_TIERS.values() and role not in earned_roles:
            await member.remove_roles(role)

    # add new roles
    for role in earned_roles:
        if role not in member.roles:
            await member.add_roles(role)


# =========================
# SLASH COMMANDS
# =========================

@tree.command(name="register", description="Link your OSRS account")
async def register(interaction: discord.Interaction, rsn: str):

    add_player(interaction.user.id, rsn)

    await interaction.response.send_message(
        f"✅ Linked **{rsn}** to {interaction.user.mention}",
        ephemeral=True
    )


@tree.command(name="stats", description="Check OSRS total level")
async def stats(interaction: discord.Interaction, rsn: str):

    level = await get_total_level(rsn)

    if level is None:
        await interaction.response.send_message("❌ Player not found.")
        return

    embed = discord.Embed(
        title=rsn,
        description=f"🏆 Total Level: **{level}**",
        color=discord.Color.green()
    )

    await interaction.response.send_message(embed=embed)


@tree.command(name="sync", description="Force sync clan (admin)")
async def sync(interaction: discord.Interaction):

    await interaction.response.send_message("🔄 Syncing clan...")

    guild = interaction.guild

    for discord_id, rsn in get_players():

        member = guild.get_member(discord_id)
        if not member:
            continue

        level = await get_total_level(rsn)
        if level is None:
            continue

        await sync_roles(member, level)

    await interaction.followup.send("✅ Sync complete")


# =========================
# BACKGROUND LOOP
# =========================
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

        await asyncio.sleep(2)


# =========================
# ON READY
# =========================
@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    try:
        await tree.sync(guild=discord.Object(id=GUILD_ID))
        print("Slash commands synced")
    except Exception as e:
        print(f"Command sync failed: {e}")

    if not auto_sync.is_running():
        auto_sync.start()


# =========================
# RUN BOT
# =========================
bot.run(TOKEN)
