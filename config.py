"""Configuration : constantes, textes, menus d'aide."""

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

# ================================ CONFIG ================================
TOKEN = os.getenv("DISCORD_TOKEN", "TON_TOKEN_ICI")
SERVER_NAME = "Abde"
# Sur Railway, le disque du conteneur est effacé à chaque déploiement.
# Il faut monter un Volume (ex. chemin /data) et définir DATA_FILE=/data/bot_data.json
# dans les variables. Sans variable, le fichier est créé à côté du script (usage local).
DATA_FILE = os.getenv("DATA_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bot_data.json")

# Anti-raid
RAID_JOIN_LIMIT = 5        # 5 arrivées...
RAID_WINDOW = 10           # ...en 10 secondes = raid
RAID_CREATE_LIMIT = 4      # 4 salons/rôles créés par la même personne en 10 s = raid
LOCKDOWN_DURATION = 600    # secondes avant de remettre les permissions des salons

# Recrutement : les postes proposés dans le menu déroulant (modifiable librement)
POSTES = [
    {"id": "mod_discord", "label": "Modérateur Discord", "emoji": "👮", "desc": "Modérer le serveur Discord"},
    {"id": "anim_discord", "label": "Animateur Discord", "emoji": "🎉", "desc": "Animer la communauté Discord"},
    {"id": "mod_reseaux", "label": "Modérateur Réseaux", "emoji": "🌐", "desc": "Modérer les réseaux et YouTube"},
]

DEFAULT_WELCOME = (
    "Salut {membre} ! Nous sommes ravis de t'accueillir sur le serveur communautaire de "
    "**{serveur}**, un espace de partage, de détente et de bonne humeur 💖\n\n"
    "🚀 Nous te souhaitons une excellente aventure parmi nous !"
)

DEFAULT_TICKET_MENU = (
    "Aide & Question|Une question ou un problème|❓;"
    "Signalement|Signaler un membre|⚠️;"
    "Contacter la direction|Message au Haut Staff|🌱"
)

# Salons créés automatiquement par /logsautomatique : (clé, nom du salon)
LOG_KINDS = [
    ("join", "logs-arrivees-departs"),
    ("messages", "logs-messages"),
    ("sanctions", "logs-sanctions"),
    ("structure", "logs-salons-roles"),
]

LINK_RE = re.compile(r"(https?://|www\.|discord\.gg/)\S+", re.IGNORECASE)

TWITCH_URL = "https://www.twitch.tv/sinoorzl"
TWITCH_STATUS = "Rejoins-nous sur Twitch !"

ON_OFF = [
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
]

OUI_NON = [
    app_commands.Choice(name="Oui", value="oui"),
    app_commands.Choice(name="Non", value="non"),
]

HELP = {
    "🛡️ Anti-raid & sécurité": [
        ("/antiraid on|off", "Bloque les arrivées massives et les créations de salons/rôles en masse."),
        ("/antiliens on|off", "Supprime automatiquement les liens envoyés par les membres."),
    ],
    "🔨 Modération": [
        ("/ban membre [raison]", "Bannit l'utilisateur sur tous les serveurs où le bot est présent."),
        ("/blacklist membre [raison]", "Blacklist globale : ban partout + ban automatique à l'arrivée."),
        ("/unban id", "Débannit un utilisateur de ce serveur."),
        ("/unblacklist id", "Retire de la blacklist et débannit partout."),
        ("/kick membre [raison]", "Expulse un membre."),
        ("/mute membre [minutes] [raison]", "Met un membre en timeout (10 min par défaut)."),
        ("/unmute membre", "Retire le timeout d'un membre."),
        ("/rank membre role message salon", "Donne le rôle et publie un rank dans un salon (administrateurs)."),
        ("/derank membre role message salon", "Retire le rôle et publie un derank dans un salon (administrateurs)."),
    ],
    "💬 Salons": [
        ("/slowmode secondes", "Active le mode lent dans ce salon (0 pour désactiver)."),
        ("/lock", "Verrouille le salon actuel."),
        ("/unlock", "Déverrouille le salon actuel."),
        ("/clear nombre", "Supprime jusqu'à 100 messages."),
    ],
    "🎫 Tickets": [
        ("/ticketsettings ...", "Configure et publie le panel de tickets (menu, bannière, transcription, avis...)."),
        ("/ticketmp on|off", "Les MP envoyés au bot ouvrent un ticket visible par le staff, et le staff répond en MP."),
    ],
    "⚙️ Configuration": [
        ("/bienvenuesettings", "Ouvre le panel de bienvenue : salon, message, bannière, rôle automatique."),
        ("/reglementsettings", "Ouvre le panel du règlement : texte, salon, rôle à l'acceptation, publication."),
        ("/logsautomatique", "Crée automatiquement les salons de logs dans une catégorie privée."),
        ("/infini salon", "Lance le compteur infini dans un salon."),
        ("/recrutement salon_panel salon_candidatures", "Publie le panel de recrutement et choisit où arrivent les candidatures."),
    ],
}

