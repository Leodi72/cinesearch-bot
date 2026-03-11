import logging
import os
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
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = [5140415021]  # Ajoute le Chat ID de ton duo : [5140415021, CHAT_ID_DUO]

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Stockage des demandes en attente
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
def build_bluray_keyboard(titre: str):
    query = quote(f"{titre} sortie Blu-Ray date")
    google_url = f"https://www.google.com/search?q={query}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Chercher sur Google", url=google_url)],
    ])

def build_approbation_keyboard(demande_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📺 Déjà en ligne", callback_data=f"deja_{demande_id}"),
            InlineKeyboardButton("✅ Accepter", callback_data=f"accept_{demande_id}"),
            InlineKeyboardButton("❌ Refuser", callback_data=f"refuse_{demande_id}"),
        ]
    ])

def build_loc_request_keyboard():
    bouton = KeyboardButton("📍 Envoyer ma localisation", request_location=True)
    return ReplyKeyboardMarkup([[bouton]], resize_keyboard=True, one_time_keyboard=True)

def build_location_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📍 Partager ma localisation", callback_data="share_loc")],
        [InlineKeyboardButton("🇫🇷 Non merci, continuer en heure française", callback_data="tz_france")],
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
            "👋 Envoie-moi un titre de film ou un lien et je m'occupe du reste ! 😊"
        )

    # ── Déjà en ligne ──
    elif cle.startswith("deja_"):
        demande_id = cle.replace("deja_", "")
        if demande_id in demandes_en_attente:
            demande = demandes_en_attente.pop(demande_id)
            admin_nom = query.from_user.first_name
            await context.bot.send_message(
                chat_id=demande["user_id"],
                text=f"🎬 *Bonne nouvelle, ce contenu est déjà disponible sur notre site !*\n\n"
                     f"Merci quand même pour ta contribution 😊",
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

    # ── Accepter ──
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

    # ── Refuser ──
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
            f"👋 Envoie-moi un titre de film ou un lien et je m'occupe du reste ! 😊",
            parse_mode="Markdown"
        )
    except Exception:
        context.user_data["tz_offset"] = 1
        await update.message.reply_text(
            "✅ Localisation reçue !\n\n"
            "👋 Envoie-moi un titre de film ou un lien et je m'occupe du reste ! 😊"
        )

# =============================================
# Gestion des messages texte — détection auto
# =============================================
async def message_texte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salut = salutation_from_context(context)
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
        await update.message.reply_text(
            f"🎬 *{texte}*\n\n"
            f"Clique ci-dessous pour chercher la date de sortie Blu-Ray 👇\n\n"
            f"_{salut}_",
            reply_markup=build_bluray_keyboard(texte),
            parse_mode="Markdown"
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
