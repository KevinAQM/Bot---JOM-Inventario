import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
)

from config import config
from bot.middlewares import admin_only
from database.connection import get_db
from database.crud import reset_entire_database
from utils.helpers import escape_markdown

logger = logging.getLogger(__name__)

# Estados de la conversación para reset_db
WAITING_RESET_PIN, CONFIRM_RESET = range(2)
ADMIN_RESET_PASSWORD = "201209"


@admin_only
async def start_reset_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el proceso de reset de la base de datos solicitando la clave de seguridad."""
    user = update.effective_user
    safe_name = escape_markdown(user.first_name if user else "Administrador")

    logger.warning(f"Comando /reset_db iniciado por admin ID={user.id if user else 'Desconocido'}")

    msg = (
        f"🔐 *ÁREA RESTRINGIDA DE ADMINISTRACIÓN*\n\n"
        f"Hola, {safe_name}. Has solicitado el reset total de la base de datos del sistema.\n\n"
        f"⚠️ *Por favor, ingresa la clave de seguridad para continuar:*\n"
        f"_(O escribe /cancelar para salir)_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return WAITING_RESET_PIN


async def process_reset_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa e inspecciona la clave de seguridad ingresada por el administrador."""
    entered_pin = update.message.text.strip() if update.message and update.message.text else ""

    if entered_pin == ADMIN_RESET_PASSWORD:
        keyboard = [
            [InlineKeyboardButton("🔴 SÍ, RESETEAR TODO DE CERO", callback_data="confirm_reset_db")],
            [InlineKeyboardButton("🟢 CANCELAR", callback_data="cancel_reset_db")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = (
            f"✅ *CLAVE CORRECTA*\n\n"
            f"⚠️ *ADVERTENCIA DE SEGURIDAD EXTREMA*\n"
            f"Estás a punto de borrar **TODOS** los registros de producción diaria, salidas de mercadería "
            f"e historial de auditoría de fotos en la base de datos de producción.\n\n"
            f"Esta acción no se puede deshacer.\n\n"
            f"¿Estás completamente seguro de proceder?"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
        return CONFIRM_RESET
    else:
        logger.warning(f"Intento fallido de reset DB con clave incorrecta por usuario ID={update.effective_user.id}")
        msg = (
            f"❌ *CLAVE INCORRECTA*\n\n"
            f"La clave ingresada no es válida. La operación de reset de base de datos ha sido **CANCELADA** por seguridad."
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return ConversationHandler.END


async def handle_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la confirmación por botón inline para ejecutar o cancelar el reset de la BD."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "cancel_reset_db":
        await query.edit_message_text(
            "🟢 *Operación Cancelada*\n\nLa base de datos no ha sufrido ningún cambio y los datos de prueba permanecen intactos.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if data == "confirm_reset_db":
        await query.edit_message_text(
            "⏳ *Procesando reset de base de datos... Por favor espera.*",
            parse_mode="Markdown"
        )
        try:
            async with get_db() as session:
                res = await reset_entire_database(session)

            summary_msg = (
                f"✅ *BASE DE DATOS RESETEADA CON ÉXITO*\n\n"
                f"El sistema ha sido limpiado y reestablecido a cero:\n"
                f"• Registros de producción eliminados: `{res['deleted_productions']}`\n"
                f"• Salidas de mercadería eliminadas: `{res['deleted_withdrawals']}`\n"
                f"• Auditorías de fotos limpiadas: `{res['deleted_photos']}`\n"
                f"• Stock inicial: Reestablecido a `0` para todo el catálogo (R, V, A, NC, N).\n\n"
                f"🚀 *El bot está 100% limpio y listo para ser usado oficialmente en la empresa.*"
            )
            await query.edit_message_text(summary_msg, parse_mode="Markdown")
            logger.info("✅ Base de datos reseteada con éxito por comando /reset_db")
        except Exception as e:
            logger.error(f"❌ Error al ejecutar el reset de base de datos: {e}", exc_info=True)
            await query.edit_message_text(
                f"❌ *ERROR AL RESETEAR BASE DE DATOS*\n\nOcurrió un error inesperado: `{e}`",
                parse_mode="Markdown"
            )

        return ConversationHandler.END

    return ConversationHandler.END


async def cancel_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela el flujo de reset de la base de datos."""
    if update.message:
        await update.message.reply_text("🟢 Operación de reset cancelada.", parse_mode="Markdown")
    return ConversationHandler.END


# Construcción del ConversationHandler para /reset_db
reset_db_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("reset_db", start_reset_db)],
    states={
        WAITING_RESET_PIN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_reset_pin)
        ],
        CONFIRM_RESET: [
            CallbackQueryHandler(handle_reset_callback, pattern="^(confirm_reset_db|cancel_reset_db)$")
        ],
    },
    fallbacks=[CommandHandler("cancelar", cancel_reset)],
)
