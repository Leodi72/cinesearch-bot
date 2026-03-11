import logging
from datetime import datetime, timezone
from urllib.parse import quote
from timezonefinder import TimezoneFinder
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# =============================================
# 🔧 CONFIGURATION
# =============================================
import os
BOT_TOKEN = os.environ.get("8467102753:AAE9wnydWFEA29H9fGmzmEgnreWd0Q-C8Ws")
ADMIN_IDS = [5140415021]  # Ajoute le Chat ID de ton duo ici quand tu l'as : [5140415021, CHAT_ID_DUO]

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Stockage temporaire des demandes en attente
# Format : { "user_id:lien_hash" : { "user_id": ..., "user_name": ..., "lien": ... } }
demandes_en_attente = {}

# =============================================
# 🕐 Salutation selon l'heure
# =============================================
def get_salutation(offset_hours: float = 1) -> str:
    heure_locale = (datetime.now(timezone.utc).hour + offset_hours) % 24
    if 6 <= heure_locale < 18:
        return "🌞 Merci et bonne journée !"
    else:
        return "🌙 Merci et bonne soirée !"

def salutation_from_context(context: ContextTypes.DEFAULT_TYPE) -> str:
    offset = context.user_data.get("tz_offset", 1)
    return get_salutation(offset)

# =============================================
# Claviers
# =============================================
def build_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Quel film / série veux-tu ?", callback_data="q1")],
        [InlineKeyboardButton("📅 Quand sortira ce film / série ?", callback_data="q2")],
        [InlineKeyboardButton("➕ Ajouter un film / série", callback_data="q3")],
    ])

def build_retour_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Retour au menu", callback_data="menu")]
    ])

def build_location_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 Partager ma localisation", callback_data="share_loc")],
        [InlineKeyboardButton("🇫🇷 Non merci, continuer en heure française", callback_data="tz_france")],
    ])

def build_bluray_keyboard(titre: str):
    query = quote(f"{titre} sortie Blu-Ray date")
    google_url = f"https://www.google.com/search?q={query}"
    justwatch_url = f"https://www.justwatch.com/fr/recherche?q={quote(titre)}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Chercher sur Google", url=google_url)],
        [InlineKeyboardButton("🎬 Chercher sur JustWatch", url=justwatch_url)],
        [InlineKeyboardButton("⬅️ Retour au menu", callback_data="menu")],
    ])

def build_loc_request_keyboard():
    bouton = KeyboardButton("📍 Envoyer ma localisation", request_location=True)
    return ReplyKeyboardMarkup([[bouton]], resize_keyboard=True, one_time_keyboard=True)

def build_approbation_keyboard(demande_id: str):
    return InlineKeyboardMarkup([
        [
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
        "📍 Veux-tu partager ta localisation pour que je détecte ton fuseau horaire automatiquement ?",
        reply_markup=build_location_keyboard()
    )

# =============================================
# Gestion des boutons inline
# =============================================
async def bouton_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cle = query.data

    if cle == "share_loc":
        await query.edit_message_text(
            "📍 Appuie sur le bouton ci-dessous pour partager ta position :"
        )
        await query.message.reply_text(
            "👇 Appuie sur le bouton pour partager ta localisation :",
            reply_markup=build_loc_request_keyboard()
        )

    elif cle == "tz_france":
        context.user_data["tz_offset"] = 1
        await query.edit_message_text(
            "🇫🇷 Heure française sélectionnée !\n\n"
            "👋 Comment puis-je t'aider ?",
            reply_markup=build_main_keyboard()
        )

    elif cle == "q1":
        salut = salutation_from_context(context)
        await query.edit_message_text(
            "🎬 *Quel film / série veux-tu ?*\n\n"
            "Voici le lien pour nous permettre de le trouver :\n"
            "👉 [The Movie Database (TMDB)](https://www.themoviedb.org/)\n\n"
            "Recherche ton film ou ta série, puis envoie-nous le lien de la page correspondante !\n\n"
            f"_{salut}_ 😊",
            reply_markup=build_retour_keyboard(),
            parse_mode="Markdown"
        )

    elif cle == "q2":
        context.user_data["attente_titre"] = True
        await query.edit_message_text(
            "📅 *Quand sortira ce film / série en Blu-Ray ?*\n\n"
            "Envoie-moi le *titre du film ou de la série* 🎬",
            reply_markup=build_retour_keyboard(),
            parse_mode="Markdown"
        )

    elif cle == "q3":
        context.user_data["attente_lien"] = True
        await query.edit_message_text(
            "➕ *Ajouter un film / série*\n\n"
            "Envoie-moi le lien que tu as trouvé sur internet et on s'occupe du reste ! 🙌",
            reply_markup=build_retour_keyboard(),
            parse_mode="Markdown"
        )

    elif cle == "menu":
        context.user_data.pop("attente_titre", None)
        context.user_data.pop("attente_lien", None)
        await query.edit_message_text(
            "👋 Comment puis-je t'aider ?",
            reply_markup=build_main_keyboard()
        )

    # ── Accepter un lien ──
    elif cle.startswith("accept_"):
        demande_id = cle.replace("accept_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name

            # Notifier l'utilisateur
            await context.bot.send_message(
                chat_id=demande["user_id"],
                text=f"✅ *Bonne nouvelle !*\n\nTon lien a été *accepté* par notre équipe 🎉\n\n"
                     f"🔗 {demande['lien']}\n\n"
                     f"Merci pour ta contribution ! 😊",
                parse_mode="Markdown",
                reply_markup=build_main_keyboard()
            )

            # Mettre à jour le message admin
            await query.edit_message_text(
                f"✅ *Lien accepté par {admin_nom}*\n\n"
                f"👤 {demande['user_name']}\n"
                f"🔗 {demande['lien']}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Cette demande a déjà été traitée.")

    # ── Refuser un lien ──
    elif cle.startswith("refuse_"):
        demande_id = cle.replace("refuse_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name

            # Notifier l'utilisateur
            await context.bot.send_message(
                chat_id=demande["user_id"],
                text=f"❌ *Lien refusé*\n\nNous n'avons pas pu ajouter ton lien cette fois-ci.\n\n"
                     f"🔗 {demande['lien']}\n\n"
                     f"N'hésite pas à réessayer avec un autre lien ! 😊",
                parse_mode="Markdown",
                reply_markup=build_main_keyboard()
            )

            # Mettre à jour le message admin
            await query.edit_message_text(
                f"❌ *Lien refusé par {admin_nom}*\n\n"
                f"👤 {demande['user_name']}\n"
                f"🔗 {demande['lien']}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("⚠️ Cette demande a déjà été traitée.")

# =============================================
# Gestion de la localisation
# =============================================
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    try:
        tf = TimezoneFinder()
        tz_name = tf.timezone_at(lng=loc.longitude, lat=loc.latitude)
        tz = pytz.timezone(tz_name)
        offset = tz.utcoffset(datetime.now()).total_seconds() / 3600
        context.user_data["tz_offset"] = offset
        pays = tz_name.split("/")[-1].replace("_", " ")
        await update.message.reply_text(
            f"✅ Localisation détectée : *{pays}*\n\n"
            f"👋 Comment puis-je t'aider ?",
            reply_markup=build_main_keyboard(),
            parse_mode="Markdown"
        )
    except Exception:
        context.user_data["tz_offset"] = 1
        await update.message.reply_text(
            "✅ Localisation reçue !\n\n👋 Comment puis-je t'aider ?",
            reply_markup=build_main_keyboard()
        )

# =============================================
# Gestion des messages texte
# =============================================
async def message_texte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salut = salutation_from_context(context)

    if context.user_data.get("attente_titre"):
        context.user_data.pop("attente_titre")
        titre = update.message.text.strip()
        await update.message.reply_text(
            f"📅 *Sortie Blu-Ray de '{titre}' :*\n\n"
            f"Clique sur un des boutons ci-dessous pour trouver la date de sortie 👇\n\n"
            f"_{salut}_ 😊",
            reply_markup=build_bluray_keyboard(titre),
            parse_mode="Markdown"
        )
        return

    if context.user_data.get("attente_lien"):
        context.user_data.pop("attente_lien")
        lien = update.message.text.strip()
        user = update.message.from_user
        nom = f"{user.first_name or ''} (@{user.username or 'sans pseudo'})"

        # Créer un ID unique pour cette demande
        demande_id = f"{user.id}_{int(datetime.now().timestamp())}"
        demandes_en_attente[demande_id] = {
            "user_id": user.id,
            "user_name": nom,
            "lien": lien
        }

        # Réponse à l'utilisateur
        await update.message.reply_text(
            f"⏳ *Lien reçu, merci !*\n\n"
            f"🔗 {lien}\n\n"
            f"Ton lien est *en attente de validation* par notre équipe.\n"
            f"Tu recevras une réponse dès que possible ! 😊\n\n"
            f"_{salut}_ 😊",
            reply_markup=build_main_keyboard(),
            parse_mode="Markdown"
        )

        # Envoyer la demande à tous les admins
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔔 *Nouvelle demande d'ajout !*\n\n"
                     f"👤 De : {nom}\n"
                     f"🔗 Lien : {lien}\n\n"
                     f"Que veux-tu faire ?",
                parse_mode="Markdown",
                reply_markup=build_approbation_keyboard(demande_id)
            )
        return

    await update.message.reply_text(
        "Je ne comprends pas, utilise le menu ci-dessous 👇",
        reply_markup=build_main_keyboard()
    )

# =============================================
# Lancement
# =============================================
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(bouton_callback))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_texte))

    print("🤖 Bot démarré ! Appuie sur Ctrl+C pour arrêter.")
    app.run_polling(drop_pending_updates=True)
