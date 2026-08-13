import pytest
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database.models import Base
from database.crud import (
    upsert_production_records, get_recent_production_dates, get_consolidated_inventory
)


@pytest.mark.asyncio
async def test_get_recent_production_dates_and_edit():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        d1 = date(2026, 7, 20)
        d2 = date(2026, 7, 21)

        # Insertar registros iniciales
        rec1 = [
            {"date": d1, "product_code": "R", "quantity": 100, "is_worked_day": True},
            {"date": d2, "product_code": "V", "quantity": 50, "is_worked_day": True},
        ]
        await upsert_production_records(session, rec1)
        await session.commit()

        # Verificar fechas recientes
        recent = await get_recent_production_dates(session, limit=7)
        assert len(recent) == 2
        assert recent[0] == d2  # Orden descendente
        assert recent[1] == d1

        # Editar manualmente la cantidad del día 1 (Rojo -> de 100 a 120)
        edit_rec = [
            {"date": d1, "product_code": "R", "quantity": 120, "is_worked_day": True}
        ]
        await upsert_production_records(session, edit_rec)
        await session.commit()

        inv = await get_consolidated_inventory(session)
        assert inv["R"]["produced"] == 120
        assert inv["R"]["current_stock"] == 120

    await engine.dispose()
