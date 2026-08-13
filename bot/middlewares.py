import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import config
from utils.helpers import escape_markdown

logger = logging.getLogger(__name__)

def restricted_access(func):
    """
    Decorador middleware para restringir el uso del bot únicamente a los IDs de Telegram autorizados.
    Permite el acceso si el usuario está en ALLOWED_TELEGRAM_USERS o ALLOWED_TELEGRAM_ADMIN.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        allowed_users = config.ALLOWED_TELEGRAM_USERS
        allowed_admins = config.ALLOWED_TELEGRAM_ADMIN

        # Si hay restricción configurada y el usuario no está en ninguna lista, se bloquea
        if (allowed_users or allowed_admins) and (user_id not in allowed_users and user_id not in allowed_admins):
            safe_name = escape_markdown(user.first_name)
            logger.warning(f"Intento de acceso denegado para usuario no autorizado: ID={user_id}, Username=@{user.username}")
            message_text = (
                f"⚠️ *Acceso Restringido*\n\n"
                f"Hola, {safe_name}. No tienes autorización para utilizar este bot de producción.\n\n"
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


def admin_only(func):
    """
    Decorador middleware exclusivo para funciones de administración (como /reset_db).
    Restringe el uso únicamente a los IDs presentes en ALLOWED_TELEGRAM_ADMIN.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        admins = config.ALLOWED_TELEGRAM_ADMIN

        if admins and user_id not in admins:
            safe_name = escape_markdown(user.first_name)
            logger.warning(f"Intento de acceso de administrador denegado: ID={user_id}, Username=@{user.username}")
            message_text = (
                f"⛔ *Acceso de Administrador Requerido*\n\n"
                f"Hola, {safe_name}. El comando solicitado es exclusivo para administradores del sistema.\n\n"
                f"Tu ID de Telegram es: `{user_id}`"
            )
            if update.message:
                await update.message.reply_text(message_text, parse_mode="Markdown")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Acceso denegado: Requiere permisos de administrador.", show_alert=True)
            return

        return await func(update, context, *args, **kwargs)

    return wrapper

