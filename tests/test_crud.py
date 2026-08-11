import pytest
import pytest_asyncio
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from database.models import Base
from database.crud import (
    upsert_production_records, record_withdrawal, set_initial_stock, get_consolidated_inventory
)

@pytest_asyncio.fixture
async def test_db_session():
    """Crea una base de datos SQLite en memoria para pruebas aisladas y rápidas."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()

@pytest.mark.asyncio
async def test_inventory_upsert_and_deduplication(test_db_session):
    """
    Prueba que los registros de producción se ingresen correctamente y que
    la re-subida de una foto no duplique inventarios (UPSERT por fecha).
    """
    session = test_db_session
    d1 = date(2026, 7, 20)

    # 1. Establecer inventario inicial
    await set_initial_stock(session, {"R": 500, "V": 200})

    # 2. Primera carga (Foto del lunes): R-110, V-94
    rec1 = [
        {"date": d1, "product_code": "R", "quantity": 110, "is_worked_day": True},
        {"date": d1, "product_code": "V", "quantity": 94, "is_worked_day": True},
    ]
    await upsert_production_records(session, rec1)
    await session.commit()

    inv1 = await get_consolidated_inventory(session)
    assert inv1["R"]["produced"] == 110
    assert inv1["R"]["current_stock"] == 610  # 500 + 110
    assert inv1["V"]["current_stock"] == 294  # 200 + 94

    # 3. Segunda carga (Foto del viernes que incluye el lunes nuevamente con corregidos o iguales valores)
    # R se mantiene en 110, V se corrige a 94. No debe duplicar a 220 ni 188.
    await upsert_production_records(session, rec1)
    await session.commit()

    inv2 = await get_consolidated_inventory(session)
    assert inv2["R"]["produced"] == 110
    assert inv2["R"]["current_stock"] == 610

@pytest.mark.asyncio
async def test_withdrawals_calculation(test_db_session):
    """Prueba que los retiros manuales descuenten adecuadamente el inventario."""
    session = test_db_session
    d1 = date(2026, 7, 20)

    await set_initial_stock(session, {"R": 100})
    await upsert_production_records(session, [{"date": d1, "product_code": "R", "quantity": 50}])
    
    # Descontar 30 unidades
    await record_withdrawal(session, product_code="R", quantity=30, withdrawal_type="MANUAL", customer_or_reason="Prueba")
    await session.commit()

    inv = await get_consolidated_inventory(session)
    # Stock Neto = 100 (base) + 50 (producido) - 30 (retirado) = 120
    assert inv["R"]["current_stock"] == 120
