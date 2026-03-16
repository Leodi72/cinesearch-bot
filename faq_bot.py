import logging
import os
import requests
from datetime import datetime, timezone
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# =============================================
# 🔧 CONFIGURATION
# =============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TMDB_API_KEY = "TMDB_API_KEY"
ADMIN_IDS = [5140415021]  # Ajoute le Chat ID de ton duo : [5140415021, CHAT_ID_DUO]

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Stockage des demandes en attente
demandes_en_attente = {}

# =============================================
# 🕐 Salutation selon l'heure (heure française fixe)
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
def build_bluray_keyboard(titre: str):
    query = quote(f"{titre} sortie Blu-Ray date")
    google_url = f"https://www.google.com/search?q={query}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Chercher sur Google", url=google_url)],
    ])

def build_tmdb_keyboard(resultats: list):
    boutons = []
    for r in resultats:
        label = f"{r['emoji']} {r['nom']} ({r['annee']}) — {r['type']}"
        boutons.append([InlineKeyboardButton(label, url=r['url'])])
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
# /start
# =============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenue sur CineSearch !\n\n"
        "Envoie-moi un titre de film ou de série et je m'occupe du reste ! 😊"
    )

# =============================================
# Gestion des boutons inline
# =============================================
async def bouton_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cle = query.data

    if cle.startswith("deja_"):
        demande_id = cle.replace("deja_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name
            await context.bot.send_message(
                chat_id=demande["user_id"],
                text="🎬 *Bonne nouvelle, ce contenu est déjà disponible sur notre site !*\n\n"
                     "Merci quand même pour ta contribution 😊",
                parse_mode="Markdown"
            )
            await query.edit_message_text(
                f"📺 *Déjà en ligne — traité par {admin_nom}*\n\n"
                f"👤 {demande['user_name']}\n"
                f"🔗 {demande['lien']}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Cette demande a déjà été traitée.")

    elif cle.startswith("accept_"):
        demande_id = cle.replace("accept_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name
            await context.bot.send_message(
                chat_id=demande["user_id"],
                text=f"✅ *Bonne nouvelle !*\n\nTon lien a été *accepté* par notre équipe 🎉\n\n"
                     f"🔗 {demande['lien']}\n\n"
                     f"Merci pour ta contribution ! 😊",
                parse_mode="Markdown"
            )
            await query.edit_message_text(
                f"✅ *Accepté par {admin_nom}*\n\n"
                f"👤 {demande['user_name']}\n"
                f"🔗 {demande['lien']}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Cette demande a déjà été traitée.")

    elif cle.startswith("refuse_"):
        demande_id = cle.replace("refuse_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name
            await context.bot.send_message(
                chat_id=demande["user_id"],
                text=f"❌ *Lien refusé*\n\nNous n'avons pas pu ajouter ton lien cette fois-ci.\n\n"
                     f"🔗 {demande['lien']}\n\n"
                     f"N'hésite pas à réessayer avec un autre lien ! 😊",
                parse_mode="Markdown"
            )
            await query.edit_message_text(
                f"❌ *Refusé par {admin_nom}*\n\n"
                f"👤 {demande['user_name']}\n"
                f"🔗 {demande['lien']}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Cette demande a déjà été traitée.")

# =============================================
# Gestion des messages texte — détection auto
# =============================================
async def message_texte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salut = get_salutation()
    texte = update.message.text.strip()
    user = update.message.from_user
    nom = f"{user.first_name or ''} (@{user.username or 'sans pseudo'})"

    # ── Détection lien ──
    if texte.startswith("http://") or texte.startswith("https://"):
        demande_id = f"{user.id}_{int(datetime.now().timestamp())}"
        demandes_en_attente[demande_id] = {
            "user_id": user.id,
            "user_name": nom,
            "lien": texte
        }
        await update.message.reply_text(
            f"⏳ *Lien reçu, merci !*\n\n"
            f"🔗 {texte}\n\n"
            f"Ton lien est *en attente de validation* par notre équipe.\n"
            f"Tu recevras une réponse dès que possible ! 😊\n\n"
            f"_{salut}_",
            parse_mode="Markdown"
        )
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔔 *Nouvelle demande d'ajout !*\n\n"
                     f"👤 De : {nom}\n"
                     f"🔗 Lien : {texte}\n\n"
                     f"Que veux-tu faire ?",
                parse_mode="Markdown",
                reply_markup=build_approbation_keyboard(demande_id)
            )

    # ── Détection titre de film ──
    else:
        resultats = recherche_tmdb(texte)

        if not resultats:
            await update.message.reply_text(
                f"🎬 *{texte}*\n\n"
                f"Aucun résultat trouvé sur TMDB.\n"
                f"Clique ci-dessous pour chercher la date de sortie Blu-Ray 👇\n\n"
                f"_{salut}_",
                reply_markup=build_bluray_keyboard(texte),
                parse_mode="Markdown"
            )
        elif len(resultats) == 1:
            r = resultats[0]
            await update.message.reply_text(
                f"{r['emoji']} *{r['nom']}* ({r['annee']}) — {r['type']}\n\n"
                f"Clique ci-dessous pour voir la fiche TMDB 👇\n\n"
                f"_{salut}_",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Voir sur TMDB", url=r['url'])],
                    [InlineKeyboardButton("🔍 Chercher la date Blu-Ray", url=f"https://www.google.com/search?q={quote(r['nom'] + ' sortie Blu-Ray date')}")],
                ]),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"🔎 *Plusieurs résultats pour \"{texte}\"*\n\n"
                f"Clique sur le bon titre 👇\n\n"
                f"_{salut}_",
                reply_markup=build_tmdb_keyboard(resultats),
                parse_mode="Markdown"
            )

# =============================================
# Lancement
# =============================================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(bouton_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_texte))

    print("🤖 Bot démarré ! Appuie sur Ctrl+C pour arrêter.")
    app.run_polling(drop_pending_updates=True)
