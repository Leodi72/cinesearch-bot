import logging
import os
import requests
from datetime import datetime, timezone
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# =============================================
# 🔧 CONFIGURATION
# =============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TMDB_API_KEY = "05902896074695709d7763505bb88b4d"
ADMIN_IDS = [5140415021]

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Stockage des demandes en attente
demandes_en_attente = {}

# États de conversation
ATTENTE_TITRE_AJOUT = 1
ATTENTE_LIEN_SIGNALEMENT = 2
ATTENTE_TITRE_RECHERCHE = 3
ATTENTE_MESSAGE_AUTRE = 4

# =============================================
# 🕐 Salutation selon l'heure française
# =============================================
def get_salutation() -> str:
    heure_locale = (datetime.now(timezone.utc).hour + 1) % 24
    if 6 <= heure_locale < 18:
        return "🌞 Merci et bonne journée !"
    else:
        return "🌙 Merci et bonne soirée !"

# =============================================
# 🎬 Recherche TMDB
# =============================================
def recherche_tmdb(titre: str):
    url = "https://api.themoviedb.org/3/search/multi"
    params = {
        "api_key": TMDB_API_KEY,
        "query": titre,
        "language": "fr-FR",
        "page": 1
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        resultats = []
        for item in data.get("results", [])[:5]:
            media_type = item.get("media_type")
            if media_type == "movie":
                nom = item.get("title", "?")
                annee = item.get("release_date", "")[:4]
                emoji = "🎬"
                type_fr = "Film"
            elif media_type == "tv":
                nom = item.get("name", "?")
                annee = item.get("first_air_date", "")[:4]
                emoji = "📺"
                type_fr = "Série"
            else:
                continue
            tmdb_id = item.get("id")
            tmdb_url = f"https://www.themoviedb.org/{media_type}/{tmdb_id}"
            resultats.append({
                "nom": nom,
                "annee": annee,
                "emoji": emoji,
                "type": type_fr,
                "url": tmdb_url,
            })
        return resultats
    except Exception:
        return []

# =============================================
# Claviers
# =============================================
def build_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Signaler un lien inactif", callback_data="menu_signalement")],
        [InlineKeyboardButton("➕ Demande d'ajout de film/série", callback_data="menu_ajout")],
        [InlineKeyboardButton("🎬 Rechercher un film/série", callback_data="menu_recherche")],
        [InlineKeyboardButton("📩 Autre problème ou demande", callback_data="menu_autre")],
    ])

def build_retour_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Faire une autre demande", callback_data="menu_retour")],
    ])

def build_tmdb_keyboard(resultats: list):
    boutons = []
    for r in resultats:
        label = f"{r['emoji']} {r['nom']} ({r['annee']}) — {r['type']}"
        boutons.append([InlineKeyboardButton(label, url=r['url'])])
    boutons.append([InlineKeyboardButton("🔁 Faire une autre demande", callback_data="menu_retour")])
    return InlineKeyboardMarkup(boutons)

def build_approbation_keyboard(demande_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📺 Déjà en ligne", callback_data=f"deja_{demande_id}"),
            InlineKeyboardButton("✅ Accepter", callback_data=f"accept_{demande_id}"),
            InlineKeyboardButton("❌ Refuser", callback_data=f"refuse_{demande_id}"),
        ]
    ])

# =============================================
# /start — Affiche le menu
# =============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenue sur CineSearch !\n\n"
        "Comment puis-je t'aider ? 👇",
        reply_markup=build_menu_keyboard()
    )
    return ConversationHandler.END

# =============================================
# Gestion des boutons du menu
# =============================================
async def bouton_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cle = query.data

    # ── Menu ──
    if cle == "menu_retour":
        await query.edit_message_text(
            "Comment puis-je t'aider ? 👇",
            reply_markup=build_menu_keyboard()
        )
        return ConversationHandler.END

    elif cle == "menu_signalement":
        await query.edit_message_text(
            "🔗 *Signalement de lien inactif*\n\n"
            "Envoie-moi le lien du film/série concerné :",
            parse_mode="Markdown"
        )
        return ATTENTE_LIEN_SIGNALEMENT

    elif cle == "menu_ajout":
        await query.edit_message_text(
            "➕ *Demande d'ajout*\n\n"
            "Quel film ou série souhaites-tu ajouter ?\n"
            "Envoie-moi le titre :",
            parse_mode="Markdown"
        )
        return ATTENTE_TITRE_AJOUT

    elif cle == "menu_recherche":
        await query.edit_message_text(
            "🎬 *Recherche TMDB*\n\n"
            "Quel film ou série cherches-tu ?\n"
            "Envoie-moi le titre :",
            parse_mode="Markdown"
        )
        return ATTENTE_TITRE_RECHERCHE

    elif cle == "menu_autre":
        await query.edit_message_text(
            "📩 *Autre problème ou demande*\n\n"
            "Décris-moi ton problème ou ta demande :",
            parse_mode="Markdown"
        )
        return ATTENTE_MESSAGE_AUTRE

    # ── Approbation admin ──
    elif cle.startswith("deja_"):
        demande_id = cle.replace("deja_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name
            await query.message.bot.send_message(
                chat_id=demande["user_id"],
                text="🎬 *Bonne nouvelle, ce contenu est déjà disponible sur notre site !*\n\n"
                     "Merci quand même pour ta contribution 😊",
                parse_mode="Markdown"
            )
            await query.edit_message_text(
                f"📺 *Déjà en ligne — traité par {admin_nom}*\n\n"
                f"👤 {demande['user_name']}\n"
                f"📋 {demande.get('titre', demande.get('lien', '?'))}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Cette demande a déjà été traitée.")

    elif cle.startswith("accept_"):
        demande_id = cle.replace("accept_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name
            await query.message.bot.send_message(
                chat_id=demande["user_id"],
                text=f"✅ *Bonne nouvelle !*\n\nTa demande a été *acceptée* par notre équipe 🎉\n\n"
                     f"Merci pour ta contribution ! 😊",
                parse_mode="Markdown"
            )
            await query.edit_message_text(
                f"✅ *Accepté par {admin_nom}*\n\n"
                f"👤 {demande['user_name']}\n"
                f"📋 {demande.get('titre', demande.get('lien', '?'))}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Cette demande a déjà été traitée.")

    elif cle.startswith("refuse_"):
        demande_id = cle.replace("refuse_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name
            await query.message.bot.send_message(
                chat_id=demande["user_id"],
                text=f"❌ *Demande refusée*\n\nNous n'avons pas pu donner suite à ta demande cette fois-ci.\n\n"
                     f"N'hésite pas à réessayer ! 😊",
                parse_mode="Markdown"
            )
            await query.edit_message_text(
                f"❌ *Refusé par {admin_nom}*\n\n"
                f"👤 {demande['user_name']}\n"
                f"📋 {demande.get('titre', demande.get('lien', '?'))}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Cette demande a déjà été traitée.")

# =============================================
# Réponses aux étapes de conversation
# =============================================

# ── Ajout film/série ──
async def handle_ajout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salut = get_salutation()
    titre = update.message.text.strip()
    user = update.message.from_user
    nom = f"{user.first_name or ''} (@{user.username or 'sans pseudo'})"
    demande_id = f"{user.id}_{int(datetime.now().timestamp())}"

    resultats = recherche_tmdb(titre)

    demandes_en_attente[demande_id] = {
        "user_id": user.id,
        "user_name": nom,
        "titre": titre
    }

    if not resultats:
        await update.message.reply_text(
            f"⏳ *Demande d'ajout enregistrée !*\n\n"
            f"🎬 Titre : *{titre}*\n\n"
            f"Ta demande est *en attente de validation*.\n"
            f"Tu recevras une réponse dès que possible ! 😊\n\n"
            f"_{salut}_",
            parse_mode="Markdown",
            reply_markup=build_retour_menu_keyboard()
        )
    else:
        tmdb_boutons = []
        for r in resultats:
            label = f"{r['emoji']} {r['nom']} ({r['annee']}) — {r['type']}"
            tmdb_boutons.append([InlineKeyboardButton(label, url=r['url'])])
        tmdb_boutons.append([InlineKeyboardButton("🔁 Faire une autre demande", callback_data="menu_retour")])

        await update.message.reply_text(
            f"⏳ *Demande d'ajout enregistrée !*\n\n"
            f"🎬 Titre : *{titre}*\n\n"
            f"Ta demande est *en attente de validation*.\n"
            f"Voici les résultats TMDB correspondants 👇\n\n"
            f"_{salut}_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(tmdb_boutons)
        )

    for admin_id in ADMIN_IDS:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"🔔 *Nouvelle demande d'ajout !*\n\n"
                 f"👤 De : {nom}\n"
                 f"🎬 Titre : {titre}\n\n"
                 f"Que veux-tu faire ?",
            parse_mode="Markdown",
            reply_markup=build_approbation_keyboard(demande_id)
        )

    return ConversationHandler.END

# ── Signalement lien inactif ──
async def handle_signalement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salut = get_salutation()
    lien = update.message.text.strip()
    user = update.message.from_user
    nom = f"{user.first_name or ''} (@{user.username or 'sans pseudo'})"
    demande_id = f"{user.id}_{int(datetime.now().timestamp())}"

    demandes_en_attente[demande_id] = {
        "user_id": user.id,
        "user_name": nom,
        "lien": lien
    }

    await update.message.reply_text(
        f"✅ *Signalement enregistré, merci !*\n\n"
        f"🔗 {lien}\n\n"
        f"Notre équipe va vérifier ça dès que possible ! 😊\n\n"
        f"_{salut}_",
        parse_mode="Markdown",
        reply_markup=build_retour_menu_keyboard()
    )

    for admin_id in ADMIN_IDS:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"⚠️ *Lien inactif signalé !*\n\n"
                 f"👤 De : {nom}\n"
                 f"🔗 Lien : {lien}",
            parse_mode="Markdown"
        )

    return ConversationHandler.END

# ── Recherche TMDB ──
async def handle_recherche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salut = get_salutation()
    titre = update.message.text.strip()
    resultats = recherche_tmdb(titre)

    if not resultats:
        await update.message.reply_text(
            f"🎬 *{titre}*\n\n"
            f"Aucun résultat trouvé sur TMDB.\n\n"
            f"_{salut}_",
            parse_mode="Markdown",
            reply_markup=build_retour_menu_keyboard()
        )
    elif len(resultats) == 1:
        r = resultats[0]
        await update.message.reply_text(
            f"{r['emoji']} *{r['nom']}* ({r['annee']}) — {r['type']}\n\n"
            f"_{salut}_",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Voir sur TMDB", url=r['url'])],
                [InlineKeyboardButton("🔍 Chercher la date Blu-Ray", url=f"https://www.google.com/search?q={quote(r['nom'] + ' sortie Blu-Ray date')}")],
                [InlineKeyboardButton("🔁 Faire une autre demande", callback_data="menu_retour")],
            ]),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"🔎 *Plusieurs résultats pour \"{titre}\"*\n\n"
            f"Clique sur le bon titre 👇\n\n"
            f"_{salut}_",
            reply_markup=build_tmdb_keyboard(resultats),
            parse_mode="Markdown"
        )

    return ConversationHandler.END

# ── Autre problème ──
async def handle_autre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salut = get_salutation()
    message = update.message.text.strip()
    user = update.message.from_user
    nom = f"{user.first_name or ''} (@{user.username or 'sans pseudo'})"

    await update.message.reply_text(
        f"📩 *Message bien reçu, merci !*\n\n"
        f"Notre équipe va traiter ta demande dès que possible ! 😊\n\n"
        f"_{salut}_",
        parse_mode="Markdown",
        reply_markup=build_retour_menu_keyboard()
    )

    for admin_id in ADMIN_IDS:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"📩 *Nouveau message !*\n\n"
                 f"👤 De : {nom}\n"
                 f"💬 Message : {message}",
            parse_mode="Markdown"
        )

    return ConversationHandler.END

# =============================================
# Annulation
# =============================================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Action annulée.\n\nComment puis-je t'aider ? 👇",
        reply_markup=build_menu_keyboard()
    )
    return ConversationHandler.END

# =============================================
# Lancement
# =============================================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(bouton_callback)
        ],
        states={
            ATTENTE_TITRE_AJOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ajout)],
            ATTENTE_LIEN_SIGNALEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_signalement)],
            ATTENTE_TITRE_RECHERCHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_recherche)],
            ATTENTE_MESSAGE_AUTRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_autre)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    app.add_handler(conv_handler)

    print("🤖 Bot démarré ! Appuie sur Ctrl+C pour arrêter.")
    app.run_polling(drop_pending_updates=True)
