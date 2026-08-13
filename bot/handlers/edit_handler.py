import logging
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

from bot.middlewares import restricted_access
from database.connection import get_db
from database.crud import get_recent_production_dates, upsert_production_records, get_consolidated_inventory
from database.models import PRODUCT_CATALOG
from utils.helpers import parse_board_date, get_product_info, escape_markdown

logger = logging.getLogger(__name__)

# Estados de la conversación de edición
EDIT_SELECT_DATE, EDIT_SELECT_PRODUCT, EDIT_INPUT_QTY = range(3)


@restricted_access
async def start_edit_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Inicia el flujo interactivo de edición/corrección de producción manual.
    Comando: /editar o /editar_dia
    """
    context.user_data.clear()

    # Consultar fechas recientes en la base de datos
    try:
        async with get_db() as session:
            recent_dates = await get_recent_production_dates(session, limit=7)
    except Exception as e:
        logger.error(f"Error al obtener fechas recientes para edición: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error al consultar la base de datos: `{escape_markdown(str(e))}`", parse_mode="Markdown")
        return ConversationHandler.END

    keyboard = []
    # Generar botones para cada fecha reciente
    for d in recent_dates:
        d_str = d.strftime("%d-%m-%Y")
        keyboard.append([InlineKeyboardButton(f"📅 {d_str}", callback_data=f"edit_date_{d_str}")])

    keyboard.append([InlineKeyboardButton("✍️ Escribir otra fecha (DD-MM-YYYY)", callback_data="edit_date_custom")])
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "✏️ *EDICIÓN MANUAL DE PRODUCCIÓN*\n\n"
        "Selecciona la fecha que deseas corregir o actualizar:"
    )

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    return EDIT_SELECT_DATE


async def handle_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa la selección de fecha por botón callback o entrada manual."""
    query = update.callback_query

    if query:
        await query.answer()
        data = query.data

        if data == "edit_cancel":
            await query.edit_message_text("❌ *Edición cancelada.*", parse_mode="Markdown")
            context.user_data.clear()
            return ConversationHandler.END

        if data == "edit_date_custom":
            await query.edit_message_text(
                "✍️ *Por favor escribe la fecha a editar en formato DD-MM-YYYY* (Ejemplo: `20-07-2026`):",
                parse_mode="Markdown"
            )
            return EDIT_SELECT_DATE

        if data.startswith("edit_date_"):
            raw_date = data.replace("edit_date_", "")
            parsed = parse_board_date(raw_date)
            if not parsed:
                await query.edit_message_text("❌ Fecha no válida. Por favor reintenta con `/editar`.")
                return ConversationHandler.END

            context.user_data["edit_date"] = parsed
            return await prompt_product_selection(update, context, parsed)

    else:
        # Entrada manual por texto
        text_input = update.message.text.strip()
        parsed = parse_board_date(text_input)
        if not parsed:
            await update.message.reply_text(
                "⚠️ *Formato de fecha inválido.* Por favor ingresa la fecha en formato DD-MM (ej. `20-07`) o DD-MM-YYYY:",
                parse_mode="Markdown"
            )
            return EDIT_SELECT_DATE

        context.user_data["edit_date"] = parsed
        return await prompt_product_selection(update, context, parsed)


async def prompt_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_date: date):
    """Muestra el menú de selección de productos para la fecha dada."""
    d_str = selected_date.strftime("%d-%m-%Y")

    keyboard = []
    for code, info in PRODUCT_CATALOG.items():
        keyboard.append([
            InlineKeyboardButton(f"{info['emoji']} {info['name']} ({code})", callback_data=f"edit_prod_{code}")
        ])

    keyboard.append([InlineKeyboardButton("❌ Marcar como Día No Laborado ('X')", callback_data="edit_prod_NOWORK")])
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="edit_cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"📅 *Fecha seleccionada:* `{d_str}`\n\n"
        "Selecciona el producto que deseas modificar:"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    return EDIT_SELECT_PRODUCT


async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el producto seleccionado."""
    query = update.callback_query
    if not query or not query.data:
        return EDIT_SELECT_PRODUCT

    await query.answer()
    data = query.data

    if data == "edit_cancel":
        await query.edit_message_text("❌ *Edición cancelada.*", parse_mode="Markdown")
        context.user_data.clear()
        return ConversationHandler.END

    selected_date = context.user_data.get("edit_date")
    if not selected_date:
        await query.edit_message_text("❌ Sesión expirada. Por favor usa `/editar` nuevamente.")
        return ConversationHandler.END

    if data == "edit_prod_NOWORK":
        # Marcar todo el día como NO LABORADO (0 en todos los productos)
        records = [
            {"date": selected_date, "product_code": code, "quantity": 0, "is_worked_day": False}
            for code in PRODUCT_CATALOG.keys()
        ]
        try:
            async with get_db() as session:
                await upsert_production_records(session, records)
                consolidated = await get_consolidated_inventory(session)

            d_str = selected_date.strftime("%d-%m-%Y")
            await query.edit_message_text(
                f"✅ *DÍA NO LABORADO REGISTRADO*\n\n"
                f"La fecha `{d_str}` fue marcada como día sin producción ('X').\n"
                f"Usa `/inventario` para consultar el stock consolidado.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error al marcar día no laborado: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error al guardar en BD: `{escape_markdown(str(e))}`", parse_mode="Markdown")

        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("edit_prod_"):
        prod_code = data.replace("edit_prod_", "")
        if prod_code not in PRODUCT_CATALOG:
            await query.edit_message_text("❌ Producto no válido.")
            return ConversationHandler.END

        context.user_data["edit_product"] = prod_code
        p_info = get_product_info(prod_code)
        d_str = selected_date.strftime("%d-%m-%Y")

        await query.edit_message_text(
            f"📅 *Fecha:* `{d_str}`\n"
            f"{p_info['emoji']} *Producto:* `{p_info['name']} ({prod_code})`\n\n"
            f"✍️ *Escribe el nuevo número de unidades producidas:*",
            parse_mode="Markdown"
        )
        return EDIT_INPUT_QTY

    return EDIT_SELECT_PRODUCT


async def handle_quantity_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa y guarda la nueva cantidad ingresada."""
    text_input = update.message.text.strip()

    if not text_input.isdigit():
        await update.message.reply_text(
            "⚠️ *Cantidad no válida.* Por favor ingresa únicamente un número entero positivo (ej. `105` o `0`):",
            parse_mode="Markdown"
        )
        return EDIT_INPUT_QTY

    new_qty = int(text_input)
    selected_date = context.user_data.get("edit_date")
    selected_prod = context.user_data.get("edit_product")

    if not selected_date or not selected_prod:
        await update.message.reply_text("❌ Sesión de edición expirada. Reintenta con `/editar`.")
        context.user_data.clear()
        return ConversationHandler.END

    records = [
        {"date": selected_date, "product_code": selected_prod, "quantity": new_qty, "is_worked_day": True}
    ]

    try:
        async with get_db() as session:
            await upsert_production_records(session, records)
            consolidated = await get_consolidated_inventory(session)

        p_info = get_product_info(selected_prod)
        d_str = selected_date.strftime("%d-%m-%Y")
        current_stock = consolidated.get(selected_prod, {}).get("current_stock", 0)

        keyboard = [[InlineKeyboardButton("📦 Ver Inventario Actualizado", callback_data="refresh_inventory")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ *¡PRODUCCIÓN ACTUALIZADA EXITOSAMENTE!*\n\n"
            f"📅 *Fecha:* `{d_str}`\n"
            f"{p_info['emoji']} *Producto:* `{p_info['name']} ({selected_prod})`\n"
            f"🔢 *Nueva Cantidad:* `{new_qty}` unidades\n\n"
            f"🟢 *Stock Neto Actualizado de {p_info['name']}:* `{current_stock}` unidades",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error al guardar corrección de producción: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error al guardar en BD: `{escape_markdown(str(e))}`", parse_mode="Markdown")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el flujo de edición manual."""
    context.user_data.clear()
    msg = "❌ *Edición manual cancelada.*"
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
    return ConversationHandler.END


edit_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("editar", start_edit_flow),
        CommandHandler("editar_dia", start_edit_flow),
    ],
    states={
        EDIT_SELECT_DATE: [
            CallbackQueryHandler(handle_date_selection, pattern="^(edit_date_|edit_cancel)"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date_selection),
        ],
        EDIT_SELECT_PRODUCT: [
            CallbackQueryHandler(handle_product_selection, pattern="^(edit_prod_|edit_cancel)"),
        ],
        EDIT_INPUT_QTY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quantity_input),
        ],
    },
    fallbacks=[
        CommandHandler("cancelar", cancel_edit),
        CallbackQueryHandler(cancel_edit, pattern="^edit_cancel$"),
    ],
)
