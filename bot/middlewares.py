import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import config

logger = logging.getLogger(__name__)

def restricted_access(func):
    """
    Decorador middleware para restringir el uso del bot únicamente a los IDs de Telegram autorizados.
    Si la lista ALLOWED_TELEGRAM_USERS está configurada, bloquea usuarios no autorizados.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        allowed = config.ALLOWED_TELEGRAM_USERS

        if allowed and user_id not in allowed:
            logger.warning(f"Intento de acceso denegado para usuario no autorizado: ID={user_id}, Username=@{user.username}")
            message_text = (
                f"⚠️ *Acceso Restringido*\n\n"
                f"Hola, {user.first_name}. No tienes autorización para utilizar este bot de producción.\n\n"
                f"Tu ID de Telegram es: `{user_id}`\n"
                f"Solicita al administrador que añada tu ID a la variable `ALLOWED_TELEGRAM_USERS`."
            )
            if update.message:
                await update.message.reply_text(message_text, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.answer("⚠️ Acceso Denegado.", show_alert=True)
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
