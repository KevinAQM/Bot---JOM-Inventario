import asyncio
import sys
import io

# Configurar stdout para usar UTF-8 en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database.models import Base
from database.crud import (
    upsert_production_records, record_withdrawal, set_initial_stock, get_consolidated_inventory
)
from services.schemas import AnalisisPizarra, CodigoProducto

async def test_crud_and_upsert():
    print("🧪 Ejecutando prueba de CRUD y UPSERT (Deduplicación)...")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        # 1. Establecer stock inicial
        await set_initial_stock(session, {"R": 500, "V": 200, "A": 100, "NC": 50, "N": 300})
        
        # 2. Cargar registros del lunes (20-07-2026): R-110, V-94, A-18, NC-63
        d1 = date(2026, 7, 20)
        rec1 = [
            {"date": d1, "product_code": "R", "quantity": 110, "is_worked_day": True},
            {"date": d1, "product_code": "V", "quantity": 94, "is_worked_day": True},
            {"date": d1, "product_code": "A", "quantity": 18, "is_worked_day": True},
            {"date": d1, "product_code": "NC", "quantity": 63, "is_worked_day": True},
        ]
        await upsert_production_records(session, rec1)
        await session.commit()

        inv1 = await get_consolidated_inventory(session)
        assert inv1["R"]["current_stock"] == 610, f"Esperado 610, obtenido {inv1['R']['current_stock']}"
        assert inv1["V"]["current_stock"] == 294, f"Esperado 294, obtenido {inv1['V']['current_stock']}"

        # 3. Segunda carga (Simulación de foto enviada el viernes que vuelve a incluir el lunes)
        # La deduplicación debe evitar sumar 110 nuevamente
        await upsert_production_records(session, rec1)
        await session.commit()

        inv2 = await get_consolidated_inventory(session)
        assert inv2["R"]["produced"] == 110, f"Deduplicación falló: Producido R = {inv2['R']['produced']}"
        assert inv2["R"]["current_stock"] == 610

        # 4. Probar retiro manual (/retiro)
        await record_withdrawal(session, product_code="R", quantity=50, withdrawal_type="MANUAL", customer_or_reason="Prueba")
        await session.commit()

        inv3 = await get_consolidated_inventory(session)
        # 500 (base) + 110 (producido) - 50 (retirado) = 560
        assert inv3["R"]["current_stock"] == 560, f"Retiro falló: Stock = {inv3['R']['current_stock']}"

    await engine.dispose()
    print("✅ Prueba de CRUD y Deduplicación COMPLETADA EXITOSAMENTE.")

def test_pydantic_schemas():
    print("🧪 Ejecutando prueba de Esquemas Pydantic (Structured Output)...")
    data = {
        "days": [
            {
                "day_header": "L",
                "date_str": "20-07",
                "is_worked_day": True,
                "items": [
                    {"code": "R", "quantity": 110},
                    {"code": "V", "quantity": 94},
                    {"code": "A", "quantity": 18},
                    {"code": "NC", "quantity": 63}
                ],
                "withdrawals": []
            }
        ],
        "observations": "Foto clara"
    }
    parsed = AnalisisPizarra.model_validate(data)
    assert len(parsed.days) == 1
    assert parsed.days[0].items[0].code == CodigoProducto.ROJO
    assert parsed.days[0].items[0].quantity == 110
    print("✅ Prueba de Esquemas Pydantic COMPLETADA EXITOSAMENTE.")

async def run_all_tests():
    test_pydantic_schemas()
    await test_crud_and_upsert()
    print("\n🎉 TODAS LAS PRUEBAS UNITARIAS PASARON CORRECTAMENTE (100% FUNCIONAL).")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
