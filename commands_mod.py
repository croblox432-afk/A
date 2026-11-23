"""Commandes : anti-raid, liens, modération, rank."""

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
from moderation import *
from raid import *

# ============================ ANTI-RAID / LIENS ============================
@bot.tree.command(name="antiraid", description="Active ou désactive l'anti-raid")
@app_commands.describe(etat="on pour activer, off pour désactiver")
@app_commands.choices(etat=ON_OFF)
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def antiraid(interaction: discord.Interaction, etat: app_commands.Choice[str]):
    await interaction.response.defer()
    guild = interaction.guild
    data["antiraid"][str(guild.id)] = etat.value == "on"
    save_data()
    if etat.value == "on":
        embed = make_embed("🛡️ Anti-raid activé",
                           "Les arrivées massives et les créations de salons/rôles en masse seront bloquées.",
                           discord.Color.green())
    else:
        if guild.id in raid_mode or str(guild.id) in data["lockdown"]:
            await end_raid(guild, "Anti-raid désactivé : permissions restaurées")
        embed = make_embed("🛡️ Anti-raid désactivé", color=discord.Color.red())
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="antiliens", description="Supprime automatiquement les liens")
@app_commands.describe(etat="on pour activer, off pour désactiver")
@app_commands.choices(etat=ON_OFF)
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def antiliens(interaction: discord.Interaction, etat: app_commands.Choice[str]):
    data["antiliens"][str(interaction.guild_id)] = etat.value == "on"
    save_data()
    state = "activé 🔗" if etat.value == "on" else "désactivé"
    await interaction.response.send_message(f"Anti-liens {state}.")


# ============================ MODÉRATION ============================
@bot.tree.command(name="ban", description="Bannit un utilisateur sur tous les serveurs du bot")
@app_commands.describe(membre="Utilisateur à bannir", raison="Raison du ban")
@has_perms(ban_members=True)
@app_commands.guild_only()
async def ban(interaction: discord.Interaction, membre: discord.User, raison: str = "Aucune raison"):
    await interaction.response.defer()
    count = await global_ban(membre.id, f"{interaction.user} : {raison}")
    await interaction.followup.send(embed=make_embed(
        "🔨 Ban global",
        f"{membre.mention} a été banni sur **{count}** serveur(s).\n**Raison :** {raison}",
        discord.Color.red(),
    ))


@bot.tree.command(name="blacklist", description="Blacklist globale : ban partout + ban à l'arrivée")
@app_commands.describe(membre="Utilisateur à blacklister", raison="Raison")
@has_perms(ban_members=True)
@app_commands.guild_only()
async def blacklist(interaction: discord.Interaction, membre: discord.User, raison: str = "Aucune raison"):
    await interaction.response.defer()
    if membre.id not in data["blacklist"]:
        data["blacklist"].append(membre.id)
        save_data()
    count = await global_ban(membre.id, f"Blacklist : {raison}")
    await interaction.followup.send(embed=make_embed(
        "⛔ Blacklist globale",
        f"{membre.mention} est blacklisté. Banni sur **{count}** serveur(s) et banni automatiquement à l'arrivée.\n"
        f"**Raison :** {raison}",
        discord.Color.dark_red(),
    ))


@bot.tree.command(name="unban", description="Débannit un utilisateur de ce serveur")
@app_commands.describe(utilisateur_id="ID de l'utilisateur à débannir")
@has_perms(ban_members=True)
@app_commands.guild_only()
async def unban(interaction: discord.Interaction, utilisateur_id: str):
    uid = parse_id(utilisateur_id)
    if uid is None:
        return await error_msg(interaction, "ID invalide.")
    try:
        await interaction.guild.unban(discord.Object(id=uid), reason=f"Par {interaction.user}")
    except discord.NotFound:
        return await error_msg(interaction, "Cet utilisateur n'est pas banni ici.")
    except discord.HTTPException as e:
        return await error_msg(interaction, f"Impossible de débannir : {e}")
    await interaction.response.send_message(f"♻️ <@{uid}> a été débanni.")


@bot.tree.command(name="unblacklist", description="Retire un utilisateur de la blacklist et le débannit partout")
@app_commands.describe(utilisateur_id="ID de l'utilisateur")
@has_perms(ban_members=True)
@app_commands.guild_only()
async def unblacklist(interaction: discord.Interaction, utilisateur_id: str):
    uid = parse_id(utilisateur_id)
    if uid is None:
        return await error_msg(interaction, "ID invalide.")
    await interaction.response.defer()
    if uid in data["blacklist"]:
        data["blacklist"].remove(uid)
        save_data()
    await global_unban(uid, f"Unblacklist par {interaction.user}")
    await interaction.followup.send(f"✅ <@{uid}> n'est plus blacklisté.")


@bot.tree.command(name="kick", description="Expulse un membre")
@app_commands.describe(membre="Membre à expulser", raison="Raison")
@has_perms(kick_members=True)
@app_commands.guild_only()
async def kick(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison"):
    try:
        await membre.kick(reason=f"{interaction.user} : {raison}")
    except discord.HTTPException as e:
        return await error_msg(interaction, f"Impossible d'expulser : {e}")
    await interaction.response.send_message(f"👢 {membre} a été expulsé. Raison : {raison}")


@bot.tree.command(name="mute", description="Met un membre en timeout")
@app_commands.describe(membre="Membre à mute", minutes="Durée en minutes (max 40320)", raison="Raison")
@has_perms(moderate_members=True)
@app_commands.guild_only()
async def mute(interaction: discord.Interaction, membre: discord.Member,
               minutes: app_commands.Range[int, 1, 40320] = 10, raison: str = "Aucune raison"):
    try:
        await membre.timeout(datetime.timedelta(minutes=minutes), reason=f"{interaction.user} : {raison}")
    except discord.HTTPException as e:
        return await error_msg(interaction, f"Impossible de mute : {e}")
    await interaction.response.send_message(f"🔇 {membre.mention} est muet pendant {minutes} min. Raison : {raison}")


@bot.tree.command(name="unmute", description="Retire le timeout d'un membre")
@app_commands.describe(membre="Membre à unmute")
@has_perms(moderate_members=True)
@app_commands.guild_only()
async def unmute(interaction: discord.Interaction, membre: discord.Member):
    try:
        await membre.timeout(None, reason=f"Unmute par {interaction.user}")
    except discord.HTTPException as e:
        return await error_msg(interaction, f"Impossible d'unmute : {e}")
    await interaction.response.send_message(f"🔊 {membre.mention} peut à nouveau parler.")


@bot.tree.command(name="rank", description="Donne un rôle et publie un rank (administrateurs)")
@app_commands.describe(membre="Membre concerné", role="Rôle à donner", message="Message du rank", salon="Salon où publier")
@has_perms(administrator=True)
@app_commands.guild_only()
async def rank(interaction: discord.Interaction, membre: discord.Member, role: discord.Role,
               message: str, salon: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    try:
        await membre.add_roles(role, reason=f"Rank par {interaction.user}")
    except discord.HTTPException as e:
        return await interaction.followup.send(f"❌ Impossible de donner le rôle : {e}", ephemeral=True)
    embed = make_embed("🏅 Rank",
                       f"**Membre :** {membre.mention}\n**Rôle :** {role.mention}\n**Message :** {message}",
                       discord.Color.gold())
    embed.set_thumbnail(url=membre.display_avatar.url)
    await salon.send(embed=embed)
    await interaction.followup.send(f"✅ Rôle donné et rank publié dans {salon.mention}.", ephemeral=True)


@bot.tree.command(name="derank", description="Retire un rôle et publie un derank (administrateurs)")
@app_commands.describe(membre="Membre concerné", role="Rôle à retirer", message="Message du derank", salon="Salon où publier")
@has_perms(administrator=True)
@app_commands.guild_only()
async def derank(interaction: discord.Interaction, membre: discord.Member, role: discord.Role,
                 message: str, salon: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    try:
        await membre.remove_roles(role, reason=f"Derank par {interaction.user}")
    except discord.HTTPException as e:
        return await interaction.followup.send(f"❌ Impossible de retirer le rôle : {e}", ephemeral=True)
    embed = make_embed("📉 Derank",
                       f"**Membre :** {membre.mention}\n**Rôle retiré :** {role.mention}\n**Message :** {message}",
                       discord.Color.red())
    embed.set_thumbnail(url=membre.display_avatar.url)
    await salon.send(embed=embed)
    await interaction.followup.send(f"✅ Rôle retiré et derank publié dans {salon.mention}.", ephemeral=True)


