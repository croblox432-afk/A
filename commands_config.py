"""Commandes : salons et configuration."""

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
from welcome import *
from rules import *
from recruit import *
from tickets import *

# ============================ SALONS ============================
@bot.tree.command(name="slowmode", description="Active le mode lent dans ce salon")
@app_commands.describe(secondes="Délai entre deux messages (0 pour désactiver, max 21600)")
@has_perms(manage_channels=True)
@app_commands.guild_only()
async def slowmode(interaction: discord.Interaction, secondes: app_commands.Range[int, 0, 21600]):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await error_msg(interaction, "Cette commande fonctionne seulement dans un salon texte.")
    await channel.edit(slowmode_delay=secondes, reason=f"Par {interaction.user}")
    msg = "Mode lent désactivé." if secondes == 0 else f"Mode lent réglé sur {secondes} s."
    await interaction.response.send_message(f"🐢 {msg}")


@bot.tree.command(name="lock", description="Verrouille le salon actuel")
@has_perms(manage_channels=True)
@app_commands.guild_only()
async def lock(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await error_msg(interaction, "Cette commande fonctionne seulement dans un salon texte.")
    await channel.set_permissions(interaction.guild.default_role, send_messages=False,
                                  reason=f"Lock par {interaction.user}")
    await interaction.response.send_message("🔒 Salon verrouillé.")


@bot.tree.command(name="unlock", description="Déverrouille le salon actuel")
@has_perms(manage_channels=True)
@app_commands.guild_only()
async def unlock(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await error_msg(interaction, "Cette commande fonctionne seulement dans un salon texte.")
    await channel.set_permissions(interaction.guild.default_role, send_messages=None,
                                  reason=f"Unlock par {interaction.user}")
    await interaction.response.send_message("🔓 Salon déverrouillé.")


@bot.tree.command(name="clear", description="Supprime des messages dans ce salon")
@app_commands.describe(nombre="Nombre de messages à supprimer (1 à 100)")
@has_perms(manage_messages=True)
@app_commands.guild_only()
async def clear(interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 100]):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await error_msg(interaction, "Cette commande fonctionne seulement dans un salon texte.")
    await interaction.response.defer(ephemeral=True)
    deleted = await channel.purge(limit=nombre)
    await interaction.followup.send(f"🧹 {len(deleted)} message(s) supprimé(s).", ephemeral=True)


# ============================ CONFIGURATION ============================
@bot.tree.command(name="bienvenuesettings", description="Ouvre le panel de configuration de la bienvenue")
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def bienvenuesettings(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=welcome_panel_embed(interaction.guild), view=WelcomePanelView(), ephemeral=True)


@bot.tree.command(name="reglementsettings", description="Ouvre le panel du règlement")
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def reglementsettings(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=rules_panel_embed(interaction.guild), view=RulesPanelView(), ephemeral=True)


@bot.tree.command(name="logsautomatique", description="Crée automatiquement tous les salons de logs")
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def logsautomatique(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    existing = data["logs"].get(str(guild.id))
    if isinstance(existing, dict) and all(log_channel(guild, kind) for kind, _ in LOG_KINDS):
        return await interaction.followup.send("ℹ️ Les logs automatiques sont déjà configurés.", ephemeral=True)

    try:
        category = await guild.create_category("📁 LOGS", overwrites=staff_overwrites(guild),
                                               reason=f"Logs automatiques par {interaction.user}")
        stored = {"category": category.id}
        for kind, name in LOG_KINDS:
            channel = await guild.create_text_channel(name, category=category,
                                                      overwrites=staff_overwrites(guild),
                                                      reason="Logs automatiques")
            stored[kind] = channel.id
    except discord.HTTPException as e:
        return await interaction.followup.send(f"❌ Impossible de créer les logs : {e}", ephemeral=True)

    data["logs"][str(guild.id)] = stored
    save_data()
    names = "\n".join(f"• #{name}" for _, name in LOG_KINDS)
    await interaction.followup.send(
        f"✅ Catégorie **📁 LOGS** créée (visible par les modérateurs et administrateurs) :\n{names}",
        ephemeral=True)


@bot.tree.command(name="infini", description="Lance le compteur infini dans un salon")
@app_commands.describe(salon="Salon du compteur")
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def infini(interaction: discord.Interaction, salon: discord.TextChannel):
    data["infini"][str(interaction.guild_id)] = {"channel": salon.id, "count": 0}
    save_data()
    await interaction.response.send_message(
        f"🔢 Compteur infini lancé dans {salon.mention}. Le premier nombre est **1**.", ephemeral=True)


@bot.tree.command(name="ticketsettings", description="Configure et publie le panel de tickets")
@app_commands.describe(
    salon="Salon où le panel de tickets est publié",
    titre="Titre du panel",
    texte="Texte du panel",
    menu="Options : Label|Description|Emoji ; séparées par des points-virgules",
    categorie="Catégorie où les tickets sont créés",
    salon_transcription="Salon des transcriptions et des avis",
    banniere="Lien d'une image (https://...) affichée en bannière du panel",
    reclamation="Afficher le bouton Réclamer",
    unclaim="Afficher le bouton Unclaim",
    avis="Demander un avis en MP à la fermeture",
)
@app_commands.choices(reclamation=OUI_NON, unclaim=OUI_NON, avis=OUI_NON)
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def ticketsettings(
    interaction: discord.Interaction,
    salon: discord.TextChannel,
    titre: str = "Support",
    texte: str = "Choisis une catégorie dans le menu ci-dessous pour ouvrir un ticket.",
    menu: str = DEFAULT_TICKET_MENU,
    categorie: Optional[discord.CategoryChannel] = None,
    salon_transcription: Optional[discord.TextChannel] = None,
    banniere: Optional[str] = None,
    reclamation: str = "oui",
    unclaim: str = "oui",
    avis: str = "oui",
):
    options = parse_menu(menu)
    if not options:
        return await error_msg(interaction, "Le menu est vide. Format : Label|Description|Emoji ; ...")
    if banniere and not banniere.startswith("http"):
        return await error_msg(interaction, "La bannière doit être un lien commençant par http(s).")

    gid = str(interaction.guild_id)
    data["ticket"][gid] = {
        "options": options,
        "categorie": categorie.id if categorie else None,
        "transcript": salon_transcription.id if salon_transcription else None,
        "reclamation": reclamation == "oui",
        "unclaim": unclaim == "oui",
        "avis": avis == "oui",
    }
    save_data()

    embed = make_embed(titre, texte, discord.Color.blurple())
    if banniere:
        embed.set_image(url=banniere)
    select_options = [
        discord.SelectOption(label=o["label"], description=o["desc"] or None,
                             emoji=o["emoji"], value=str(i))
        for i, o in enumerate(options)
    ]
    try:
        await salon.send(embed=embed, view=TicketPanelView(select_options))
    except discord.HTTPException as e:
        return await error_msg(interaction, f"Impossible de publier le panel : {e}")
    await interaction.response.send_message(
        f"✅ Panel publié dans {salon.mention} avec {len(options)} option(s).", ephemeral=True)


@bot.tree.command(name="ticketmp", description="Active les tickets par MP (les MP au bot ouvrent un ticket)")
@app_commands.describe(etat="on pour activer, off pour désactiver")
@app_commands.choices(etat=ON_OFF)
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def ticketmp(interaction: discord.Interaction, etat: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    cfg = data["ticketmp"]

    if etat.value == "off":
        cfg["enabled"] = False
        save_data()
        return await interaction.followup.send("🔕 Tickets par MP désactivés.", ephemeral=True)

    category = guild.get_channel(cfg["category"]) if cfg.get("guild") == guild.id and cfg.get("category") else None
    if category is None:
        try:
            category = await guild.create_category("📨 TICKETS MP", overwrites=staff_overwrites(guild),
                                                   reason=f"Tickets MP par {interaction.user}")
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Impossible de créer la catégorie : {e}", ephemeral=True)

    cfg.update({"enabled": True, "guild": guild.id, "category": category.id})
    save_data()
    await interaction.followup.send(
        f"✅ Tickets par MP activés. Catégorie **{category.name}** créée, visible seulement par les "
        "modérateurs et administrateurs.", ephemeral=True)


@bot.tree.command(name="recrutement", description="Publie le panel de recrutement et choisit où arrivent les candidatures")
@app_commands.describe(
    salon_panel="Salon où le message de recrutement est publié",
    salon_candidatures="Salon où arrivent les candidatures",
)
@has_perms(manage_guild=True)
@app_commands.guild_only()
async def recrutement(interaction: discord.Interaction,
                      salon_panel: discord.TextChannel,
                      salon_candidatures: discord.TextChannel):
    try:
        await salon_panel.send(embed=recruit_embed(), view=RecruitView())
    except discord.HTTPException as e:
        return await error_msg(interaction, f"Impossible de publier le panel : {e}")
    data["recrutement"][str(interaction.guild_id)] = salon_candidatures.id
    save_data()
    await interaction.response.send_message(
        f"✅ Panel publié dans {salon_panel.mention}. Les candidatures arriveront dans {salon_candidatures.mention}.",
        ephemeral=True)


