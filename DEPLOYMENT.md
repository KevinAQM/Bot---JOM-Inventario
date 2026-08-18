# 🚀 GUÍA PASO A PASO: CONFIGURACIÓN Y DESPLIEGUE GRATUITO EN LA NUBE

Esta guía te explicará detalladamente cómo configurar todas las herramientas y servicios en línea gratuitos necesarios para poner en marcha tu **Bot de Telegram de Producción e Inventario**.

---

## 📋 PASO 1: Crear el Bot en Telegram (@BotFather)

1. Abre la aplicación de Telegram en tu celular o computadora.
2. Busca el usuario oficial `@BotFather` (tiene un check azul de verificación).
3. Inicia una conversación y envía el comando:
   ```text
   /newbot
   ```
4. BotFather te pedirá dos nombres:
   - **Nombre visible**: Ej. `Bot Inventario Campo`
   - **Nombre de usuario (username)**: Debe terminar en `bot`. Ej. `MiProduccionCampo_bot`
5. Al finalizar, BotFather te entregará un mensaje con el **Token de la API HTTP**:
   ```text
   Use this token to access the HTTP API:
   123456789:AAFg...-tu_token_aqui...
   ```
   👉 *Guarda este token, será la variable `TELEGRAM_BOT_TOKEN`.*

6. **Obtener tus IDs de Telegram autorizados (Seguridad)**:
   - Para que solo tú y tu equipo (hasta 3 celulares) puedan usar el bot, cada usuario debe buscar a `@userinfobot` en Telegram y enviarle cualquier mensaje.
   - `@userinfobot` les responderá con su `Id` numérico (ej: `987654321`).
   - Anota los IDs separados por comas. Ej. `123456789,987654321`.
   👉 *Éstos formarán la variable `ALLOWED_TELEGRAM_USERS`.*

---

## 🔑 PASO 2: Obtener la API Key Gratuita de Google Gemini IA

1. Ingresa a [Google AI Studio](https://aistudio.google.com/).
2. Inicia sesión con tu cuenta personal o empresarial de Google (Gmail).
3. Haz clic en el botón azul **"Get API key"** (Obtener clave API) en el menú lateral o superior.
4. Presiona **"Create API key"** -> **"Create API key in new project"**.
5. Copia la clave generada (empieza por `AIzaSy...`).
   👉 *Ésta será tu variable `GEMINI_API_KEY`.* (Utiliza el modelo `gemini-3.7-flash`).

---

## 🗄️ PASO 3: Crear la Base de Datos PostgreSQL Gratuita (Neon.tech o Supabase)

Recomendamos **Neon.tech** por ser extremadamente rápido, gratuito y no requerir tarjeta de crédito.

### Opción A: Neon.tech (Recomendado)
1. Entra a [https://neon.tech](https://neon.tech) y regístrate con tu cuenta de GitHub o Google.
2. Haz clic en **"Create a project"**.
3. Nombra tu proyecto (ej: `inventario-campo`) y haz clic en **"Create project"**.
4. En el panel principal (Dashboard), busca la sección **"Connection Details"**.
5. Selecciona la opción **"Connection string"** (asegúrate de que esté marcado `Node.js` o `PostgreSQL`).
6. Copia la URL que luce así:
   ```text
   postgresql://usuario:password@ep-xyz-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
   👉 *Ésta será tu variable `DATABASE_URL`.* (El bot transformará automáticamente `postgresql://` a `postgresql+asyncpg://` para conexión asíncrona).

### Opción B: Supabase
1. Entra a [https://supabase.com](https://supabase.com) y crea una cuenta.
2. Crea un **New Project**, asigna nombre y contraseña de base de datos.
3. Ve a `Project Settings` -> `Database` -> `Connection String` (URI) y copia la cadena.

---

## ☁️ PASO 4: Desplegar el Bot 24/7 Gratis en Render.com (o Koyeb.com)

**Render.com** permite ejecutar workers de Python de forma continua en su plan gratuito.

1. **Subir tu código a GitHub**:
   - Crea un repositorio privado en [GitHub.com](https://github.com).
   - Sube todos los archivos del proyecto (`config.py`, `main.py`, `requirements.txt`, carpeta `bot/`, `database/`, `services/`, etc.).

2. **Crear el servicio en Render**:
   - Entra a [Render.com](https://render.com) y regístrate o inicia sesión con tu cuenta de GitHub.
   - En el panel principal, haz clic en **"New +"** y selecciona **"Background Worker"** (o "Web Service").
   - Conecta tu repositorio de GitHub `bot_produccion`.

3. **Configurar el Servicio**:
   - **Name**: `bot-inventario-produccion`
   - **Region**: Selecciona la más cercana (ej: Oregon / Frankfurt).
   - **Environment**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     python main.py
     ```
   - **Instance Type**: Selecciona **Free** ($0 / month).

4. **Cargar las Variables de Entorno (Environment Variables)**:
   En la pestaña **"Environment"** de Render, agrega las siguientes llaves y valores:

   | Key | Value |
   | :--- | :--- |
   | `TELEGRAM_BOT_TOKEN` | Tu token de BotFather (ej. `123456789:AAFg...`) |
   | `GEMINI_API_KEY` | Tu API key de Google AI Studio (ej. `AIzaSy...`) |
   | `GEMINI_MODEL` | `gemini-3.7-flash` |
   | `DATABASE_URL` | Tu URI de Neon/Supabase (ej. `postgresql://...`) |
   | `ALLOWED_TELEGRAM_USERS` | Tus IDs de Telegram (ej. `123456789,987654321`) |
   | `DEFAULT_YEAR` | `2026` |
   | `PYTHON_VERSION` | `3.11.0` |

5. **Desplegar**:
   - Haz clic en **"Create Background Worker"**.
   - Render compilará tu código, instalará las dependencias e iniciará el bot.
   - Verás en los logs:
     ```text
     ==================================================
     Iniciando Bot de Control de Inventario y Producción
     ==================================================
     Inicializando tablas en la base de datos...
     Base de datos lista y sincronizada.
     Bot en ejecución. Escuchando mensajes de Telegram...
     ```

---

## 📱 PASO 5: ¡Probar tu Bot en Telegram!

1. Abre tu bot en Telegram y presiona `/start`.
2. Asigna tu stock inicial de prueba usando:
   ```text
   /set_stock R 500 V 300 A 100 NC 50 N 200
   ```
3. Toma una foto a tu pizarra de campo y envíasela al bot.
4. Presiona `[✅ Confirmar e Ingresar]` en la vista previa.
5. Consulta tu stock disponible con el comando `/inventario`.
6. Haz un retiro de prueba con `/retiro`.

¡Felicidades! Tu bot está 100% operativo, seguro y funcionando en la nube de forma totalmente gratuita.
