"""Recrutement : panel et formulaire de candidature."""

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

# ============================ RECRUTEMENT ============================
def recruit_embed():
    embed = make_embed(
        f"🎓 Recrutement – {SERVER_NAME}",
        f"📌 Le serveur **{SERVER_NAME}** recrute !\n"
        "Pas beaucoup de profils vont être acceptés, détaille donc un maximum tes candidatures.",
        discord.Color.purple(),
    )
    embed.add_field(
        name="Pôles recherchés",
        value="\n".join(f"{p['emoji']} {p['label']}" for p in POSTES),
        inline=False,
    )
    embed.add_field(
        name="Comment postuler ?",
        value="Choisis le poste voulu dans le menu déroulant ci-dessous ✅",
        inline=False,
    )
    embed.add_field(
        name="Conditions",
        value="• Avoir **16 ans**\n"
              "• Avoir une bonne **connaissance** globale de Discord\n"
              "• Avoir une **orthographe** irréprochable\n"
              "• Ne pas avoir de **sanctions**, ou très **peu**\n"
              "• Être **motivé**",
        inline=False,
    )
    embed.add_field(name="Date de fin des recrutements", value="`Indéterminée`", inline=False)
    embed.set_footer(text=f"{len(POSTES)} postes disponibles · choisis un poste dans le menu")
    return embed


class ApplyModal(discord.ui.Modal):
    def __init__(self, poste):
        super().__init__(title=f"Candidature – {poste['label']}"[:45])
        self.poste = poste
        self.pseudo = discord.ui.TextInput(label="Pseudo Discord et âge", max_length=100)
        self.experience = discord.ui.TextInput(
            label="Ton expérience sur Discord", style=discord.TextStyle.paragraph, max_length=800)
        self.motivation = discord.ui.TextInput(
            label="Ta motivation", style=discord.TextStyle.paragraph, max_length=800)
        self.dispo = discord.ui.TextInput(label="Tes disponibilités", required=False, max_length=200)
        for item in (self.pseudo, self.experience, self.motivation, self.dispo):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        cid = data["recrutement"].get(str(interaction.guild_id))
        channel = interaction.guild.get_channel(cid) if cid and interaction.guild else None
        if not channel:
            await interaction.response.send_message(
                "❌ Le salon des candidatures n'est pas configuré.", ephemeral=True)
            return
        embed = make_embed(f"📝 Candidature – {self.poste['label']}", color=discord.Color.purple())
        embed.add_field(name="Candidat", value=f"{interaction.user.mention} ({interaction.user})", inline=False)
        embed.add_field(name="Pseudo et âge", value=self.pseudo.value, inline=False)
        embed.add_field(name="Expérience", value=self.experience.value, inline=False)
        embed.add_field(name="Motivation", value=self.motivation.value, inline=False)
        embed.add_field(name="Disponibilités", value=self.dispo.value or "Non précisé", inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            await interaction.response.send_message("❌ Impossible d'envoyer la candidature.", ephemeral=True)
            return
        await interaction.response.send_message("✅ Ta candidature a bien été envoyée !", ephemeral=True)


class RecruitSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=p["label"], value=p["id"], emoji=p["emoji"], description=p["desc"])
            for p in POSTES
        ]
        super().__init__(
            placeholder="Choisis un poste...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="recruit_select",
        )

    async def callback(self, interaction: discord.Interaction):
        poste = next(p for p in POSTES if p["id"] == self.values[0])
        await interaction.response.send_modal(ApplyModal(poste))


class RecruitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # reste actif après redémarrage
        self.add_item(RecruitSelect())


