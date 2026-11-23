"""Point d'entrée : lance le bot (python main.py).

Les modules sont importés ici pour que leurs commandes et événements
soient enregistrés avant le démarrage.
"""

import sys
import traceback

import discord

from config import TOKEN
from core import bot
from storage import data, save_data, make_embed
import events  # noqa: F401  (événements Discord)
import commands_mod  # noqa: F401  (commandes de modération)
import commands_config  # noqa: F401  (commandes de configuration)
import bot_help  # noqa: F401  (commande /help)
from rules import RulesAcceptView
from recruit import RecruitView
from tickets import TicketPanelView, TicketControlView


async def setup_hook():
    # Vues persistantes : elles restent actives après un redémarrage
    bot.add_view(RecruitView())
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    bot.add_view(RulesAcceptView())
    await bot.tree.sync()


bot.setup_hook = setup_hook


if __name__ == "__main__":
    # Sur Railway : pas de console interactive. On quitte avec un code d'erreur
    # (non nul) pour que Railway affiche l'échec dans les logs et redémarre le service.
    token = TOKEN.strip().strip('"').strip("'")
    if token in ("", "TON_TOKEN_ICI"):
        print("[ERREUR] Variable DISCORD_TOKEN absente. Ajoute-la dans l'onglet Variables de Railway.",
              flush=True)
        sys.exit(1)
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("[ERREUR] Token invalide : copie-le en entier, sans espace ni guillemets, "
              "ou régénère-le dans le portail développeur (onglet Bot).", flush=True)
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
