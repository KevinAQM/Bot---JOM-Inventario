import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.middlewares import restricted_access

logger = logging.getLogger(__name__)

@restricted_access
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start: Mensaje de bienvenida e instrucciones principales."""
    user_name = update.effective_user.first_name if update.effective_user else "Usuario"
    
    welcome_text = (
        f"👋 ¡Hola, *{user_name}*! Bienvenido al *Bot de Control de Inventario y Producción*.\n\n"
        f"🤖 *¿Qué puedo hacer por ti?*\n\n"
        f"📸 *1. Registro por Foto de Pizarra*\n"
        f"Simplemente *envíame una foto* de la pizarra física de producción. Usaré Inteligencia Artificial de visión (Gemini) "
        f"para extraer automáticamente los datos diarios, evitar duplicados y actualizar el inventario.\n\n"
        f"📦 *2. Consulta de Inventario*\n"
        f"Usa `/inventario` para ver el stock neto consolidado disponible en tiempo real.\n\n"
        f"➖ *3. Retiro Manual de Mercadería*\n"
        f"Usa `/retiro` para registrar salidas o descuentos manuales de productos.\n\n"
        f"⚙️ *4. Establecer Inventario Inicial*\n"
        f"Usa `/set_stock` para ajustar o cargar el stock físico inicial base.\n\n"
        f"❓ Usa `/help` en cualquier momento si necesitas ayuda detallada."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

@restricted_access
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help: Guía de uso detallada en español."""
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
        f"📋 *Lista de Comandos Disponibles:*\n"
        f"• `/inventario` - Ver el resumen de existencias actuales.\n"
        f"• `/retiro` - Registrar una salida de mercadería.\n"
        f"• `/set_stock` - Ajustar inventario inicial base.\n"
        f"• `/historial` - Ver la producción registrada de los últimos días."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Manejador global de excepciones no capturadas."""
    logger.error(f"Excepción capturada en Telegram handler: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Ocurrió un error inesperado al procesar tu solicitud. Por favor intenta nuevamente más tarde."
        )
