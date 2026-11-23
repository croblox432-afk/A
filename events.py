"""Événements Discord et gestion des erreurs de commandes."""

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
from raid import *
from welcome import *
from tickets import *
from moderation import *

_ready_done = False


@bot.event
async def on_ready():
    global _ready_done
    print(f"Connecté en tant que {bot.user}")
    # Statut du bot : « Streaming » avec le lien Twitch
    await bot.change_presence(activity=discord.Streaming(name=TWITCH_STATUS, url=TWITCH_URL))
    if not _ready_done:
        _ready_done = True
        # Si le bot a redémarré pendant un lockdown, on lève le lockdown
        for gid in list(data["lockdown"].keys()):
            guild = bot.get_guild(int(gid))
            if guild:
                await end_raid(guild, "Redémarrage du bot : lockdown levé")


@bot.event
async def on_member_join(member):
    guild = member.guild

    if member.id in data["blacklist"]:
        await punish(guild, member.id, "Blacklist globale")
        return

    if is_on("antiraid", guild):
        now = time.monotonic()
        q = join_log[guild.id]
        q.append((now, member.id))
        while q and now - q[0][0] > RAID_WINDOW:
            q.popleft()
        if guild.id in raid_mode:
            await punish(guild, member.id, "Anti-raid : lockdown actif")
            return
        if len(q) >= RAID_JOIN_LIMIT:
            await handle_raid(guild, [uid for _, uid in q], f"{len(q)} arrivées en {RAID_WINDOW} s")
            return

    await give_join_role(member)
    await send_welcome(member)
    await send_log(guild, "join", make_embed("📥 Arrivée", f"{member.mention} ({member}) a rejoint le serveur.",
                                             discord.Color.green()))


@bot.event
async def on_member_remove(member):
    await send_log(member.guild, "join",
                   make_embed("📤 Départ", f"{member} a quitté le serveur.", discord.Color.orange()))


@bot.event
async def on_member_ban(guild, user):
    await send_log(guild, "sanctions", make_embed("🔨 Ban", f"{user} a été banni.", discord.Color.red()))


@bot.event
async def on_member_unban(guild, user):
    await send_log(guild, "sanctions", make_embed("♻️ Unban", f"{user} a été débanni.", discord.Color.green()))


@bot.event
async def on_message_delete(message):
    if message.guild is None or message.author.bot:
        return
    content = message.content[:900] or "*vide*"
    await send_log(message.guild, "messages", make_embed(
        "🗑️ Message supprimé",
        f"**Auteur :** {message.author.mention}\n**Salon :** {message.channel.mention}\n**Contenu :** {content}",
        discord.Color.dark_grey(),
    ))


@bot.event
async def on_guild_channel_create(channel):
    await send_log(channel.guild, "structure",
                   make_embed("➕ Salon créé", channel.name, discord.Color.green()))
    await check_creation_raid(channel.guild, discord.AuditLogAction.channel_create)


@bot.event
async def on_guild_channel_delete(channel):
    await send_log(channel.guild, "structure",
                   make_embed("➖ Salon supprimé", channel.name, discord.Color.orange()))
    topic = getattr(channel, "topic", None) or ""
    if topic.startswith("DM:"):
        uid = topic[3:]
        if data["dmtickets"].get(uid) == channel.id:
            data["dmtickets"].pop(uid, None)
            save_data()


@bot.event
async def on_guild_role_create(role):
    await check_creation_raid(role.guild, discord.AuditLogAction.role_create)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # MP envoyés au bot
    if message.guild is None:
        await handle_dm(message)
        return

    # Anti-liens
    if is_on("antiliens", message.guild) and LINK_RE.search(message.content):
        if not message.author.guild_permissions.manage_messages:
            try:
                await message.delete()
                await message.channel.send(
                    f"🔗 {message.author.mention}, les liens ne sont pas autorisés ici.", delete_after=8)
            except discord.HTTPException:
                pass
            return

    # Réponse du staff dans un ticket MP
    await relay_staff_reply(message)

    # Compteur infini
    cfg = data["infini"].get(str(message.guild.id))
    if cfg and cfg["channel"] == message.channel.id and re.fullmatch(r"\d+", message.content.strip()):
        number = int(message.content.strip())
        try:
            if number == cfg["count"] + 1:
                cfg["count"] = number
                save_data()
                await message.add_reaction("✅")
            else:
                cfg["count"] = 0
                save_data()
                await message.add_reaction("❌")
                await message.channel.send(
                    f"❌ {message.author.mention} s'est trompé ! Le compte repart à 0.", delete_after=10)
        except discord.HTTPException:
            pass



# ============================ ERREURS ============================
@bot.tree.error
async def on_app_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        text = "Tu n'as pas la permission d'utiliser cette commande."
    else:
        traceback.print_exception(type(error), error, error.__traceback__)
        text = "Une erreur est survenue."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ {text}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {text}", ephemeral=True)
    except discord.HTTPException:
        pass


