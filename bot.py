import os
import asyncio
import aiohttp
import discord
import json

from discord.ext import commands, tasks
from dotenv import load_dotenv

# ==========================================
# LOAD ENV
# ==========================================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# DEBUGGING
print("TOKEN LOADED:", DISCORD_TOKEN is not None)
print("GUILD ID RAW:", GUILD_ID)

if DISCORD_TOKEN is None:
    raise Exception("DISCORD_TOKEN missing from .env")

if GUILD_ID is None:
    raise Exception("GUILD_ID missing from .env")

GUILD_ID = int(GUILD_ID)

# ==========================================
# CONFIG
# ==========================================

HISCORES_URL = (
    "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player="
)

ROLE_REQUIREMENTS = {
    "Topaz Member": 750,
    "Sapphire Member": 1000,
    "Emerald Member": 1500,
    "Ruby Member": 1750,
    "Diamond Member": 1900,
    "Dragonstone Member": 2100,
    "Onyx Member": 2200,
    "Zenyte Member": 2277,
}

# ==========================================
# PLAYER STORAGE
# ==========================================

DATA_FILE = "players.json"


def load_players():

    if not os.path.exists(DATA_FILE):

        with open(DATA_FILE, "w") as f:
            json.dump({}, f)

    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_players(data):

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


PLAYER_LINKS = load_players()

# ==========================================
# DISCORD SETUP
# ==========================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ==========================================
# FETCH TOTAL LEVEL
# ==========================================

async def fetch_total_level(username):

    try:

        username = username.replace(" ", "%20")

        url = f"{HISCORES_URL}{username}"

        async with aiohttp.ClientSession() as session:

            async with session.get(url) as response:

                if response.status != 200:
                    print(f"Could not fetch: {username}")
                    return None

                data = await response.text()

        lines = data.splitlines()

        if len(lines) == 0:
            return None

        overall = lines[0]

        rank, level, xp = overall.split(",")

        return int(level)

    except Exception as e:
        print("ERROR FETCHING LEVEL:", e)
        return None

# ==========================================
# UPDATE ROLES
# ==========================================

async def update_member_roles(member, total_level):

    highest_role = None
    highest_requirement = 0

    # Find highest eligible role
    for role_name, required_level in ROLE_REQUIREMENTS.items():

        role = discord.utils.get(
            member.guild.roles,
            name=role_name
        )

        if role is None:
            print(f"Missing role: {role_name}")
            continue

        if total_level >= required_level:

            if required_level > highest_requirement:

                highest_requirement = required_level
                highest_role = role

    if highest_role is None:

        print(f"{member.name} qualifies for no roles")
        return

    # Check if user already has correct role
    if highest_role in member.roles:

        print(
            f"{member.name} already has correct role "
            f"({highest_role.name})"
        )

        return

    # Remove ONLY incorrect progression roles
    for role in member.roles:

        if role.name in ROLE_REQUIREMENTS:

            if role != highest_role:

                try:

                    await member.remove_roles(role)

                    print(
                        f"Removed {role.name} "
                        f"from {member.name}"
                    )

                except Exception as e:
                    print(e)

    # Add highest role
    try:

        await member.add_roles(highest_role)

        print(
            f"{member.name} assigned "
            f"{highest_role.name}"
        )

    except Exception as e:
        print(e)

# ==========================================
# MAIN SYNC
# ==========================================

async def sync_all_members():

    guild = bot.get_guild(GUILD_ID)

    if guild is None:
        print("Guild not found.")
        print("Bot guilds:", bot.guilds)
        return

    print(f"Connected to guild: {guild.name}")

    for discord_id, rsn in PLAYER_LINKS.items():

        discord_id = int(discord_id)

        member = guild.get_member(discord_id)

        if member is None:
            print(f"Member not found: {discord_id}")
            continue

        print(f"Checking {rsn}")

        total_level = await fetch_total_level(rsn)

        if total_level is None:
            print(f"Could not fetch stats for {rsn}")
            continue

        print(f"{rsn} Total Level: {total_level}")

        await update_member_roles(member, total_level)

        await asyncio.sleep(2)

# ==========================================
# AUTO LOOP
# ==========================================

@tasks.loop(minutes=30)
async def role_sync_loop():

    await sync_all_members()

# ==========================================
# READY EVENT
# ==========================================

@bot.event
async def on_ready():

    print("=" * 50)
    print(f"Logged in as {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print("Connected Servers:")

    for guild in bot.guilds:
        print(f"- {guild.name} ({guild.id})")

    print("=" * 50)

    if not role_sync_loop.is_running():
        role_sync_loop.start()

# ==========================================
# COMMANDS
# ==========================================

@bot.command()
async def sync(ctx):

    await ctx.send("Starting OSRS sync...")

    await sync_all_members()

    await ctx.send("Sync complete.")


@bot.command()
async def stats(ctx, *, username):

    total_level = await fetch_total_level(username)

    if total_level is None:
        await ctx.send("Player not found.")
        return

    embed = discord.Embed(
        title=username,
        description=f"Total Level: {total_level}",
        color=discord.Color.green()
    )

    await ctx.send(embed=embed)


# ==========================================
# REGISTER RSN
# ==========================================

@bot.command()
async def register(ctx, *, rsn):

    PLAYER_LINKS[str(ctx.author.id)] = rsn

    save_players(PLAYER_LINKS)

    await ctx.send(
        f"{ctx.author.mention} registered RSN: {rsn}"
    )


# ==========================================
# VIEW REGISTERED RSN
# ==========================================

@bot.command()
async def myrsn(ctx):

    rsn = PLAYER_LINKS.get(str(ctx.author.id))

    if rsn is None:

        await ctx.send(
            "You have not registered an RSN yet."
        )

        return

    await ctx.send(
        f"Your registered RSN is: {rsn}"
    )


# ==========================================
# REMOVE REGISTERED RSN
# ==========================================

@bot.command()
async def unregister(ctx):

    if str(ctx.author.id) not in PLAYER_LINKS:

        await ctx.send(
            "You are not registered."
        )

        return

    del PLAYER_LINKS[str(ctx.author.id)]

    save_players(PLAYER_LINKS)

    await ctx.send(
        "Your RSN registration has been removed."
    )


# ==========================================
# SHOW ALL REGISTERED PLAYERS
# ==========================================

@bot.command()
async def registered(ctx):

    if len(PLAYER_LINKS) == 0:

        await ctx.send("No players registered.")
        return

    message = "**Registered Players**\n\n"

    for discord_id, rsn in PLAYER_LINKS.items():

        member = ctx.guild.get_member(int(discord_id))

        if member:
            message += f"{member.name} → {rsn}\n"

    await ctx.send(message)


# ==========================================
# MANUAL ADMIN PLAYER ADD
# ==========================================

@bot.command()
@commands.has_permissions(administrator=True)
async def addplayer(
    ctx,
    member: discord.Member = None,
    *,
    rsn=None
):

    # Check command usage
    if member is None or rsn is None:

        await ctx.send(
            "Usage: !addplayer @User RSN"
        )

        return

    # Save player
    PLAYER_LINKS[str(member.id)] = rsn

    save_players(PLAYER_LINKS)

    # Success message
    await ctx.send(
        f"{member.mention} registered with RSN: {rsn}"
    )


# ==========================================
# MANUAL ADMIN PLAYER REMOVE
# ==========================================

@bot.command()
@commands.has_permissions(administrator=True)
async def removeplayer(ctx, member: discord.Member = None):

    if member is None:

        await ctx.send(
            "Usage: !removeplayer @User"
        )

        return

    if str(member.id) not in PLAYER_LINKS:

        await ctx.send(
            "Player is not registered."
        )

        return

    del PLAYER_LINKS[str(member.id)]

    save_players(PLAYER_LINKS)

    await ctx.send(
        f"{member.name} removed from tracking."
    )
# ==========================================
# START BOT
# ==========================================

bot.run(DISCORD_TOKEN)
