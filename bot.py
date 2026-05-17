import os
import asyncio
import discord

from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

from db import (
    add_player,
    remove_player,
    get_players,
    log_admin,
    get_admin_logs
)

from osrs_api import get_total_level

# -------------------
# LOAD ENV
# -------------------
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# -------------------
# CONFIG
# -------------------
ADMIN_ROLE = "Clan Admin"

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

# -------------------
# BOT SETUP
# -------------------
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# -------------------
# ADMIN CHECK
# -------------------
def is_admin(member: discord.Member):
    return any(r.name == ADMIN_ROLE for r in member.roles)


# -------------------
# ROLE SYSTEM
# -------------------
async def sync_roles(member: discord.Member, level: int):

    guild = member.guild
    earned = []

    for req, role_name in ROLE_TIERS.items():

        role = discord.utils.get(guild.roles, name=role_name)

        if role and level >= req:
            earned.append(role)

    for role in member.roles:
        if role.name in ROLE_TIERS.values() and role not in earned:
            await member.remove_roles(role)

    for role in earned:
        if role not in member.roles:
            await member.add_roles(role)


# -------------------
# REGISTER PLAYER
# -------------------
@tree.command(name="register", description="Link your OSRS account")
async def register(interaction: discord.Interaction, rsn: str):

    add_player(interaction.user.id, rsn)

    await interaction.response.send_message(
        f"✅ Linked {rsn}",
        ephemeral=True
    )


# -------------------
# STATS
# -------------------
@tree.command(name="stats", description="Check OSRS total level")
async def stats(interaction: discord.Interaction, rsn: str):

    level = await get_total_level(rsn)

    if level is None:
        await interaction.response.send_message("Player not found.")
        return

    await interaction.response.send_message(
        f"🏆 {rsn} total level: {level}"
    )


# -------------------
# ADD PLAYER (ADMIN)
# -------------------
@tree.command(name="addplayer", description="Admin: add player")
async def addplayer(interaction: discord.Interaction, user: discord.Member, rsn: str):

    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    add_player(user.id, rsn)
    log_admin(interaction.user.id, "ADD_PLAYER", f"{user.id}:{rsn}")

    await interaction.response.send_message("✅ Player added", ephemeral=True)


# -------------------
# REMOVE PLAYER (ADMIN)
# -------------------
@tree.command(name="removeplayer", description="Admin: remove player")
async def removeplayer(interaction: discord.Interaction, user: discord.Member):

    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    remove_player(user.id)
    log_admin(interaction.user.id, "REMOVE_PLAYER", str(user.id))

    await interaction.response.send_message("🗑️ Player removed", ephemeral=True)


# -------------------
# ADMIN LOGS
# -------------------
@tree.command(name="adminlog", description="View admin logs")
async def adminlog(interaction: discord.Interaction):

    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    logs = get_admin_logs()

    text = "\n".join(
        f"{t} | {a} | {x}"
        for _, a, x, t in logs
    )

    await interaction.response.send_message(f"```{text}```", ephemeral=True)


# -------------------
# SYNC ALL (ADMIN)
# -------------------
@tree.command(name="sync", description="Force clan sync")
async def sync(interaction: discord.Interaction):

    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    log_admin(interaction.user.id, "SYNC_CLAN")

    await interaction.response.send_message("🔄 Syncing...")

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

    await interaction.followup.send("✅ Sync complete")


# -------------------
# AUTO SYNC LOOP
# -------------------
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


# -------------------
# READY EVENT
# -------------------
@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    await tree.sync(guild=discord.Object(id=GUILD_ID))

    if not auto_sync.is_running():
        auto_sync.start()


# -------------------
# RUN BOT
# -------------------
bot.run(TOKEN)
