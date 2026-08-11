import asyncio
import sys

# Configurar stdout para usar UTF-8 en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database.models import Base
from database.crud import (
    upsert_production_records, record_withdrawal, set_initial_stock,
    get_consolidated_inventory, count_photos_today, create_photo_audit,
    get_photo_audit_by_id, update_photo_audit_status
)
from services.schemas import AnalisisPizarra, CodigoProducto


async def test_crud_and_upsert():
    print("🧪 Ejecutando prueba de CRUD y UPSERT (Deduplicación)...")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        # Configurar inventario inicial
        await set_initial_stock(session, {"R": 500, "V": 200, "A": 100, "NC": 50, "N": 300})

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
        print("  ✅ Insert inicial correcto")

        # UPSERT: mismos datos no deben duplicar
        await upsert_production_records(session, rec1)
        await session.commit()

        inv2 = await get_consolidated_inventory(session)
        assert inv2["R"]["produced"] == 110, f"Deduplicación falló: Producido R = {inv2['R']['produced']}"
        assert inv2["R"]["current_stock"] == 610
        print("  ✅ Deduplicación UPSERT correcta")

        # Retiro
        await record_withdrawal(session, product_code="R", quantity=50, withdrawal_type="MANUAL", customer_or_reason="Prueba")
        await session.commit()

        inv3 = await get_consolidated_inventory(session)
        assert inv3["R"]["current_stock"] == 560, f"Retiro falló: Stock = {inv3['R']['current_stock']}"
        print("  ✅ Retiro correcto")

    await engine.dispose()
    print("✅ Prueba de CRUD y Deduplicación COMPLETADA EXITOSAMENTE.\n")


async def test_photo_audit_and_limit():
    print("🧪 Ejecutando prueba de Auditoría de Fotos y Límite Diario...")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        # Crear 3 auditorías de fotos
        for i in range(3):
            audit = await create_photo_audit(
                session, telegram_file_id=f"file_{i}", telegram_user_id=123456,
                extracted_summary=f'{{"days": [], "observations": "test {i}"}}'
            )
        await session.commit()

        # Verificar conteo diario
        count = await count_photos_today(session, 123456)
        assert count == 3, f"Esperado 3 fotos hoy, obtenido {count}"
        print("  ✅ Conteo de fotos diarias correcto (3)")

        # Verificar recuperación por ID
        audit = await get_photo_audit_by_id(session, 1)
        assert audit is not None, "Auditoría ID=1 no encontrada"
        assert audit.status == "PENDIENTE"
        print("  ✅ Recuperación de auditoría por ID correcta")

        # Verificar actualización de estado
        await update_photo_audit_status(session, 1, "CONFIRMADO")
        await session.commit()
        audit = await get_photo_audit_by_id(session, 1)
        assert audit.status == "CONFIRMADO"
        print("  ✅ Actualización de estado de auditoría correcta")

    await engine.dispose()
    print("✅ Prueba de Auditoría de Fotos COMPLETADA EXITOSAMENTE.\n")


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
    print("  ✅ Parsing de esquema correcto")

    # Verificar serialización JSON (para persistencia en BD)
    json_str = parsed.model_dump_json()
    restored = AnalisisPizarra.model_validate_json(json_str)
    assert len(restored.days) == 1
    assert restored.days[0].items[0].quantity == 110
    print("  ✅ Serialización/Deserialización JSON correcta")

    print("✅ Prueba de Esquemas Pydantic COMPLETADA EXITOSAMENTE.\n")


def test_build_db_records():
    print("🧪 Ejecutando prueba de _build_db_records...")
    from services.vision_service import _build_db_records

    data = {
        "days": [
            {
                "day_header": "L",
                "date_str": "20-07",
                "is_worked_day": True,
                "items": [
                    {"code": "R", "quantity": 110},
                    {"code": "V", "quantity": 94},
                ],
                "withdrawals": []
            },
            {
                "day_header": "M",
                "date_str": "21-07",
                "is_worked_day": False,
                "items": [],
                "withdrawals": []
            }
        ],
        "observations": None
    }
    analysis = AnalisisPizarra.model_validate(data)
    records = _build_db_records(analysis, 2026)

    # Día 1: 2 productos + 3 faltantes = 5 registros
    # Día 2: no laborado = 5 registros (todos a 0)
    assert len(records) == 10, f"Esperado 10 registros, obtenido {len(records)}"

    # Verificar que R tenga 110 en el día 1
    r_records = [r for r in records if r["product_code"] == "R" and r["date"] == date(2026, 7, 20)]
    assert len(r_records) == 1
    assert r_records[0]["quantity"] == 110
    print("  ✅ Construcción de registros BD correcta")

    # Verificar que el día no laborado tiene quantity=0
    day2_records = [r for r in records if r["date"] == date(2026, 7, 21)]
    assert all(r["quantity"] == 0 for r in day2_records)
    assert all(r["is_worked_day"] is False for r in day2_records)
    print("  ✅ Registros de día no laborado correctos")

    print("✅ Prueba de _build_db_records COMPLETADA EXITOSAMENTE.\n")


async def run_all_tests():
    test_pydantic_schemas()
    test_build_db_records()
    await test_crud_and_upsert()
    await test_photo_audit_and_limit()
    print("🎉 TODAS LAS PRUEBAS UNITARIAS PASARON CORRECTAMENTE (100% FUNCIONAL).")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
