import logging
from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
)

from config import config
from bot.handlers.common_handler import start_command, help_command, error_handler
from bot.handlers.photo_handler import handle_photo_upload, handle_photo_callback
from bot.handlers.withdrawal_handler import withdrawal_conv_handler
from bot.handlers.inventory_handler import (
    show_inventory, inventory_callback, show_history, set_stock_conv_handler, export_excel_handler
)
from bot.handlers.edit_handler import edit_conv_handler
from bot.handlers.admin_handler import reset_db_conv_handler

logger = logging.getLogger(__name__)

async def setup_bot_commands(application):
    """Configura el botón azul de Menú y la lista desplegable de comandos en Telegram."""
    commands = [
        BotCommand("iniciar", "Iniciar el bot y ver bienvenida."),
        BotCommand("inventario", "Consultar estado actual del inventario."),
        BotCommand("retiro", "Registrar salida o descuento de mercadería."),
        BotCommand("editar", "Editar manualmente la producción de una fecha."),
        BotCommand("historial", "Ver producción reciente de los últimos días."),
        BotCommand("excel", "Generar reporte excel."),
        BotCommand("ajustar_stock", "Establecer o ajustar el inventario base."),
        BotCommand("ayuda", "Ayuda y guía de uso detallada."),
        BotCommand("cancelar", "Cancelar la operación actual."),
    ]
    try:
        # Registrar lista de comandos por defecto
        await application.bot.set_my_commands(commands)
        logger.info("✅ Botón azul de Menú y desplegable de comandos de Telegram configurados exitosamente.")
    except Exception as e:
        logger.error(f"❌ No se pudo establecer el menú de comandos en Telegram: {e}", exc_info=True)

def create_telegram_application():
    """Construye y devuelve la aplicación del bot de Telegram con todos sus handlers."""
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN no está definido en las variables de entorno.")

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).post_init(setup_bot_commands).build()

    # Registros de Conversaciones (tienen prioridad alta)
    app.add_handler(reset_db_conv_handler)
    app.add_handler(withdrawal_conv_handler)
    app.add_handler(set_stock_conv_handler)
    app.add_handler(edit_conv_handler)

    # Registro de Comandos Estándar (soporta nombres en español y alias tradicionales)
    app.add_handler(CommandHandler(["iniciar", "start"], start_command))
    app.add_handler(CommandHandler(["ayuda", "help"], help_command))
    app.add_handler(CommandHandler("inventario", show_inventory))
    app.add_handler(CommandHandler("historial", show_history))
    app.add_handler(CommandHandler(["excel", "reporte"], export_excel_handler))

    # Registro de Recepción de Fotos de Pizarra
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_upload))

    # Registro de Callbacks Inline para confirmación de foto e inventario
    app.add_handler(CallbackQueryHandler(handle_photo_callback, pattern="^(confirm_photo_|cancel_photo_)"))
    app.add_handler(CallbackQueryHandler(inventory_callback, pattern="^(refresh_inventory|view_history|download_excel)"))

    # Manejador Global de Errores
    app.add_error_handler(error_handler)

    return app
