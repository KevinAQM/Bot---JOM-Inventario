import asyncio
import logging
import os
import sys
from config import config
from database.connection import init_db
from bot.bot_app import create_telegram_application

# Configuración de logs limpia y profesional
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def start_health_check_server():
    """Inicia un servidor HTTP ligero para pasar la prueba de puerto/salud de Render Web Service (Gratis)."""
    port_str = os.getenv("PORT")
    if not port_str or not port_str.isdigit():
        return None

    port = int(port_str)
    
    async def handle_request(reader, writer):
        data = await reader.read(1024)
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "Content-Length: 22\r\n"
            "Connection: close\r\n\r\n"
            "Bot Activo y Saludable"
        )
        writer.write(response.encode('utf-8'))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_request, '0.0.0.0', port)
    logger.info(f"Servidor de Health Check iniciado en el puerto {port} para Render Web Service.")
    return server

async def main():
    logger.info("==================================================")
    logger.info("Iniciando Bot de Control de Inventario y Producción")
    logger.info("==================================================")
    
    # Validar variables de entorno
    config.validate()

    # Inicializar las tablas de la base de datos de forma asíncrona
    logger.info("Inicializando tablas en la base de datos...")
    await init_db()
    logger.info("Base de datos lista y sincronizada.")

    # Iniciar servidor HTTP de salud si Render asigna la variable PORT
    health_server = await start_health_check_server()

    # Crear e iniciar el bot de Telegram
    telegram_app = create_telegram_application()

    logger.info("Bot en ejecución. Escuchando mensajes de Telegram (Polling mode)...")
    
    # Iniciar la aplicación en modo polling asíncrono
    async with telegram_app:
        await telegram_app.start()
        await telegram_app.updater.start_polling(drop_pending_updates=True)
        
        # Mantener el proceso vivo de forma asíncrona limpia
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Deteniendo el bot...")
        finally:
            if health_server:
                health_server.close()
                await health_server.wait_closed()
            await telegram_app.updater.stop()
            await telegram_app.stop()
            logger.info("Bot detenido correctamente.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Programa finalizado.")
