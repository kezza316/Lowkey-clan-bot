import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from db import add_player, get_players, update_level
from osrs_api import get_total_level

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

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

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# -----------------------------
# REGISTER PLAYER
# -----------------------------
@bot.command()
async def register(ctx, rsn: str):
    add_player(ctx.author.id, rsn)
    await ctx.send(f"Linked {ctx.author.mention} to RSN: {rsn}")


# -----------------------------
# ROLE SYNC
# -----------------------------
async def sync_player(member, rsn, level):
    guild = member.guild

    earned = []

    for req, role_name in ROLE_TIERS.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if role and level >= req:
            earned.append(role)

    # remove old tiers
    for role in member.roles:
        if role.name in ROLE_TIERS.values() and role not in earned:
            await member.remove_roles(role)

    # add new tiers
    for role in earned:
        if role not in member.roles:
            await member.add_roles(role)


# -----------------------------
# LOOP
# -----------------------------
@tasks.loop(minutes=30)
async def update_loop():
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

        update_level(discord_id, level)
        await sync_player(member, rsn, level)


# -----------------------------
# MANUAL SYNC
# -----------------------------
@bot.command()
async def sync(ctx):
    await ctx.send("Syncing clan...")

    guild = ctx.guild

    for discord_id, rsn in get_players():
        member = guild.get_member(discord_id)
        if not member:
            continue

        level = await get_total_level(rsn)
        if level:
            await sync_player(member, rsn, level)

    await ctx.send("Done.")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_loop.start()


bot.run(TOKEN)
