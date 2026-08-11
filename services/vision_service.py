import io
import logging
from datetime import datetime, date
from typing import Tuple, List, Dict, Any
from PIL import Image

from config import config
from services.schemas import AnalisisPizarra, CodigoProducto

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

async def analyze_whiteboard_photo(
    image_bytes: bytes,
    year: int = 2026
) -> Tuple[AnalisisPizarra, List[Dict[str, Any]]]:
    """
    Analiza la foto de la pizarra utilizando Google Gemini API (gemini-3.6-flash).
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
                temperature=0.1
            )
        )
        
        analysis = AnalisisPizarra.model_validate_json(response.text)
        
    except Exception as e:
        logger.error(f"Error al invocar Google Gemini SDK (google-genai): {e}")
        # Intentar fallback alternativo con google-generativeai si fuera necesario
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=config.GEMINI_API_KEY)
            model = legacy_genai.GenerativeModel(config.GEMINI_MODEL)
            
            img = Image.open(io.BytesIO(optimized_bytes))
            prompt = WHITEBOARD_SYSTEM_PROMPT + "\nDevuelve un JSON estrictamente conforme a las instrucciones."
            res = model.generate_content([img, prompt])
            
            # Limpiar markdown de respuesta si viene envuelto en ```json ... ```
            raw_text = res.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            analysis = AnalisisPizarra.model_validate_json(raw_text.strip())
        except Exception as fallback_err:
            logger.error(f"Error en fallback de Gemini: {fallback_err}")
            raise RuntimeError(f"Error en el análisis de imagen con Gemini IA: {e}")

    # Convertir las fechas DD-MM extraídas en objetos datetime.date reales con el año configurado
    db_records = []
    for day in analysis.days:
        try:
            # Parsear "20-07" o "20/07"
            clean_date_str = day.date_str.strip().replace('/', '-')
            parts = clean_date_str.split('-')
            if len(parts) == 2:
                day_num = int(parts[0])
                month_num = int(parts[1])
                parsed_date = date(year, month_num, day_num)
            else:
                continue
        except ValueError as ve:
            logger.warning(f"Fecha inválida extraída por la IA '{day.date_str}': {ve}")
            continue

        if not day.is_worked_day or not day.items:
            # Si el día no fue laborado ('X'), podemos registrarlo con cantidades 0 para tener auditoría
            for code in CodigoProducto:
                db_records.append({
                    "date": parsed_date,
                    "product_code": code.value,
                    "quantity": 0,
                    "is_worked_day": False
                })
        else:
            # Registrar cada producto detectado
            found_codes = set()
            for item in day.items:
                db_records.append({
                    "date": parsed_date,
                    "product_code": item.code.value,
                    "quantity": item.quantity,
                    "is_worked_day": True
                })
                found_codes.add(item.code.value)

            # Para los productos del catálogo no mencionados en ese día, colocamos 0
            for code in CodigoProducto:
                if code.value not in found_codes:
                    db_records.append({
                        "date": parsed_date,
                        "product_code": code.value,
                        "quantity": 0,
                        "is_worked_day": True
                    })

    return analysis, db_records
