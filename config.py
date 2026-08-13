import os
from typing import List
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env si existe
load_dotenv()

class Config:
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./inventario.db")
    
    # Límites de fotos diarias
    MAX_PHOTOS_PER_DAY_TECHNICAL: int = int(os.getenv("MAX_PHOTOS_PER_DAY_TECHNICAL", "20"))
    DISPLAYED_DAILY_LIMIT: int = int(os.getenv("DISPLAYED_DAILY_LIMIT", "5"))

    # Convierte la cadena separada por comas de IDs de Telegram en una lista de enteros
    _raw_users = os.getenv("ALLOWED_TELEGRAM_USERS", "")
    ALLOWED_TELEGRAM_USERS: List[int] = [
        int(uid.strip()) for uid in _raw_users.split(",") if uid.strip().isdigit()
    ]

    _raw_admins = os.getenv("ALLOWED_TELEGRAM_ADMIN", os.getenv("ALLOWED_TELEGRAM_USERS", ""))
    ALLOWED_TELEGRAM_ADMIN: List[int] = [
        int(uid.strip()) for uid in _raw_admins.split(",") if uid.strip().isdigit()
    ]

    @classmethod
    def validate(cls) -> None:
        """Verifica que las variables críticas estén presentes antes de iniciar el bot."""
        missing = []
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        
        if missing:
            print(f"⚠️ ADVERTENCIA: Faltan las siguientes variables de entorno: {', '.join(missing)}")
            print("Por favor, configura tu archivo .env utilizando .env.example como referencia.")

config = Config()
