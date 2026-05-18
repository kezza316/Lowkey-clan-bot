import os
import asyncio
import sqlite3
import aiohttp
import discord

from discord.ext import commands, tasks
from dotenv import load_dotenv

# ==================================================
# LOAD ENV VARIABLES
# ==================================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# ==================================================
# DISCORD INTENTS
# ==================================================
intents = discord.Intents.default()

intents.members = True
intents.message_content = True

# ==================================================
# BOT SETUP
# ==================================================
bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ==================================================
# DATABASE
# ==================================================
conn = sqlite3.connect("clan.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    discord_id INTEGER PRIMARY KEY,
    rsn TEXT NOT NULL
)
""")

conn.commit()

# ==================================================
# ROLE TIERS
# ==================================================
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

# ==================================================
# OSRS HISCORES API
# ==================================================
HISCORES_URL = (
    "https://secure.runescape.com/"
    "m=hiscore_oldschool/index_lite.ws?player="
)

# ==================================================
# DATABASE FUNCTIONS
# ==================================================
def add_player(discord_id, rsn):

    cursor.execute(
        "INSERT OR REPLACE INTO players VALUES (?, ?)",
        (discord_id, rsn)
    )

    conn.commit()


def remove_player(discord_id):

    cursor.execute(
        "DELETE FROM players WHERE discord_id = ?",
        (discord_id,)
    )

    conn.commit()


def get_players():

    cursor.execute(
        "SELECT discord_id, rsn FROM players"
    )

    return cursor.fetchall()


def get_player(discord_id):

    cursor.execute(
        "SELECT rsn FROM players WHERE discord_id = ?",
        (discord_id,)
    )

    return cursor.fetchone()

# ==================================================
# GET TOTAL LEVEL
# ==================================================
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

# ==================================================
# ROLE SYNC SYSTEM
# Highest role only
# ==================================================
async def sync_roles(member, total_level):

    highest_role = None
    highest_requirement = 0

    # Find highest role earned
    for required_level, role_name in ROLE_TIERS.items():

        if total_level >= required_level:

            if required_level > highest_requirement:

                highest_requirement = required_level

                highest_role = discord.utils.get(
                    member.guild.roles,
                    name=role_name
                )

    # Remove ALL progression roles
    for role in member.roles:

        if role.name in ROLE_TIERS.values():

            await member.remove_roles(role)

    # Add highest role only
    if highest_role:

        await member.add_roles(highest_role)

        print(
            f"Assigned {highest_role.name} "
            f"to {member.name}"
        )

# ==================================================
# BOT READY
# ==================================================
@bot.event
async def on_ready():

    print("============================")
    print(f"✅ Logged in as {bot.user}")
    print("============================")

    if not auto_sync.is_running():
        auto_sync.start()

# ==================================================
# USER COMMANDS
# ==================================================

# --------------------------------
# !register
# --------------------------------
@bot.command()
async def register(ctx, *, rsn):

    add_player(ctx.author.id, rsn)

    await ctx.send(
        f"✅ Registered RSN: {rsn}"
    )

# --------------------------------
# !stats
# --------------------------------
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

# --------------------------------
# !leaderboard
# --------------------------------
@bot.command()
async def leaderboard(ctx):

    leaderboard_data = []

    await ctx.send(
        "📊 Building leaderboard..."
    )

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

# ==================================================
# ADMIN COMMANDS
# ==================================================

# --------------------------------
# !forceadd
# --------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def forceadd(ctx, member: discord.Member, *, rsn):

    add_player(member.id, rsn)

    level = await get_total_level(rsn)

    if level is None:

        await ctx.send(
            "❌ Could not find OSRS account."
        )

        return

    await sync_roles(member, level)

    await ctx.send(
        f"✅ Added {member.mention}\n"
        f"RSN: **{rsn}**\n"
        f"🏆 Total Level: {level}"
    )

# --------------------------------
# !forceremove
# --------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def forceremove(ctx, member: discord.Member):

    remove_player(member.id)

    await ctx.send(
        f"✅ Removed {member.mention} "
        f"from tracking."
    )

# --------------------------------
# !setrsn
# --------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def setrsn(ctx, member: discord.Member, *, rsn):

    add_player(member.id, rsn)

    await ctx.send(
        f"✅ Updated {member.mention}\n"
        f"New RSN: **{rsn}**"
    )

# --------------------------------
# !forcesync
# --------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def forcesync(ctx, member: discord.Member):

    player = get_player(member.id)

    if not player:

        await ctx.send(
            "❌ Member is not registered."
        )

        return

    rsn = player[0]

    level = await get_total_level(rsn)

    if level is None:

        await ctx.send(
            "❌ Could not fetch OSRS stats."
        )

        return

    await sync_roles(member, level)

    await ctx.send(
        f"✅ Synced {member.mention}\n"
        f"🏆 Total Level: {level}"
    )

# --------------------------------
# !tracked
# --------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def tracked(ctx):

    players = get_players()

    if not players:

        await ctx.send(
            "No tracked players."
        )

        return

    description = ""

    for discord_id, rsn in players:

        member = ctx.guild.get_member(discord_id)

        if member:

            description += (
                f"{member.mention} → "
                f"**{rsn}**\n"
            )

    embed = discord.Embed(
        title="📋 Tracked Players",
        description=description,
        color=discord.Color.blue()
    )

    await ctx.send(embed=embed)

# --------------------------------
# !sync
# --------------------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):

    await ctx.send(
        "🔄 Starting full clan sync..."
    )

    guild = bot.get_guild(GUILD_ID)

    if not guild:

        await ctx.send(
            "❌ Guild not found."
        )

        return

    players = get_players()

    if not players:

        await ctx.send(
            "❌ No registered players."
        )

        return

    synced_count = 0
    failed_count = 0

    for discord_id, rsn in players:

        member = guild.get_member(discord_id)

        if not member:

            failed_count += 1
            continue

        level = await get_total_level(rsn)

        if level is None:

            failed_count += 1
            continue

        try:

            await sync_roles(member, level)

            synced_count += 1

            print(
                f"Synced {member.name} "
                f"({rsn}) -> {level}"
            )

        except Exception as e:

            print(f"Sync Error: {e}")

            failed_count += 1

        await asyncio.sleep(1)

    embed = discord.Embed(
        title="✅ Clan Sync Complete",
        color=discord.Color.green()
    )

    embed.add_field(
        name="Successful Syncs",
        value=synced_count,
        inline=True
    )

    embed.add_field(
        name="Failed",
        value=failed_count,
        inline=True
    )

    embed.add_field(
        name="Total Players",
        value=len(players),
        inline=True
    )

    await ctx.send(embed=embed)

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
# ERROR HANDLER
# ==================================================
@bot.event
async def on_command_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ You do not have permission "
            "to use this command."
        )

# ==================================================
# RUN BOT
# ==================================================
bot.run(TOKEN)
