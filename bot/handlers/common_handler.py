import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.middlewares import restricted_access
from utils.helpers import escape_markdown

logger = logging.getLogger(__name__)

@restricted_access
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start: Mensaje de bienvenida e instrucciones principales."""
    raw_name = update.effective_user.first_name if update.effective_user else "Usuario"
    user_name = escape_markdown(raw_name)
    
    welcome_text = (
        f"👋 ¡Hola, *{user_name}*! Bienvenido al *Bot de Control de Inventario y Producción*.\n\n"
        f"🤖 *¿Qué puedo hacer por ti?*\n\n"
        f"📸 *1. Registro por Foto de Pizarra*\n"
        f"Simplemente *envíame una foto* de la pizarra física de producción. Usaré Inteligencia Artificial de visión (Gemini) "
        f"para extraer automáticamente los datos diarios, evitar duplicados y actualizar el inventario.\n\n"
        f"📋 *2. Comandos Disponibles:*\n"
        f"• `/iniciar` - Iniciar el bot y ver bienvenida.\n"
        f"• `/inventario` - Consultar estado actual del inventario.\n"
        f"• `/retiro` - Registrar salida o descuento de mercadería.\n"
        f"• `/editar` - Editar manualmente la producción de una fecha.\n"
        f"• `/historial` - Ver producción reciente de los últimos días.\n"
        f"• `/excel` - Generar reporte excel.\n"
        f"• `/ajustar_stock` - Establecer o ajustar el inventario base.\n"
        f"• `/ayuda` - Ayuda y guía de uso detallada.\n"
        f"• `/cancelar` - Cancelar la operación actual.\n\n"
        f"❓ Usa `/ayuda` en cualquier momento si necesitas ayuda detallada."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

@restricted_access
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda: Guía de uso detallada en español."""
    help_text = (
        f"📖 *GUÍA DE USO Y COMANDOS DEL BOT*\n\n"
        f"🟢 *1. Códigos de Producto Manejados:*\n"
        f"• 🔴 *R* = Rojo\n"
        f"• 🟢 *V* = Verde\n"
        f"• 🟡 *A* = Amarillo\n"
        f"• ⚪ *NC* = No Color\n"
        f"• ⬛ *N* = Negro\n\n"
        f"📷 *2. ¿Cómo subir una foto?*\n"
        f"Toma una foto clara a la pizarra al final del día. Asegúrate de que las fechas (DD-MM) y "
        f"los códigos (ej: `R-110`, `V-94`) sean visibles. Al enviarla, el bot te mostrará una "
        f"vista previa para confirmar antes de guardar en la base de datos.\n\n"
        f"🔄 *3. Deduplicación Automática:*\n"
        f"No te preocupes si la foto contiene días anteriores de la semana (ej: de lunes a viernes). "
        f"El sistema actualiza inteligentemente las fechas existentes sin duplicar cantidades.\n\n"
        f"📋 *Lista Completa de Comandos:*\n"
        f"• `/iniciar` - Iniciar el bot y ver bienvenida.\n"
        f"• `/inventario` - Consultar estado actual del inventario.\n"
        f"• `/retiro` - Registrar salida o descuento de mercadería.\n"
        f"• `/editar` - Editar manualmente la producción de una fecha.\n"
        f"• `/historial` - Ver producción reciente de los últimos días.\n"
        f"• `/excel` - Generar reporte excel.\n"
        f"• `/ajustar_stock` - Establecer o ajustar el inventario base.\n"
        f"• `/ayuda` - Ayuda y guía de uso detallada.\n"
        f"• `/cancelar` - Cancelar la operación actual."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Manejador global de excepciones no capturadas."""
    logger.error(f"Excepción capturada en Telegram handler: {context.error}", exc_info=context.error)
    if isinstance(update, Update):
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "⚠️ Ocurrió un fallo de conexión. Intenta nuevamente.",
                    show_alert=True
                )
            except Exception:
                pass
        elif update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Ocurrió un error inesperado al procesar tu solicitud. Por favor intenta nuevamente."
                )
            except Exception:
                pass
