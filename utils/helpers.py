import re
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Dict, Any

from database.models import PRODUCT_CATALOG

logger = logging.getLogger(__name__)

# Zona horaria de Perú (UTC-5)
PERU_TZ = timezone(timedelta(hours=-5))

def get_peru_now() -> datetime:
    """Devuelve la fecha y hora actual en la zona horaria de Perú (UTC-5)."""
    return datetime.now(PERU_TZ)

def get_peru_today() -> date:
    """Devuelve la fecha actual (date) en la zona horaria de Perú (UTC-5)."""
    return get_peru_now().date()

def escape_markdown(text: Optional[str]) -> str:
    r"""
    Escapa los caracteres especiales de Markdown V1 de Telegram (_ * ` [ \)
    para evitar fallos de renderizado cuando el usuario ingresa textos con guiones u otros símbolos.
    """
    if not text:
        return ""
    # Primero se escapa la barra invertida para no alterar los demás reemplazos
    escaped = str(text).replace("\\", "\\\\")
    for char in ["_", "*", "`", "["]:
        escaped = escaped.replace(char, f"\\{char}")
    return escaped

def parse_board_date(date_str: str, base_date: Optional[date] = None) -> Optional[date]:
    """
    Parsea una fecha extraída de la pizarra (usualmente en formato DD-MM o DD/MM) e infiere
    el año adecuado de forma 100% dinámica basándose en la fecha actual de Perú.

    Ejemplos:
    - '20-07' -> date(2026, 7, 20) si estamos en 2026
    - '28-12' analizado en Enero 2026 -> date(2025, 12, 28) (inteligencia de cambio de año)
    - '2026-07-20' -> date(2026, 7, 20)
    - '20/07/2026' -> date(2026, 7, 20)
    """
    if not date_str:
        return None

    clean_str = str(date_str).strip().replace('/', '-')
    if not base_date:
        base_date = get_peru_today()

    parts = [p for p in clean_str.split('-') if p.isdigit()]

    try:
        # Caso 1: DD-MM (Formato habitual en pizarra física)
        if len(parts) == 2:
            day_num = int(parts[0])
            month_num = int(parts[1])
            year_num = base_date.year

            # Manejo inteligente de transición de año (Dic-Ene)
            if base_date.month == 1 and month_num == 12:
                year_num -= 1
            elif base_date.month == 12 and month_num == 1:
                year_num += 1

            return date(year_num, month_num, day_num)

        # Caso 2: YYYY-MM-DD o DD-MM-YYYY (3 partes)
        elif len(parts) == 3:
            p1, p2, p3 = int(parts[0]), int(parts[1]), int(parts[2])
            if p1 > 1000:  # YYYY-MM-DD
                return date(p1, p2, p3)
            elif p3 > 1000:  # DD-MM-YYYY
                return date(p3, p2, p1)

    except (ValueError, TypeError) as e:
        logger.warning(f"No se pudo parsear la fecha '{date_str}': {e}")

    return None

def get_product_info(code: str) -> Dict[str, Any]:
    """
    Retorna la información estandarizada de un producto desde el catálogo (nombre, emoji y código limpio).
    """
    code_upper = str(code).strip().upper() if code else ""
    info = PRODUCT_CATALOG.get(code_upper)
    if info:
        return {
            "code": code_upper,
            "name": info["name"],
            "emoji": info["emoji"]
        }
    return {
        "code": code_upper,
        "name": code_upper or "Desconocido",
        "emoji": "📦"
    }
