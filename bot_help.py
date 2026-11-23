"""Menu /help."""

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

# ================================ HELP ================================
def help_embed(category=None):
    if category is None:
        return make_embed(f"📖 Aide – {SERVER_NAME}", "Choisis une catégorie dans le menu déroulant.")
    lines = "\n".join(f"**`{cmd}`** — {desc}" for cmd, desc in HELP[category])
    return make_embed(category, lines)


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, value=name) for name in HELP]
        super().__init__(placeholder="Choisis une catégorie...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=help_embed(self.values[0]), view=self.view)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(HelpSelect())



# ================================ HELP ================================
@bot.tree.command(name="help", description="Affiche toutes les commandes par catégorie")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=help_embed(), view=HelpView(), ephemeral=True)


