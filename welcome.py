"""Bienvenue : message, bannière, rôle automatique et panel."""

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

# ============================ BIENVENUE ============================
def welcome_cfg(guild_id):
    """Renvoie la config de bienvenue complète, avec les valeurs par défaut."""
    raw = data["bienvenue"].get(str(guild_id))
    if isinstance(raw, int):  # ancien format
        raw = {"channel": raw}
    cfg = {"channel": None, "message": "", "banner": "", "role": None}
    if raw:
        cfg.update(raw)
    return cfg


def set_welcome(guild_id, **changes):
    cfg = welcome_cfg(guild_id)
    cfg.update(changes)
    data["bienvenue"][str(guild_id)] = cfg
    save_data()


async def give_join_role(member):
    rid = welcome_cfg(member.guild.id)["role"]
    role = member.guild.get_role(rid) if rid else None
    if role:
        try:
            await member.add_roles(role, reason="Rôle automatique à l'arrivée")
        except discord.HTTPException:
            pass


async def send_welcome(member):
    cfg = welcome_cfg(member.guild.id)
    channel = member.guild.get_channel(cfg["channel"]) if cfg["channel"] else None
    if not channel:
        return

    text = cfg["message"] or DEFAULT_WELCOME
    text = (text.replace("{membre}", member.mention)
                .replace("{user}", member.mention)  # alias accepté
                .replace("{serveur}", SERVER_NAME)
                .replace("{nombre}", str(member.guild.member_count)))

    embed = make_embed(f"🎉 Bienvenue sur le serveur {SERVER_NAME} !", text, discord.Color.pink())
    if cfg["banner"]:
        embed.set_image(url=cfg["banner"])
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Membre n° {member.guild.member_count}")
    try:
        await channel.send(content=member.mention, embed=embed)
    except discord.HTTPException:
        pass


def welcome_panel_embed(guild):
    cfg = welcome_cfg(guild.id)
    channel = guild.get_channel(cfg["channel"]) if cfg["channel"] else None
    role = guild.get_role(cfg["role"]) if cfg["role"] else None
    embed = make_embed("⚙️ Panel de bienvenue", "Utilise les menus et les boutons ci-dessous.", discord.Color.pink())
    embed.add_field(name="📍 Salon", value=channel.mention if channel else "Non défini", inline=True)
    embed.add_field(name="🎭 Rôle automatique", value=role.mention if role else "Aucun", inline=True)
    embed.add_field(name="✉️ Message", value=(cfg["message"] or "Message par défaut")[:1000], inline=False)
    embed.add_field(name="🖼️ Bannière", value=cfg["banner"] or "Aucune", inline=False)
    return embed


class WelcomeChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Choisir le salon de bienvenue",
                         channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        set_welcome(interaction.guild_id, channel=self.values[0].id)
        await interaction.response.edit_message(embed=welcome_panel_embed(interaction.guild), view=self.view)


class WelcomeRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Rôle donné dès l'arrivée", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        set_welcome(interaction.guild_id, role=self.values[0].id)
        await interaction.response.edit_message(embed=welcome_panel_embed(interaction.guild), view=self.view)


class WelcomeMessageModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Message de bienvenue")
        self.texte = discord.ui.TextInput(
            label="Texte (balises : {membre} {serveur} {nombre})",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False,
        )
        self.add_item(self.texte)

    async def on_submit(self, interaction: discord.Interaction):
        set_welcome(interaction.guild_id, message=self.texte.value or "")
        await interaction.response.send_message("✅ Message de bienvenue enregistré.", ephemeral=True)


class WelcomeBannerModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Bannière de bienvenue")
        self.lien = discord.ui.TextInput(
            label="Lien de l'image (https://...) ou vide pour aucune",
            max_length=400,
            required=False,
        )
        self.add_item(self.lien)

    async def on_submit(self, interaction: discord.Interaction):
        link = (self.lien.value or "").strip()
        if link and not link.startswith("http"):
            return await interaction.response.send_message(
                "❌ La bannière doit être un lien commençant par http(s).", ephemeral=True)
        set_welcome(interaction.guild_id, banner=link)
        await interaction.response.send_message("✅ Bannière enregistrée.", ephemeral=True)


class WelcomeMessageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Message", emoji="✉️", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WelcomeMessageModal())


class WelcomeBannerButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Bannière", emoji="🖼️", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WelcomeBannerModal())


class WelcomeResetButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Réinitialiser", emoji="♻️", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        data["bienvenue"].pop(str(interaction.guild_id), None)
        save_data()
        await interaction.response.edit_message(embed=welcome_panel_embed(interaction.guild), view=self.view)


class WelcomePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900)
        self.add_item(WelcomeChannelSelect())
        self.add_item(WelcomeRoleSelect())
        self.add_item(WelcomeMessageButton())
        self.add_item(WelcomeBannerButton())
        self.add_item(WelcomeResetButton())


