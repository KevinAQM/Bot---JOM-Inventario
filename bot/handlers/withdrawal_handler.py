import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

from bot.middlewares import restricted_access
from database.connection import get_db
from database.crud import record_withdrawal, get_consolidated_inventory
from database.models import PRODUCT_CATALOG

logger = logging.getLogger(__name__)

# Estados de la conversación de retiro
SELECT_PRODUCT, ENTER_QUANTITY, ENTER_REASON, CONFIRM_WITHDRAWAL = range(4)

@restricted_access
async def start_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Punto de entrada del comando /retiro."""
    keyboard = [
        [
            InlineKeyboardButton("🔴 Rojo (R)", callback_data="prod_R"),
            InlineKeyboardButton("🟢 Verde (V)", callback_data="prod_V")
        ],
        [
            InlineKeyboardButton("🟡 Amarillo (A)", callback_data="prod_A"),
            InlineKeyboardButton("⚪ No Color (NC)", callback_data="prod_NC")
        ],
        [
            InlineKeyboardButton("⬛ Negro (N)", callback_data="prod_N"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_withdrawal")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🛒 *RETIRO O SALIDA DE MERCADERÍA*\n\n"
        "Por favor, selecciona el **producto** que deseas descontar del inventario:"
    )
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    return SELECT_PRODUCT

async def product_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback cuando el usuario selecciona un producto."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "cancel_withdrawal":
        await query.edit_message_text("❌ *Operación de retiro cancelada.*", parse_mode="Markdown")
        return ConversationHandler.END

    product_code = data.replace("prod_", "")
    context.user_data["withdrawal_product"] = product_code
    cat_info = PRODUCT_CATALOG.get(product_code, {"name": product_code, "emoji": "📦"})
    
    await query.edit_message_text(
        f"Has seleccionado: {cat_info['emoji']} *{cat_info['name']} ({product_code})*\n\n"
        f"✍️ Ahora, **escribe la cantidad** de unidades a retirar (ejemplo: `15`):",
        parse_mode="Markdown"
    )
    return ENTER_QUANTITY

async def quantity_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el ingreso del número de unidades a descontar."""
    text = update.message.text.strip() if update.message else ""
    
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text(
            "⚠️ *Cantidad inválida.* Por favor ingresa un número entero positivo (ejemplo: `12`):",
            parse_mode="Markdown"
        )
        return ENTER_QUANTITY

    qty = int(text)
    context.user_data["withdrawal_quantity"] = qty
    product_code = context.user_data.get("withdrawal_product", "R")
    cat_info = PRODUCT_CATALOG.get(product_code, {"name": product_code, "emoji": "📦"})

    keyboard = [[InlineKeyboardButton("⏩ Omitir Nota / Sin Cliente", callback_data="skip_reason")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Cantidad registrada: `{qty}` unidades de {cat_info['emoji']} *{cat_info['name']}*\n\n"
        f"📝 Opcionalmente, escribe el **nombre del cliente o motivo** del retiro (ejemplo: _Venta a Don Carlos_):\n"
        f"O presiona el botón de abajo para omitir.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return ENTER_REASON

async def reason_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda la nota o cliente ingresado mediante texto o callback."""
    reason = "Salida manual"
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.data == "skip_reason":
            reason = "Retiro manual estándar"
    elif update.message:
        reason = update.message.text.strip()

    context.user_data["withdrawal_reason"] = reason
    
    # Presentar confirmación final
    product_code = context.user_data.get("withdrawal_product", "R")
    quantity = context.user_data.get("withdrawal_quantity", 0)
    cat_info = PRODUCT_CATALOG.get(product_code, {"name": product_code, "emoji": "📦"})

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmar Retiro", callback_data="confirm_final_withdrawal"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_withdrawal")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    summary_text = (
        f"🔍 *CONFIRMACIÓN DE RETIRO DE STOCK*\n\n"
        f"• **Producto:** {cat_info['emoji']} {cat_info['name']} (`{product_code}`)\n"
        f"• **Cantidad a Descontar:** `{quantity}` unidades\n"
        f"• **Cliente / Motivo:** _{reason}_\n\n"
        f"¿Estás seguro de descontar esta cantidad del inventario?"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(summary_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(summary_text, reply_markup=reply_markup, parse_mode="Markdown")

    return CONFIRM_WITHDRAWAL

async def confirm_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ejecuta el retiro en la base de datos tras confirmación."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_withdrawal":
        await query.edit_message_text("❌ *Operación de retiro cancelada.*", parse_mode="Markdown")
        return ConversationHandler.END

    product_code = context.user_data.get("withdrawal_product")
    quantity = context.user_data.get("withdrawal_quantity", 0)
    reason = context.user_data.get("withdrawal_reason", "Manual")
    cat_info = PRODUCT_CATALOG.get(product_code, {"name": product_code, "emoji": "📦"})

    try:
        async with get_db() as session:
            # Verificar stock disponible antes de descontar
            consolidated = await get_consolidated_inventory(session)
            current_stock = consolidated.get(product_code, {}).get("current_stock", 0)

            await record_withdrawal(
                session=session,
                product_code=product_code,
                quantity=quantity,
                withdrawal_type="MANUAL",
                customer_or_reason=reason
            )
            # Re-consultar stock actualizado
            consolidated = await get_consolidated_inventory(session)

        new_stock = consolidated.get(product_code, {}).get("current_stock", 0)

        # Advertencia si el stock quedó negativo
        warning = ""
        if new_stock < 0:
            warning = (
                f"\n\n⚠️ *ADVERTENCIA:* El stock de {cat_info['emoji']} *{cat_info['name']}* "
                f"quedó en *negativo* (`{new_stock}` unidades). "
                f"Verifica que el inventario inicial y la producción estén actualizados."
            )

        result_text = (
            f"✅ *¡RETIRO REGISTRADO CORRECTAMENTE!*\n\n"
            f"Se han descontado `{quantity}` unidades de {cat_info['emoji']} *{cat_info['name']}*.\n"
            f"📦 *Nuevo Stock Disponible:* `{new_stock}` unidades."
            f"{warning}"
        )
        await query.edit_message_text(result_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error al registrar retiro: {e}", exc_info=True)
        await query.edit_message_text(f"❌ Error al guardar el retiro en la base de datos: `{str(e)}`")

    return ConversationHandler.END

async def cancel_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la conversación de retiro."""
    if update.message:
        await update.message.reply_text("❌ *Operación de retiro cancelada.*", parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text("❌ *Operación de retiro cancelada.*", parse_mode="Markdown")
    return ConversationHandler.END

# Definición del ConversationHandler para exportar
withdrawal_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("retiro", start_withdrawal)],
    states={
        SELECT_PRODUCT: [CallbackQueryHandler(product_selected, pattern="^(prod_|cancel_withdrawal)")],
        ENTER_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_entered)],
        ENTER_REASON: [
            CallbackQueryHandler(reason_entered, pattern="^skip_reason$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, reason_entered)
        ],
        CONFIRM_WITHDRAWAL: [CallbackQueryHandler(confirm_withdrawal, pattern="^(confirm_final_withdrawal|cancel_withdrawal)$")]
    },
    fallbacks=[CommandHandler("cancelar", cancel_withdrawal)]
)
