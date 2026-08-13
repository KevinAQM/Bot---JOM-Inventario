import pytest
import pytest_asyncio
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from database.models import Base
from database.crud import (
    upsert_production_records, record_withdrawal, set_initial_stock,
    get_consolidated_inventory, create_photo_audit, reset_entire_database
)

@pytest_asyncio.fixture
async def test_db_session():
    """Crea una base de datos SQLite en memoria para pruebas aisladas."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()

@pytest.mark.asyncio
async def test_reset_entire_database(test_db_session):
    """
    Prueba que el reset limpie todas las tablas de producción, retiros y fotos,
    y reestablezca el stock inicial a 0.
    """
    session = test_db_session
    d1 = date(2026, 8, 1)

    # Insertar datos de prueba
    await set_initial_stock(session, {"R": 500, "V": 200, "A": 100})
    await upsert_production_records(session, [
        {"date": d1, "product_code": "R", "quantity": 150},
        {"date": d1, "product_code": "V", "quantity": 80},
    ])
    await record_withdrawal(session, "R", 50, "MANUAL", "Cliente Prueba")
    await create_photo_audit(session, "file_123", 999888, "Foto de prueba")
    await session.commit()

    # Verificar que existen datos antes del reset
    inv_before = await get_consolidated_inventory(session)
    assert inv_before["R"]["current_stock"] == 600  # 500 + 150 - 50

    # Ejecutar el reset total
    res = await reset_entire_database(session)
    await session.commit()

    assert res["deleted_productions"] == 2
    assert res["deleted_withdrawals"] == 1
    assert res["deleted_photos"] == 1

    # Verificar que el inventario consolidado esté 100% en 0
    inv_after = await get_consolidated_inventory(session)
    for code, info in inv_after.items():
        assert info["initial"] == 0
        assert info["produced"] == 0
        assert info["withdrawn"] == 0
        assert info["current_stock"] == 0
