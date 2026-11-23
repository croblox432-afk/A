"""Fonctions de modération globales (ban/unban partout)."""

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

# ============================ FONCTIONS MOD ============================
async def global_ban(user_id, reason):
    count = 0
    for guild in bot.guilds:
        try:
            await guild.ban(discord.Object(id=user_id), reason=reason)
            count += 1
        except discord.HTTPException:
            pass
    return count


async def global_unban(user_id, reason):
    for guild in bot.guilds:
        try:
            await guild.unban(discord.Object(id=user_id), reason=reason)
        except discord.HTTPException:
            pass


