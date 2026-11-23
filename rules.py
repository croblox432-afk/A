"""Règlement : texte, publication et bouton d'acceptation."""

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

# ============================ RÈGLEMENT ============================
def rules_cfg(guild_id):
    cfg = {"channel": None, "role": None, "text": ""}
    cfg.update(data["reglement"].get(str(guild_id)) or {})
    return cfg


def set_rules(guild_id, **changes):
    cfg = rules_cfg(guild_id)
    cfg.update(changes)
    data["reglement"][str(guild_id)] = cfg
    save_data()


def rules_panel_embed(guild):
    cfg = rules_cfg(guild.id)
    channel = guild.get_channel(cfg["channel"]) if cfg["channel"] else None
    role = guild.get_role(cfg["role"]) if cfg["role"] else None
    embed = make_embed("📜 Panel du règlement",
                       "Choisis le salon et le rôle, rédige le texte, puis publie.", discord.Color.gold())
    embed.add_field(name="📍 Salon de publication", value=channel.mention if channel else "Non défini", inline=True)
    embed.add_field(name="🎭 Rôle à l'acceptation", value=role.mention if role else "Non défini", inline=True)
    embed.add_field(name="📝 Texte", value=(cfg["text"][:1000] or "Non défini"), inline=False)
    return embed


class RulesChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Salon où publier le règlement",
                         channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        set_rules(interaction.guild_id, channel=self.values[0].id)
        await interaction.response.edit_message(embed=rules_panel_embed(interaction.guild), view=self.view)


class RulesRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Rôle donné à l'acceptation", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        set_rules(interaction.guild_id, role=self.values[0].id)
        await interaction.response.edit_message(embed=rules_panel_embed(interaction.guild), view=self.view)


class RulesTextModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Texte du règlement")
        self.texte = discord.ui.TextInput(
            label="Texte du règlement",
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True,
        )
        self.add_item(self.texte)

    async def on_submit(self, interaction: discord.Interaction):
        set_rules(interaction.guild_id, text=self.texte.value)
        await interaction.response.send_message("✅ Texte du règlement enregistré.", ephemeral=True)


class RulesTextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Texte", emoji="📝", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RulesTextModal())


class RulesPublishButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Publier", emoji="📢", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        cfg = rules_cfg(interaction.guild_id)
        channel = interaction.guild.get_channel(cfg["channel"]) if cfg["channel"] else None
        if not (channel and cfg["role"] and cfg["text"]):
            return await interaction.response.send_message(
                "❌ Il faut un salon, un rôle et un texte avant de publier.", ephemeral=True)
        embed = make_embed(f"📜 Règlement – {SERVER_NAME}", cfg["text"], discord.Color.gold())
        embed.set_footer(text="En cliquant sur le bouton ci-dessous, vous confirmez avoir lu et accepté ce règlement.")
        try:
            await channel.send(embed=embed, view=RulesAcceptView())
        except discord.HTTPException as e:
            return await interaction.response.send_message(f"❌ Impossible de publier : {e}", ephemeral=True)
        await interaction.response.send_message(f"✅ Règlement publié dans {channel.mention}.", ephemeral=True)


class RulesPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900)
        self.add_item(RulesChannelSelect())
        self.add_item(RulesRoleSelect())
        self.add_item(RulesTextButton())
        self.add_item(RulesPublishButton())


class RulesAcceptButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Accepter le règlement", emoji="✅",
                         style=discord.ButtonStyle.success, custom_id="rules_accept")

    async def callback(self, interaction: discord.Interaction):
        cfg = rules_cfg(interaction.guild_id)
        role = interaction.guild.get_role(cfg["role"]) if cfg["role"] else None
        if not role:
            return await interaction.response.send_message(
                "❌ Le rôle du règlement n'est pas configuré.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message("Tu as déjà accepté le règlement ✅", ephemeral=True)
        try:
            await interaction.user.add_roles(role, reason="Règlement accepté")
        except discord.HTTPException:
            return await interaction.response.send_message("❌ Impossible de te donner le rôle.", ephemeral=True)
        # Pas de message public : seulement la confirmation privée
        await interaction.response.send_message("✅ Règlement accepté.", ephemeral=True)


class RulesAcceptView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # reste actif après redémarrage
        self.add_item(RulesAcceptButton())


