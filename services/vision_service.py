import io
import logging
from datetime import date
from typing import Tuple, List, Dict, Any, Optional, Union
from PIL import Image

from config import config
from services.schemas import AnalisisPizarra, CodigoProducto
from utils.helpers import parse_board_date

logger = logging.getLogger(__name__)

# Prompt detallado en español para guiado del OCR de Gemini
WHITEBOARD_SYSTEM_PROMPT = """
Eres un sistema experto en Visión por Computadora u OCR especializado en extraer datos de producción agrícola/campo anotados en pizarras acrílicas físicas.

INSTRUCCIONES DE LECTURA DE LA PIZARRA:
1. ENCABEZADO: La parte superior de la pizarra dice 'PRODUCCIÓN'.
2. DÍAS DE LA SEMANA: La primera fila tiene las letras L, M, M, J, V, S, D (Lunes, Martes, Miércoles, Jueves, Viernes, Sábado, Domingo).
3. FECHAS: La segunda fila tiene las fechas en formato DD-MM (ejemplo: '20-07', '21-07', '22-07', '23-07', '24-07', '25-07', '28-07').
4. PRODUCTOS Y CANTIDADES:
   Las filas de producción contienen parejas de [Código de Producto]-[Cantidad].
   Los 5 códigos válidos de producto son:
   - R: Rojo (ej: R-110, R-109, R-89, R-43, R-45, R-53)
   - V: Verde (ej: V-94, V-82, V-81)
   - A: Amarillo (ej: A-18, A-24, A-27)
   - NC: No color (ej: NC-63, NC-13, NC-12)
   - N: Negro (ej: N-23, N-150, N-27, N-25)
5. DÍAS NO LABORADOS O SIN PRODUCCIÓN: Si una columna tiene una 'X' marcada o está en blanco/vacía, marca `is_worked_day = false`.
6. RETIROS O SALIDAS A CLIENTES: Si en la parte inferior de una columna de un día hay anotado el nombre de un cliente (ej. 'Maria') seguido de una producción (ej. 'V-12'), extráelo como un retiro en la lista `withdrawals`.

Analiza detenidamente toda la imagen de la pizarra, columna por columna de izquierda a derecha, y devuelve estrictamente la información JSON estructurada según el esquema indicado.
"""


def process_image_bytes(image_bytes: bytes) -> bytes:
    """Valida y optimiza la imagen antes de enviarla a Gemini."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Redimensionar si es extremadamente grande para acelerar la respuesta de la API
        max_dim = 2048
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim))

        output_buffer = io.BytesIO()
        img.save(output_buffer, format='JPEG', quality=85)
        return output_buffer.getvalue()
    except Exception as e:
        logger.warning(f"No se pudo optimizar la imagen con PIL: {e}")
        return image_bytes


def _build_db_records(
    analysis: AnalisisPizarra,
    base_date: Optional[Union[date, int]] = None
) -> List[Dict[str, Any]]:
    """
    Convierte la estructura AnalisisPizarra en una lista de registros
    listos para insertar en la base de datos con inferencia dinámica del año (Perú).
    """
    if isinstance(base_date, int):
        base_date_obj = date(base_date, 1, 1)
    else:
        base_date_obj = base_date

    db_records = []
    for day in analysis.days:
        parsed_date = parse_board_date(day.date_str, base_date=base_date_obj)
        if not parsed_date:
            logger.warning(f"Fecha no reconocida u omitida de la pizarra: '{day.date_str}'")
            continue

        if not day.is_worked_day or not day.items:
            for code in CodigoProducto:
                db_records.append({
                    "date": parsed_date,
                    "product_code": code.value,
                    "quantity": 0,
                    "is_worked_day": False
                })
        else:
            found_codes = set()
            for item in day.items:
                db_records.append({
                    "date": parsed_date,
                    "product_code": item.code.value,
                    "quantity": item.quantity,
                    "is_worked_day": True
                })
                found_codes.add(item.code.value)

            for code in CodigoProducto:
                if code.value not in found_codes:
                    db_records.append({
                        "date": parsed_date,
                        "product_code": code.value,
                        "quantity": 0,
                        "is_worked_day": True
                    })

    return db_records


async def analyze_whiteboard_photo(
    image_bytes: bytes
) -> Tuple[AnalisisPizarra, List[Dict[str, Any]]]:
    """
    Analiza la foto de la pizarra utilizando Google Gemini API (gemini-3.7-flash).
    Devuelve la estructura Pydantic `AnalisisPizarra` y una lista de registros listos para la BD.
    """
    optimized_bytes = process_image_bytes(image_bytes)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=optimized_bytes, mime_type="image/jpeg"),
                WHITEBOARD_SYSTEM_PROMPT
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AnalisisPizarra,
                thinking_config=types.ThinkingConfig(
                    thinking_level="medium"
                )
            )
        )

        analysis = AnalisisPizarra.model_validate_json(response.text)

    except Exception as e:
        logger.error(f"Error al invocar Google Gemini SDK (google-genai): {e}", exc_info=True)
        raise RuntimeError(
            f"Error en el análisis de imagen con Gemini IA ({config.GEMINI_MODEL}): {e}"
        )

    db_records = _build_db_records(analysis)
    return analysis, db_records
