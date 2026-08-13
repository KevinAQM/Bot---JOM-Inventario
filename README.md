# 🤖 Bot de Telegram: Gestión e Inventario de Producción Diaria en Campo (IA Gemini 3.6 Flash)

Sistema automatizado de control de inventarios diseñado para empresas de campo. Extrae datos de producción a partir de fotografías tomadas a una pizarra física acrílica utilizando **Google Gemini 3.6 Flash (IA Visión)**, almacena la información de forma segura en **PostgreSQL / SQLite**, aplica **deduplicación automática (UPSERT)** por fecha y permite retiros e inventarios interactivos en Telegram.

---

## 🌟 Características Principales

1. **OCR / Visión por Computadora con Gemini 3.6 Flash**:
   - Analiza las fotos de la pizarra y extrae columnas de días (`L`, `M`, `M`, `J`, `V`, `S`, `D`), fechas (`DD-MM`), códigos de producto (`R`, `V`, `A`, `NC`, `N`) y cantidades.
   - Detecta días no laborados marcados con `X`.
   - Lee retiros de clientes anotados al pie de columna (ej. `Maria` -> `V-12`).

2. **Deduplicación por Fecha (UPSERT)**:
   - Dado que una foto tomada el viernes incluye la información acumulada de la semana, la base de datos actualiza o mantiene los registros de fechas existentes sin duplicar el stock.

3. **Flujos Interactivos en Español para Telegram**:
   - **Envío de Foto**: Muestra vista previa Markdown + botones `[✅ Confirmar e Ingresar]` y `[❌ Descartar]`.
   - **`/iniciar`**: Muestra la bienvenida e instrucciones de uso.
   - **`/inventario`**: Muestra el saldo neto en tiempo real (`Base Inicial + Producido - Retirado`).
   - **`/retiro`**: Menú guiado con botones inline para descontar mercadería y registrar cliente o motivo.
   - **`/editar`**: Permite editar o corregir manualmente la producción de cualquier fecha.
   - **`/ajustar_stock`**: Configura o ajusta el inventario inicial base para los 5 productos.
   - **`/historial`**: Revisa los registros de producción de los últimos días.
   - **`/excel`**: Descarga el reporte histórico consolidado en Excel.
   - **`/ayuda`**: Guía detallada de comandos y productos.

4. **Seguridad y Whitelist**:
   - Restringe el uso del bot a una lista blanca de IDs de Telegram (`ALLOWED_TELEGRAM_USERS`) para evitar consumo no autorizado o agotamiento de cuotas API.

---

## 🛠️ Requisitos Previos

- Python 3.11 o superior.
- Token de Bot de Telegram (obtenido de `@BotFather`).
- API Key de Google Gemini (obtenida gratis en [Google AI Studio](https://aistudio.google.com/)).

---

## 🚀 Instalación y Uso Local

1. **Clonar o descargar el proyecto**:
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd bot_produccion
   ```

2. **Crear e instalar el entorno virtual**:
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   # En Linux/Mac:
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configurar las variables de entorno (`.env`)**:
   Copia la plantilla `.env.example` a un nuevo archivo `.env`:
   ```bash
   cp .env.example .env
   ```
   Edita `.env` con tus credenciales:
   ```env
   TELEGRAM_BOT_TOKEN=tu_token_de_botfather
   GEMINI_API_KEY=tu_api_key_de_gemini
   DATABASE_URL=sqlite+aiosqlite:///./inventario.db
   ALLOWED_TELEGRAM_USERS=123456789,987654321
   DEFAULT_YEAR=2026
   ```

4. **Ejecutar Pruebas Unitarias**:
   ```bash
   python run_tests.py
   ```

5. **Iniciar el Bot**:
   ```bash
   python main.py
   ```

---

## 📂 Estructura del Proyecto

```
bot_produccion/
├── config.py                 # Configuración global y validación de .env
├── main.py                   # Punto de entrada principal
├── run_tests.py              # Ejecutador de pruebas unitarias
├── requirements.txt          # Dependencias del proyecto
├── schema.sql                # Script SQL de creación de tablas
├── database/
│   ├── connection.py         # Conexión SQLAlchemy asíncrona (Postgres/SQLite)
│   ├── models.py             # Modelos ORM (DailyProduction, InventoryWithdrawal, etc.)
│   └── crud.py               # Operaciones atómicas UPSERT y consultas
├── services/
│   ├── vision_service.py     # Integración con la API Gemini 2.0 Flash
│   └── schemas.py            # Esquemas Pydantic (Structured Output)
├── bot/
│   ├── middlewares.py        # Control de acceso restringido (Whitelist)
│   ├── bot_app.py            # Constructor y registro de handlers Telegram
│   └── handlers/
│       ├── photo_handler.py  # Procesamiento y confirmación de fotos
│       ├── withdrawal_handler.py # Conversación interactiva /retiro
│       ├── inventory_handler.py  # Reportes /inventario, /set_stock y /historial
│       └── common_handler.py     # Comandos /start y /help
└── DEPLOYMENT.md             # Guía paso a paso para despliegue en la nube gratis
```
