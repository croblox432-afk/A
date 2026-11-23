"""Tickets (panel, réclamer, fermer) et tickets par MP."""

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

# ============================ TICKETS ============================
def parse_menu(text):
    options = []
    for part in text.split(";"):
        bits = [b.strip() for b in part.split("|")]
        if not bits or not bits[0]:
            continue
        options.append({
            "label": bits[0][:100],
            "desc": (bits[1] if len(bits) > 1 else "")[:100],
            "emoji": bits[2] if len(bits) > 2 and bits[2] else None,
        })
    return options[:25]


async def build_transcript(channel):
    lines = []
    async for msg in channel.history(limit=None, oldest_first=True):
        ts = msg.created_at.strftime("%d/%m/%Y %H:%M")
        text = msg.content or ""
        for attachment in msg.attachments:
            text += f" [pièce jointe : {attachment.url}]"
        lines.append(f"[{ts}] {msg.author} : {text}")
    return "\n".join(lines) or "(aucun message)"


class RatingSelect(discord.ui.Select):
    def __init__(self, log_ch):
        options = [discord.SelectOption(label="⭐" * n, value=str(n)) for n in range(1, 6)]
        super().__init__(placeholder="Note ton expérience...", options=options)
        self.log_ch = log_ch

    async def callback(self, interaction: discord.Interaction):
        note = int(self.values[0])
        if self.log_ch:
            try:
                await self.log_ch.send(embed=make_embed(
                    "⭐ Avis sur un ticket",
                    f"**Membre :** {interaction.user.mention}\n**Note :** {'⭐' * note} ({note}/5)",
                    discord.Color.gold(),
                ))
            except discord.HTTPException:
                pass
        await interaction.response.edit_message(content="Merci pour ton avis ! 💖", view=None)


class RatingView(discord.ui.View):
    def __init__(self, log_ch):
        super().__init__(timeout=259200)  # 3 jours
        self.add_item(RatingSelect(log_ch))


async def close_ticket(guild, channel, info, closer):
    cfg = data["ticket"].get(str(guild.id), {})
    transcript = await build_transcript(channel)
    log_ch = guild.get_channel(cfg["transcript"]) if cfg.get("transcript") else None
    claimer = f"<@{info['claimed_by']}>" if info.get("claimed_by") else "Personne"

    if log_ch:
        file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"transcript-{channel.name}.txt")
        try:
            await log_ch.send(
                embed=make_embed(
                    "📄 Ticket fermé",
                    f"**Salon :** {channel.name}\n**Type :** {info['type']}\n"
                    f"**Ouvert par :** <@{info['owner']}>\n**Fermé par :** {closer.mention}\n"
                    f"**Réclamé par :** {claimer}",
                    discord.Color.dark_grey(),
                ),
                file=file,
            )
        except discord.HTTPException:
            pass

    if cfg.get("avis"):
        owner = guild.get_member(info["owner"]) or bot.get_user(info["owner"])
        if owner:
            try:
                await owner.send(
                    embed=make_embed(f"🎫 Ton ticket « {info['type']} » est fermé",
                                     f"Peux-tu noter ton expérience sur **{guild.name}** ?",
                                     discord.Color.blurple()),
                    view=RatingView(log_ch),
                )
            except discord.HTTPException:
                pass

    data["tickets"].pop(str(channel.id), None)
    save_data()
    try:
        await channel.delete(reason=f"Ticket fermé par {closer}")
    except discord.HTTPException:
        pass


class TicketPanelSelect(discord.ui.Select):
    def __init__(self, options=None):
        opts = options or [discord.SelectOption(label="Ouvrir", value="0")]
        super().__init__(
            placeholder="Choisis une catégorie...",
            options=opts,
            min_values=1,
            max_values=1,
            custom_id="ticket_panel",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = data["ticket"].get(str(guild.id))
        if not cfg:
            return await interaction.response.send_message("❌ Les tickets ne sont pas configurés.", ephemeral=True)
        for info in data["tickets"].values():
            if info["guild"] == guild.id and info["owner"] == interaction.user.id:
                return await interaction.response.send_message(
                    "❌ Tu as déjà un ticket ouvert.", ephemeral=True)

        option = cfg["options"][int(self.values[0])]
        await interaction.response.defer(ephemeral=True)

        category = guild.get_channel(cfg["categorie"]) if cfg.get("categorie") else None
        overwrites = staff_overwrites(guild)
        overwrites[interaction.user] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True)

        clean_name = re.sub(r"[^a-z0-9-]", "", interaction.user.name.lower())[:20] or "membre"
        try:
            channel = await guild.create_text_channel(
                f"ticket-{clean_name}", category=category, overwrites=overwrites,
                reason=f"Ticket de {interaction.user}")
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Impossible de créer le ticket : {e}", ephemeral=True)

        data["tickets"][str(channel.id)] = {
            "guild": guild.id,
            "owner": interaction.user.id,
            "type": option["label"],
            "claimed_by": None,
        }
        save_data()

        embed = make_embed(
            f"🎫 {option['label']}",
            f"Bonjour {interaction.user.mention} ! Explique ta demande, le staff te répondra dès que possible.",
            discord.Color.blurple(),
        )
        view = TicketControlView(claim=cfg.get("reclamation", True), unclaim=cfg.get("unclaim", True))
        await channel.send(content=interaction.user.mention, embed=embed, view=view)
        await interaction.followup.send(f"✅ Ton ticket a été ouvert : {channel.mention}", ephemeral=True)


class TicketPanelView(discord.ui.View):
    def __init__(self, options=None):
        super().__init__(timeout=None)
        self.add_item(TicketPanelSelect(options))


class ClaimButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Réclamer", emoji="🙋", style=discord.ButtonStyle.success, custom_id="ticket_claim")

    async def callback(self, interaction: discord.Interaction):
        info = data["tickets"].get(str(interaction.channel_id))
        if not info:
            return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Seul le staff peut réclamer un ticket.", ephemeral=True)
        if info["claimed_by"]:
            return await interaction.response.send_message(
                f"❌ Ce ticket est déjà réclamé par <@{info['claimed_by']}>.", ephemeral=True)
        info["claimed_by"] = interaction.user.id
        save_data()
        await interaction.response.send_message(f"🙋 {interaction.user.mention} a réclamé ce ticket.")


class UnclaimButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Unclaim", emoji="↩️", style=discord.ButtonStyle.secondary, custom_id="ticket_unclaim")

    async def callback(self, interaction: discord.Interaction):
        info = data["tickets"].get(str(interaction.channel_id))
        if not info or not info["claimed_by"]:
            return await interaction.response.send_message("❌ Ce ticket n'est pas réclamé.", ephemeral=True)
        is_admin = interaction.user.guild_permissions.administrator
        if info["claimed_by"] != interaction.user.id and not is_admin:
            return await interaction.response.send_message(
                "❌ Seul celui qui a réclamé le ticket (ou un admin) peut le libérer.", ephemeral=True)
        info["claimed_by"] = None
        save_data()
        await interaction.response.send_message(f"↩️ {interaction.user.mention} a libéré le ticket.")


class CloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Fermer", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_close")

    async def callback(self, interaction: discord.Interaction):
        info = data["tickets"].get(str(interaction.channel_id))
        if not info:
            return await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        if not (is_staff(interaction.user) or interaction.user.id == info["owner"]):
            return await interaction.response.send_message("❌ Tu ne peux pas fermer ce ticket.", ephemeral=True)
        await interaction.response.defer()
        await close_ticket(interaction.guild, interaction.channel, info, interaction.user)


class TicketControlView(discord.ui.View):
    def __init__(self, claim=True, unclaim=True):
        super().__init__(timeout=None)
        if claim:
            self.add_item(ClaimButton())
        if unclaim:
            self.add_item(UnclaimButton())
        self.add_item(CloseButton())


# ============================ TICKETS PAR MP ============================
async def handle_dm(message):
    """Un MP envoyé au bot ouvre (ou alimente) un ticket visible par le staff."""
    cfg = data["ticketmp"]
    if not cfg.get("enabled"):
        return
    guild = bot.get_guild(cfg.get("guild", 0))
    category = guild.get_channel(cfg["category"]) if guild and cfg.get("category") else None
    if guild is None or category is None:
        return

    user = message.author
    channel = None
    cid = data["dmtickets"].get(str(user.id))
    if cid:
        channel = guild.get_channel(cid)
    created = channel is None
    if created:
        clean = re.sub(r"[^a-z0-9-]", "", user.name.lower())[:20] or "membre"
        try:
            channel = await guild.create_text_channel(
                f"mp-{clean}", category=category, topic=f"DM:{user.id}",
                overwrites=staff_overwrites(guild), reason=f"Ticket MP de {user}")
        except discord.HTTPException:
            return
        data["dmtickets"][str(user.id)] = channel.id
        save_data()
        await channel.send(embed=make_embed(
            "📨 Nouveau ticket MP",
            f"**Utilisateur :** {user.mention} ({user})\n**ID :** `{user.id}`",
            discord.Color.blue()))

    forward = discord.Embed(description=message.content or "*(pièce jointe)*", color=discord.Color.blue())
    forward.set_author(name=str(user), icon_url=user.display_avatar.url)
    urls = "\n".join(a.url for a in message.attachments)
    if urls:
        forward.add_field(name="Pièces jointes", value=urls[:1000], inline=False)
    await channel.send(embed=forward)

    if created:
        ack = discord.Embed(
            title="🎫 Ticket ouvert",
            description=f"Ton message a bien été transmis au staff d'**{SERVER_NAME}**. "
                        "Un membre du staff te répondra ici, en message privé.",
            color=discord.Color.blue(),
        )
        ack.set_footer(text=SERVER_NAME)
        try:
            await user.send(embed=ack)
        except discord.HTTPException:
            pass
    else:
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass


async def relay_staff_reply(message):
    """Une réponse d'un membre du staff dans un ticket MP est envoyée en MP à l'utilisateur."""
    topic = getattr(message.channel, "topic", None) or ""
    if not topic.startswith("DM:") or not is_staff(message.author):
        return
    try:
        uid = int(topic[3:])
    except ValueError:
        return
    user = bot.get_user(uid)
    if user is None:
        try:
            user = await bot.fetch_user(uid)
        except discord.HTTPException:
            return

    body = message.content or ""
    urls = "\n".join(a.url for a in message.attachments)
    if urls:
        body = f"{body}\n{urls}".strip()
    if not body:
        return

    embed = discord.Embed(description=body, color=discord.Color.blue())
    embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
    embed.set_footer(text=SERVER_NAME)
    try:
        await user.send(embed=embed)
    except discord.HTTPException:
        await message.channel.send("⚠️ Impossible d'envoyer le MP à ce membre.", delete_after=10)


