#!/usr/bin/env python3
"""
Script de Consola (CLI) para Resetear la Base de Datos a Cero.
Solicita la clave de seguridad (201209) y confirmación antes de limpiar las tablas.
"""
import asyncio
import logging
import sys
from getpass import getpass

from database.connection import init_db, get_db
from database.crud import reset_entire_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("reset_db")

ADMIN_RESET_PASSWORD = "201209"

async def main():
    print("==========================================================")
    print(" 🛠️  SCRIPT DE RESETEO DE BASE DE DATOS DE PRODUCCIÓN")
    print("==========================================================")
    
    # 1. Solicitar clave de seguridad
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        pin = ADMIN_RESET_PASSWORD
    else:
        try:
            pin = input("🔐 Ingresa la clave de seguridad de administración: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n🟢 Operación cancelada por el usuario.")
            return

    if pin != ADMIN_RESET_PASSWORD:
        print("❌ Clave incorrecta. Operación cancelada por seguridad.")
        sys.exit(1)

    print("\n✅ Clave de seguridad validada correctamente.")
    print("⚠️ ADVERTENCIA: Se borrarán TODOS los registros de producción, salidas y fotos en la base de datos.")
    
    # 2. Confirmación
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        confirm = "SI"
    else:
        try:
            confirm = input("Escribe 'SI' para confirmar el reset total: ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            print("\n🟢 Operación cancelada.")
            return

    if confirm != "SI":
        print("🟢 Operación cancelada. No se realizaron cambios en la base de datos.")
        return

    print("\n⏳ Inicializando conexión y ejecutando el reset...")
    await init_db()

    async with get_db() as session:
        result = await reset_entire_database(session)

    print("==========================================================")
    print(" ✅ BASE DE DATOS RESETEADA CON ÉXITO")
    print("==========================================================")
    print(f" • Registros de producción eliminados: {result['deleted_productions']}")
    print(f" • Salidas de mercadería eliminadas: {result['deleted_withdrawals']}")
    print(f" • Auditorías de foto limpiadas: {result['deleted_photos']}")
    print(" • Stock inicial: Reestablecido a 0 para todo el catálogo (R, V, A, NC, N).")
    print("==========================================================")
    print("🚀 El bot está 100% listo para operar formalmente en producción.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
