import asyncio
import logging
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
            await telegram_app.updater.stop()
            await telegram_app.stop()
            logger.info("Bot detenido correctamente.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Programa finalizado.")
