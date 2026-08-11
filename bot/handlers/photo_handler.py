import json
import logging
from datetime import datetime, date as date_cls
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import config
from bot.middlewares import restricted_access
from database.connection import get_db
from database.crud import (
    upsert_production_records, record_withdrawal, create_photo_audit,
    update_photo_audit_status, get_consolidated_inventory,
    get_photo_audit_by_id, count_photos_today
)
from database.models import PRODUCT_CATALOG
from services.schemas import AnalisisPizarra
from services.vision_service import analyze_whiteboard_photo, _build_db_records

logger = logging.getLogger(__name__)

# Límite máximo de fotos por usuario por día (para proteger cuota gratuita de Gemini)
MAX_PHOTOS_PER_DAY = 3


async def safe_edit_message_text(query, text: str, reply_markup=None):
    """Helper para editar mensajes de forma segura manejando errores de parseo Markdown de Telegram."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Fallo al editar mensaje con Markdown, reintentando como texto plano: {e}")
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
        except Exception as inner_e:
            logger.error(f"Fallo definitivo al editar mensaje: {inner_e}")


@restricted_access
async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Recibe la foto enviada por el usuario, la analiza con Gemini 3.6 Flash
    y muestra una vista previa interactiva antes de guardar en la BD.
    """
    message = update.message
    if not message or not message.photo:
        return

    telegram_user_id = update.effective_user.id
    status_msg = None

    try:
        # 1. Verificar límite diario de fotos (máximo 3 por día por usuario)
        async with get_db() as session:
            photos_today = await count_photos_today(session, telegram_user_id)

        if photos_today >= MAX_PHOTOS_PER_DAY:
            await message.reply_text(
                f"⚠️ *Límite diario alcanzado*\n\n"
                f"Ya has enviado *{photos_today}* fotos hoy. El máximo permitido es *{MAX_PHOTOS_PER_DAY}* por día "
                f"para proteger la cuota gratuita de la IA.\n\n"
                f"Podrás enviar nuevas fotos mañana.",
                parse_mode="Markdown"
            )
            return

        # 2. Enviar mensaje de espera inicial
        status_msg = await message.reply_text(
            f"⏳ *Analizando la foto de la pizarra con IA ({config.GEMINI_MODEL})...*\n"
            f"Por favor espera unos segundos. (Envío {photos_today + 1}/{MAX_PHOTOS_PER_DAY} del día)",
            parse_mode="Markdown"
        )

        # 3. Obtener la foto de mayor resolución
        photo_file = await message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        telegram_file_id = photo_file.file_id

        # 4. Analizar con IA Gemini Vision
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

        # 5. Registrar en la tabla de auditoría (persiste el borrador en BD con ID numérico garantizado)
        async with get_db() as session:
            audit = await create_photo_audit(
                session=session,
                telegram_file_id=telegram_file_id,
                telegram_user_id=telegram_user_id,
                extracted_summary=analysis.model_dump_json()
            )
            audit_id = audit.id

        if not audit_id:
            logger.error("Error: audit_id es None después de guardar auditoría en BD.")
            await status_msg.edit_text("❌ Error al generar el identificador del borrador. Por favor reintenta enviando la foto.")
            return

        # 6. Formatear vista previa en texto Markdown en español
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
        logger.error(f"Error al procesar la foto con Gemini / BD: {e}", exc_info=True)
        err_text = (
            f"❌ *Error al procesar la foto de la pizarra*\n\n"
            f"Ocurrió un problema: `{str(e)}`\n"
            f"Por favor reintenta enviando una nueva foto más clara."
        )
        if status_msg:
            try:
                await status_msg.edit_text(err_text, parse_mode="Markdown")
            except Exception:
                await message.reply_text(err_text, parse_mode="Markdown")
        else:
            await message.reply_text(err_text, parse_mode="Markdown")


@restricted_access
async def handle_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las acciones de confirmación o cancelación de las fotos analizadas."""
    query = update.callback_query
    if not query or not query.data:
        return

    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"No se pudo responder al query.answer(): {e}")

    data = query.data

    try:
        if data.startswith("confirm_photo_"):
            raw_id = data.replace("confirm_photo_", "")
            if not raw_id.isdigit():
                await safe_edit_message_text(
                    query,
                    "⚠️ Este botón pertenece a un borrador antiguo anterior a la actualización.\n"
                    "Por favor envía una nueva foto de la pizarra para continuar."
                )
                return
            audit_id = int(raw_id)

            # Todo el proceso de confirmación en una sola transacción segura
            async with get_db() as session:
                audit = await get_photo_audit_by_id(session, audit_id)

                if not audit or audit.status != "PENDIENTE":
                    await safe_edit_message_text(
                        query,
                        "⚠️ Este borrador ya fue procesado previamente o no existe.\n"
                        "Envía una nueva foto si necesitas registrar producción."
                    )
                    return

                # Reconstruir los datos desde el JSON guardado en la BD
                try:
                    analysis = AnalisisPizarra.model_validate_json(audit.extracted_summary)
                except Exception as parse_err:
                    logger.error(f"Error al reconstruir borrador desde BD: {parse_err}")
                    await safe_edit_message_text(
                        query,
                        "❌ Error al recuperar los datos de la foto. Por favor envía una nueva foto."
                    )
                    return

                db_records = _build_db_records(analysis, config.DEFAULT_YEAR)

                # 1. Ejecutar UPSERT atómico en BD
                count = await upsert_production_records(session, db_records)

                # 2. Registrar retiros a clientes de la pizarra si los hubiese
                for day in analysis.days:
                    for w in day.withdrawals:
                        clean_date_str = str(day.date_str or "").strip().replace('/', '-')
                        parts = clean_date_str.split('-')
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            try:
                                w_date = date_cls(config.DEFAULT_YEAR, int(parts[1]), int(parts[0]))
                                await record_withdrawal(
                                    session=session,
                                    product_code=w.code.value,
                                    quantity=w.quantity,
                                    withdrawal_type="CLIENTE_PIZARRA",
                                    customer_or_reason=f"Pizarra: {w.customer_name}",
                                    withdrawal_date=w_date
                                )
                            except (ValueError, TypeError) as val_err:
                                logger.warning(f"Fecha de retiro inválida '{day.date_str}': {val_err}")

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
            await safe_edit_message_text(query, "\n".join(stock_summary))

        elif data.startswith("cancel_photo_"):
            raw_id = data.replace("cancel_photo_", "")
            if not raw_id.isdigit():
                await safe_edit_message_text(query, "❌ Registro descartado.")
                return
            audit_id = int(raw_id)

            async with get_db() as session:
                await update_photo_audit_status(session, audit_id, "DESCARTADO")

            await safe_edit_message_text(query, "❌ *Registro descartado.* La foto no ha sido ingresada al inventario.")

    except Exception as e:
        logger.error(f"Error inesperado en handle_photo_callback: {e}", exc_info=True)
        await safe_edit_message_text(
            query,
            f"❌ *Error al procesar la confirmación*\n\n"
            f"Detalle: `{str(e)}`\n"
            f"Por favor intenta nuevamente enviando la foto."
        )
