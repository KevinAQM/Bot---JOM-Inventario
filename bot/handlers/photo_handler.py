import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import config
from bot.middlewares import restricted_access
from database.connection import get_db
from database.crud import (
    upsert_production_records, record_withdrawal, create_photo_audit,
    update_photo_audit_status, get_consolidated_inventory
)
from database.models import PRODUCT_CATALOG
from services.vision_service import analyze_whiteboard_photo

logger = logging.getLogger(__name__)

# Diccionario en memoria para borradores temporales mientras el usuario confirma
PENDING_DRAFTS = {}

@restricted_access
async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Recibe la foto enviada por el usuario, la analiza con Gemini 2.0 Flash
    y muestra una vista previa interactiva antes de guardar en la BD.
    """
    message = update.message
    if not message or not message.photo:
        return

    # Enviar mensaje de espera inicial
    status_msg = await message.reply_text(
        f"⏳ *Analizando la foto de la pizarra con IA ({config.GEMINI_MODEL})...*\nPor favor espera unos segundos.",
        parse_mode="Markdown"
    )

    try:
        # Obtener la foto de mayor resolución
        photo_file = await message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        telegram_file_id = photo_file.file_id
        telegram_user_id = update.effective_user.id

        # Analizar con IA Gemini Vision
        analysis, db_records = await analyze_whiteboard_photo(
            bytes(image_bytes),
            year=config.DEFAULT_YEAR
        )

        if not db_records:
            await status_msg.edit_text(
                "⚠️ *No se pudieron extraer datos de la foto.*\n"
                "Asegúrate de que la imagen sea legible, tenga buena iluminación y muestre claramente la pizarra.",
                parse_mode="Markdown"
            )
            return

        # Registrar en la tabla de auditoría
        async with get_db() as session:
            audit = await create_photo_audit(
                session=session,
                telegram_file_id=telegram_file_id,
                telegram_user_id=telegram_user_id,
                extracted_summary=analysis.model_dump_json()
            )
            audit_id = audit.id

        # Guardar en el diccionario de borradores pendientes
        PENDING_DRAFTS[audit_id] = {
            "db_records": db_records,
            "analysis": analysis,
            "telegram_user_id": telegram_user_id
        }

        # Formatear vista previa en texto Markdown en español
        preview_lines = [
            "📋 *VISTA PREVIA DE PRODUCCIÓN EXTRAÍDA*\n",
            "Revisa los datos leídos de la pizarra antes de ingresar al inventario:\n"
        ]

        for day in analysis.days:
            clean_date = day.date_str
            if not day.is_worked_day:
                preview_lines.append(f"📅 *{clean_date}* (Día No Laborado / Sin Producción - 'X')")
            else:
                preview_lines.append(f"📅 *Día {day.day_header} ({clean_date})*:")
                if not day.items:
                    preview_lines.append("   └ _Sin ítems de producción_")
                for item in day.items:
                    code_val = item.code.value
                    cat_info = PRODUCT_CATALOG.get(code_val, {"name": code_val, "emoji": "📦"})
                    preview_lines.append(f"   ├ {cat_info['emoji']} *{cat_info['name']} ({code_val})*: {item.quantity} unidades")

                if day.withdrawals:
                    preview_lines.append("   └ 🛒 *Retiros a clientes registrados:*")
                    for w in day.withdrawals:
                        w_code = w.code.value
                        w_cat = PRODUCT_CATALOG.get(w_code, {"name": w_code, "emoji": "📦"})
                        preview_lines.append(f"      • {w.customer_name}: {w_cat['emoji']} {w.quantity} {w_cat['name']}")
            preview_lines.append("")

        if analysis.observations:
            preview_lines.append(f"ℹ️ *Observaciones IA:* _{analysis.observations}_\n")

        preview_lines.append("¿Deseas confirmar el ingreso de estos datos?")
        preview_text = "\n".join(preview_lines)

        # Botones interactivos Inline
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirmar e Ingresar", callback_data=f"confirm_photo_{audit_id}"),
                InlineKeyboardButton("❌ Descartar Foto", callback_data=f"cancel_photo_{audit_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_msg.edit_text(
            preview_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error al procesar la foto con Gemini: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ *Error al procesar la foto de la pizarra*\n\n"
            f"Ocurrió un problema durante el análisis de imagen: `{str(e)}`\n"
            f"Por favor reintenta enviando una nueva foto más clara.",
            parse_mode="Markdown"
        )

async def handle_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las acciones de confirmación o cancelación de las fotos analizadas."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data

    if data.startswith("confirm_photo_"):
        audit_id = int(data.replace("confirm_photo_", ""))
        draft = PENDING_DRAFTS.pop(audit_id, None)

        if not draft:
            await query.edit_message_text("⚠️ Este borrador ya expiró o fue procesado previamente.")
            return

        db_records = draft["db_records"]
        analysis = draft["analysis"]

        try:
            async with get_db() as session:
                # 1. Ejecutar UPSERT atómico en BD
                count = await upsert_production_records(session, db_records)

                # 2. Registrar retiros a clientes de la pizarra si los hubiese
                for day in analysis.days:
                    for w in day.withdrawals:
                        # Extraer fecha
                        clean_date_str = day.date_str.strip().replace('/', '-')
                        parts = clean_date_str.split('-')
                        if len(parts) == 2:
                            w_date = datetime(config.DEFAULT_YEAR, int(parts[1]), int(parts[0])).date()
                            await record_withdrawal(
                                session=session,
                                product_code=w.code.value,
                                quantity=w.quantity,
                                withdrawal_type="CLIENTE_PIZARRA",
                                customer_or_reason=f"Pizarra: {w.customer_name}",
                                withdrawal_date=w_date
                            )

                # 3. Actualizar estado de auditoría
                await update_photo_audit_status(session, audit_id, "CONFIRMADO")

                # 4. Obtener inventario actualizado
                consolidated = await get_consolidated_inventory(session)

            # Formatear mensaje final de éxito
            stock_summary = ["✅ *¡PRODUCCIÓN INGRESADA EXITOSAMENTE!*\n"]
            stock_summary.append("Se han actualizado o registrado los datos en la base de datos sin duplicaciones.\n")
            stock_summary.append("📦 *Estado Actualizado del Inventario:*")

            for code, data_item in consolidated.items():
                stock_summary.append(
                    f"• {data_item['emoji']} *{data_item['name']} ({code})*: `{data_item['current_stock']}` unidades"
                )

            stock_summary.append("\nUsa `/inventario` para ver el desglose completo de stock.")
            await query.edit_message_text("\n".join(stock_summary), parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error al guardar registros en BD: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error al guardar en la base de datos: `{str(e)}`", parse_mode="Markdown")

    elif data.startswith("cancel_photo_"):
        audit_id = int(data.replace("cancel_photo_", ""))
        PENDING_DRAFTS.pop(audit_id, None)

        async with get_db() as session:
            await update_photo_audit_status(session, audit_id, "DESCARTADO")

        await query.edit_message_text("❌ *Registro descartado.* La foto no ha sido ingresada al inventario.", parse_mode="Markdown")
