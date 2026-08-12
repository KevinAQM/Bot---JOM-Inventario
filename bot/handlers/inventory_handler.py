import logging
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

from bot.middlewares import restricted_access
from database.connection import get_db
from database.crud import (
    get_consolidated_inventory, get_recent_production, set_initial_stock, get_full_historical_data
)
from utils.helpers import PERU_TZ, get_product_info, escape_markdown

logger = logging.getLogger(__name__)

# Estados para la conversación /set_stock interactiva
SET_STOCK_PRODUCT, SET_STOCK_QTY = range(2)

@restricted_access
async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /inventario: Muestra el estado del inventario consolidado."""
    try:
        async with get_db() as session:
            consolidated = await get_consolidated_inventory(session)

        now_str = datetime.now(PERU_TZ).strftime("%d-%m-%Y %H:%M")
        lines = [
            "📦 *ESTADO ACTUAL DEL INVENTARIO DE PRODUCCIÓN*\n",
            f"🕒 _Consultado el: {now_str}_\n"
        ]

        total_net = 0
        for code, info in consolidated.items():
            stock = info["current_stock"]
            total_net += stock
            lines.append(
                f"{info['emoji']} *{info['name']} ({code})*\n"
                f"   ├ Base Inicial: `{info['initial']}`\n"
                f"   ├ Total Producido: `+{info['produced']}`\n"
                f"   ├ Total Retirado: `-{info['withdrawn']}`\n"
                f"   └ 🟢 *Stock Neto Disponible:* `{stock}` unidades\n"
            )

        lines.append(f"📊 *TOTAL GLOBAL DISPONIBLE:* `{total_net}` unidades")

        keyboard = [
            [
                InlineKeyboardButton("🔄 Actualizar", callback_data="refresh_inventory"),
                InlineKeyboardButton("📜 Historial de Días", callback_data="view_history")
            ],
            [
                InlineKeyboardButton("📊 Descargar Reporte Excel", callback_data="download_excel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = "\n".join(lines)
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error al consultar inventario: {e}", exc_info=True)
        msg = f"❌ Error al consultar la base de datos: `{str(e)}`"
        if update.message:
            await update.message.reply_text(msg, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode="Markdown")

async def inventory_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del reporte de inventario (actualizar / historial / excel)."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    if query.data == "refresh_inventory":
        await show_inventory(update, context)
    elif query.data == "view_history":
        await show_history(update, context)
    elif query.data == "download_excel":
        await export_excel_handler(update, context)


@restricted_access
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /historial o callback para ver registros recientes."""
    try:
        async with get_db() as session:
            history = await get_recent_production(session, limit_days=7)

        if not history:
            text = "📜 *HISTORIAL DE PRODUCCIÓN*\n\nNo se han registrado días de producción aún."
        else:
            lines = ["📜 *REGISTRO DE PRODUCCIÓN (ÚLTIMOS DÍAS)*\n"]
            for day in history:
                d_str = day["date_str"]
                if not day["is_worked_day"]:
                    lines.append(f"📅 *{d_str}*: ❌ Día No Laborado ('X')")
                else:
                    items_str = []
                    for code, qty in day["items"].items():
                        cat = PRODUCT_CATALOG.get(code, {"emoji": "📦"})
                        items_str.append(f"{cat['emoji']}{code}:{qty}")
                    lines.append(f"📅 *{d_str}*: " + ", ".join(items_str))

            lines.append("\nUsa `/inventario` para ver el saldo de stock total.")
            text = "\n".join(lines)

        keyboard = [[InlineKeyboardButton("⬅️ Volver a Inventario", callback_data="refresh_inventory")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error al obtener historial: {e}", exc_info=True)
        if update.message:
            await update.message.reply_text(f"❌ Error al consultar historial: `{str(e)}`")

# -------------------------------------------------------------
# COMANDO Y FLUJO INTERACTIVO /set_stock
# -------------------------------------------------------------

@restricted_access
async def start_set_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Permite establecer el stock inicial.
    Soporta uso con argumentos directos: /set_stock R 100 V 50 A 20 NC 30 N 10
    O menú interactivo si no se envían argumentos.
    """
    args = context.args
    if args and len(args) >= 2:
        # Modo rápido por línea de comandos
        stock_map = {}
        try:
            for i in range(0, len(args) - 1, 2):
                code = args[i].upper()
                qty = int(args[i + 1])
                if code in PRODUCT_CATALOG:
                    stock_map[code] = qty

            if stock_map:
                async with get_db() as session:
                    await set_initial_stock(session, stock_map)
                    consolidated = await get_consolidated_inventory(session)

                res = ["⚙️ *INVENTARIO INICIAL ESTABLECIDO CORRECTAMENTE*\n"]
                for c, q in stock_map.items():
                    info = PRODUCT_CATALOG[c]
                    res.append(f"• {info['emoji']} *{info['name']} ({c})*: Base asignada a `{q}` unidades")

                await update.message.reply_text("\n".join(res), parse_mode="Markdown")
                return ConversationHandler.END
        except ValueError:
            pass

    # Modo interactivo paso a paso
    keyboard = [
        [
            InlineKeyboardButton("🔴 Rojo (R)", callback_data="setstock_R"),
            InlineKeyboardButton("🟢 Verde (V)", callback_data="setstock_V")
        ],
        [
            InlineKeyboardButton("🟡 Amarillo (A)", callback_data="setstock_A"),
            InlineKeyboardButton("⚪ No Color (NC)", callback_data="setstock_NC")
        ],
        [
            InlineKeyboardButton("⬛ Negro (N)", callback_data="setstock_N"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_setstock")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ *CONFIGURACIÓN DE INVENTARIO INICIAL BASE*\n\n"
        "Selecciona el **producto** para definir o ajustar su cantidad inicial base:\n"
        "_(Tip: También puedes usar `/set_stock R 100 V 50 A 20 NC 30 N 10` en un solo comando)_",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return SET_STOCK_PRODUCT

async def set_stock_product_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_setstock":
        await query.edit_message_text("❌ Configuración de inventario inicial cancelada.")
        return ConversationHandler.END

    code = data.replace("setstock_", "")
    context.user_data["set_stock_code"] = code
    info = PRODUCT_CATALOG.get(code, {"name": code, "emoji": "📦"})

    await query.edit_message_text(
        f"Has seleccionado: {info['emoji']} *{info['name']} ({code})*\n\n"
        f"✍️ Escribe el **inventario inicial base** para este producto (ejemplo: `500`):",
        parse_mode="Markdown"
    )
    return SET_STOCK_QTY

async def set_stock_qty_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip() if update.message else ""

    if not text.isdigit() or int(text) < 0:
        await update.message.reply_text("⚠️ Ingresa un número entero mayor o igual a 0:")
        return SET_STOCK_QTY

    qty = int(text)
    code = context.user_data.get("set_stock_code", "R")
    info = PRODUCT_CATALOG.get(code, {"name": code, "emoji": "📦"})

    try:
        async with get_db() as session:
            await set_initial_stock(session, {code: qty})
            consolidated = await get_consolidated_inventory(session)

        new_stock = consolidated.get(code, {}).get("current_stock", 0)

        await update.message.reply_text(
            f"✅ *Inventario Base Actualizado*\n\n"
            f"• Producto: {info['emoji']} *{info['name']} ({code})*\n"
            f"• Nueva Base Inicial: `{qty}` unidades\n"
            f"• 📦 *Stock Neto Disponible:* `{new_stock}` unidades",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error al establecer stock inicial: {e}")
        await update.message.reply_text(f"❌ Error al guardar en base de datos: `{str(e)}`")

    return ConversationHandler.END

async def cancel_set_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("❌ Configuración cancelada.")
    elif update.callback_query:
        await update.callback_query.edit_message_text("❌ Configuración cancelada.")
    return ConversationHandler.END

set_stock_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("set_stock", start_set_stock)],
    states={
        SET_STOCK_PRODUCT: [CallbackQueryHandler(set_stock_product_selected, pattern="^(setstock_|cancel_setstock)")],
        SET_STOCK_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_stock_qty_entered)]
    },
    fallbacks=[CommandHandler("cancelar", cancel_set_stock)]
)


@restricted_access
async def export_excel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /excel o /reporte: Genera y envía el reporte completo en formato Excel (.xlsx)."""
    status_msg = None
    try:
        if update.message:
            status_msg = await update.message.reply_text("📊 _Generando reporte completo de inventario en Excel..._", parse_mode="Markdown")

        async with get_db() as session:
            historical_data = await get_full_historical_data(session)

        # Generar Excel en memoria
        from services.excel_service import generate_excel_report
        excel_buffer = generate_excel_report(historical_data)

        filename = f"Inventario_JOM_{datetime.now(PERU_TZ).strftime('%Y-%m-%d_%H%M')}.xlsx"
        caption = f"📊 *Reporte General de Inventario y Producción*\n📅 Generado el: `{datetime.now(PERU_TZ).strftime('%d/%m/%Y %H:%M')}`"

        if update.message:
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            await update.message.reply_document(
                document=excel_buffer,
                filename=filename,
                caption=caption,
                parse_mode="Markdown"
            )
        elif update.callback_query:
            await update.callback_query.message.reply_document(
                document=excel_buffer,
                filename=filename,
                caption=caption,
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error al generar o enviar reporte Excel: {e}", exc_info=True)
        err_text = f"❌ Ocurrió un error al generar el archivo Excel: `{str(e)}`"
        if status_msg:
            try:
                await status_msg.edit_text(err_text, parse_mode="Markdown")
            except Exception:
                pass
        elif update.message:
            await update.message.reply_text(err_text, parse_mode="Markdown")

