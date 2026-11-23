"""Anti-raid : lockdown, sanctions et détection de création massive."""

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

# ============================ ANTI-RAID ============================
async def start_lockdown(guild):
    """Retire la permission d'écrire à @everyone dans tous les salons texte.
    Les permissions d'origine sont sauvegardées pour être restaurées ensuite."""
    gid = str(guild.id)
    if gid in data["lockdown"]:
        return
    everyone = guild.default_role
    saved = {}
    for channel in guild.text_channels:
        current = channel.overwrites_for(everyone)
        allow, deny = current.pair()
        saved[str(channel.id)] = None if current.is_empty() else [allow.value, deny.value]
        new = discord.PermissionOverwrite.from_pair(allow, deny)
        new.send_messages = False
        try:
            await channel.set_permissions(everyone, overwrite=new, reason="Anti-raid : lockdown")
        except discord.HTTPException:
            pass
    data["lockdown"][gid] = saved
    save_data()
    run_bg(auto_end_lockdown(guild.id))


async def end_raid(guild, reason):
    """Restaure les permissions d'origine des salons (« ça remet tout »)."""
    raid_mode.discard(guild.id)
    saved = data["lockdown"].pop(str(guild.id), None)
    if saved is None:
        return
    for channel_id, perms in saved.items():
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            continue
        overwrite = None
        if perms is not None:
            overwrite = discord.PermissionOverwrite.from_pair(
                discord.Permissions(perms[0]), discord.Permissions(perms[1])
            )
        try:
            await channel.set_permissions(
                guild.default_role, overwrite=overwrite, reason="Anti-raid : permissions restaurées"
            )
        except discord.HTTPException:
            pass
    save_data()
    await send_log(guild, "sanctions",
                   make_embed("✅ Anti-raid : permissions restaurées", reason, discord.Color.green()))


async def auto_end_lockdown(guild_id):
    await asyncio.sleep(LOCKDOWN_DURATION)
    guild = bot.get_guild(guild_id)
    if guild and str(guild_id) in data["lockdown"]:
        await end_raid(guild, "Fin automatique du lockdown")


async def punish(guild, user_id, reason):
    """Retire les rôles (si le membre est encore là) puis bannit."""
    member = guild.get_member(user_id)
    if member:
        try:
            await member.edit(roles=[], reason=reason)
        except discord.HTTPException:
            pass
    try:
        await guild.ban(discord.Object(id=user_id), reason=reason)
    except discord.HTTPException:
        pass


async def handle_raid(guild, user_ids, motif):
    if guild.id not in raid_mode:
        raid_mode.add(guild.id)
        await start_lockdown(guild)
        await send_log(guild, "sanctions", make_embed(
            "🚨 Anti-raid déclenché",
            f"**Motif :** {motif}\nSalons verrouillés pendant {LOCKDOWN_DURATION // 60} min.",
            discord.Color.red(),
        ))
    for uid in user_ids:
        await punish(guild, uid, f"Anti-raid : {motif}")


async def check_creation_raid(guild, action):
    """Détecte une personne qui crée trop de salons/rôles d'un coup,
    supprime ce qu'elle a créé pendant la fenêtre et la bannit."""
    if not is_on("antiraid", guild):
        return
    since = discord.utils.utcnow() - datetime.timedelta(seconds=RAID_WINDOW)
    by_user = defaultdict(list)
    try:
        async for entry in guild.audit_logs(action=action, after=since, limit=50):
            if entry.user and not entry.user.bot:
                by_user[entry.user.id].append(entry)
    except discord.HTTPException:
        return

    for uid, entries in by_user.items():
        if len(entries) < RAID_CREATE_LIMIT or uid == guild.owner_id:
            continue
        member = guild.get_member(uid)
        if member and member.guild_permissions.administrator:
            continue  # on ne touche pas aux administrateurs (mise en place du serveur)
        for entry in entries:
            try:
                if action == discord.AuditLogAction.channel_create:
                    obj = guild.get_channel(entry.target.id)
                else:
                    obj = guild.get_role(entry.target.id)
                if obj:
                    await obj.delete(reason="Anti-raid : création massive")
            except discord.HTTPException:
                pass
        await handle_raid(guild, [uid], f"création massive de salons/rôles par <@{uid}>")


