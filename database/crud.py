from datetime import date, datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    DailyProduction, InventoryWithdrawal, InitialStock, PhotoAudit, PRODUCT_CATALOG
)
from utils.helpers import get_peru_today, get_product_info, get_peru_now


async def upsert_production_records(
    session: AsyncSession,
    records: List[Dict[str, Any]]
) -> int:
    """
    Inserta o actualiza registros de producción diaria (UPSERT por clave (fecha, product_code)).
    Garantiza la deduplicación al procesar fotos acumulativas de la semana.
    """
    if not records:
        return 0

    count = 0
    for rec in records:
        rec_date = rec["date"]
        rec_code = rec["product_code"]
        rec_qty = rec["quantity"]
        rec_worked = rec.get("is_worked_day", True)

        stmt = select(DailyProduction).where(
            DailyProduction.date == rec_date,
            DailyProduction.product_code == rec_code
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.quantity = rec_qty
            existing.is_worked_day = rec_worked
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_prod = DailyProduction(
                date=rec_date,
                product_code=rec_code,
                quantity=rec_qty,
                is_worked_day=rec_worked,
                updated_at=datetime.now(timezone.utc)
            )
            session.add(new_prod)
        count += 1

    return count


async def record_withdrawal(
    session: AsyncSession,
    product_code: str,
    quantity: int,
    withdrawal_type: str = "MANUAL",
    customer_or_reason: Optional[str] = None,
    withdrawal_date: Optional[date] = None
) -> InventoryWithdrawal:
    """Registra un retiro/descuento de mercadería."""
    w_date = withdrawal_date or get_peru_today()
    withdrawal = InventoryWithdrawal(
        date=w_date,
        product_code=product_code.upper(),
        quantity=quantity,
        withdrawal_type=withdrawal_type,
        customer_or_reason=customer_or_reason,
        created_at=datetime.now(timezone.utc)
    )
    session.add(withdrawal)
    return withdrawal


async def set_initial_stock(
    session: AsyncSession,
    stock_dict: Dict[str, int]
) -> Dict[str, int]:
    """Establece el inventario inicial o base para los códigos de producto."""
    for code, qty in stock_dict.items():
        code_upper = code.upper()
        if code_upper not in PRODUCT_CATALOG:
            continue

        stmt = select(InitialStock).where(InitialStock.product_code == code_upper)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.quantity = qty
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_stock = InitialStock(
                product_code=code_upper,
                quantity=qty,
                updated_at=datetime.now(timezone.utc)
            )
            session.add(new_stock)

    return stock_dict


async def get_consolidated_inventory(session: AsyncSession) -> Dict[str, Dict[str, Any]]:
    """
    Calcula el inventario consolidado actual para cada producto del catálogo:
    Stock Neto = Inventario Inicial + Total Producido - Total Retirado
    """
    stmt_init = select(InitialStock.product_code, InitialStock.quantity)
    res_init = await session.execute(stmt_init)
    initial_map = {row[0]: row[1] for row in res_init.all()}

    stmt_prod = select(
        DailyProduction.product_code,
        func.coalesce(func.sum(DailyProduction.quantity), 0)
    ).group_by(DailyProduction.product_code)
    res_prod = await session.execute(stmt_prod)
    produced_map = {row[0]: row[1] for row in res_prod.all()}

    stmt_withd = select(
        InventoryWithdrawal.product_code,
        func.coalesce(func.sum(InventoryWithdrawal.quantity), 0)
    ).group_by(InventoryWithdrawal.product_code)
    res_withd = await session.execute(stmt_withd)
    withdrawn_map = {row[0]: row[1] for row in res_withd.all()}

    inventory = {}
    for code, meta in PRODUCT_CATALOG.items():
        initial = initial_map.get(code, 0)
        produced = produced_map.get(code, 0)
        withdrawn = withdrawn_map.get(code, 0)
        net_stock = initial + produced - withdrawn

        inventory[code] = {
            "name": meta["name"],
            "emoji": meta["emoji"],
            "initial": initial,
            "produced": produced,
            "withdrawn": withdrawn,
            "current_stock": net_stock
        }

    return inventory


async def get_recent_production(session: AsyncSession, limit_days: int = 7) -> List[Dict[str, Any]]:
    """Obtiene los registros de producción de los últimos N días registrados."""
    stmt_dates = select(DailyProduction.date).distinct().order_by(DailyProduction.date.desc()).limit(limit_days)
    res_dates = await session.execute(stmt_dates)
    recent_dates = [row[0] for row in res_dates.all()]

    if not recent_dates:
        return []

    stmt = select(DailyProduction).where(
        DailyProduction.date.in_(recent_dates)
    ).order_by(DailyProduction.date.desc(), DailyProduction.product_code)

    res = await session.execute(stmt)
    all_prods = res.scalars().all()

    grouped = {}
    for p in all_prods:
        d_str = p.date.strftime("%d-%m-%Y")
        if d_str not in grouped:
            grouped[d_str] = {
                "date": p.date,
                "date_str": d_str,
                "is_worked_day": p.is_worked_day,
                "items": {}
            }
        grouped[d_str]["items"][p.product_code] = p.quantity

    return list(grouped.values())


async def create_photo_audit(
    session: AsyncSession,
    telegram_file_id: str,
    telegram_user_id: int,
    extracted_summary: str
) -> PhotoAudit:
    """Registra la recepción de una foto para auditoría."""
    audit = PhotoAudit(
        telegram_file_id=telegram_file_id,
        telegram_user_id=telegram_user_id,
        extracted_summary=extracted_summary,
        status="PENDIENTE",
        created_at=get_peru_now()
    )
    session.add(audit)
    await session.flush()
    return audit


async def update_photo_audit_status(
    session: AsyncSession,
    audit_id: int,
    new_status: str
) -> None:
    """Actualiza el estado de una auditoría de foto (CONFIRMADO / DESCARTADO)."""
    stmt = select(PhotoAudit).where(PhotoAudit.id == audit_id)
    res = await session.execute(stmt)
    audit = res.scalar_one_or_none()
    if audit:
        audit.status = new_status


async def get_photo_audit_by_id(
    session: AsyncSession,
    audit_id: int
) -> Optional[PhotoAudit]:
    """Obtiene un registro de auditoría de foto por su ID."""
    stmt = select(PhotoAudit).where(PhotoAudit.id == audit_id)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def count_photos_today(session: AsyncSession, telegram_user_id: int) -> int:
    """Cuenta cuántas fotos ha enviado un usuario hoy en zona horaria de Perú."""
    today = get_peru_today()
    stmt = select(func.count(PhotoAudit.id)).where(
        PhotoAudit.telegram_user_id == telegram_user_id,
        func.date(PhotoAudit.created_at) == today
    )
    res = await session.execute(stmt)
    return res.scalar() or 0


async def get_full_historical_data(session: AsyncSession) -> Dict[str, Any]:
    """
    Obtiene todos los registros históricos de producción, retiros e inventario inicial
    para construir el reporte de Excel.
    """
    # 1. Obtener todas las producciones
    stmt_prod = select(DailyProduction).order_by(DailyProduction.date.asc(), DailyProduction.product_code)
    res_prod = await session.execute(stmt_prod)
    all_productions = res_prod.scalars().all()

    # 2. Obtener todos los retiros
    stmt_withd = select(InventoryWithdrawal).order_by(InventoryWithdrawal.date.asc(), InventoryWithdrawal.id.asc())
    res_withd = await session.execute(stmt_withd)
    all_withdrawals = res_withd.scalars().all()

    # 3. Obtener stock inicial
    stmt_init = select(InitialStock)
    res_init = await session.execute(stmt_init)
    all_initial = res_init.scalars().all()
    initial_map = {item.product_code: item.quantity for item in all_initial}

    return {
        "productions": all_productions,
        "withdrawals": all_withdrawals,
        "initial_stock": initial_map,
    }


async def get_recent_production_dates(session: AsyncSession, limit: int = 7) -> List[date]:
    """Obtiene las fechas más recientes que tienen registros de producción en orden descendente."""
    stmt = (
        select(DailyProduction.date)
        .distinct()
        .order_by(DailyProduction.date.desc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def reset_entire_database(session: AsyncSession) -> Dict[str, int]:
    """
    Resetea completamente la base de datos:
    - Borra registros de daily_production.
    - Borra registros de inventory_withdrawals.
    - Borra registros de photo_audit.
    - Reestablece initial_stock a 0 para los productos del catálogo (R, V, A, NC, N).
    Devuelve un diccionario con la cantidad de registros eliminados.
    """
    stmt_count_prod = select(func.count()).select_from(DailyProduction)
    prod_count = (await session.execute(stmt_count_prod)).scalar() or 0

    stmt_count_withd = select(func.count()).select_from(InventoryWithdrawal)
    withd_count = (await session.execute(stmt_count_withd)).scalar() or 0

    stmt_count_photo = select(func.count()).select_from(PhotoAudit)
    photo_count = (await session.execute(stmt_count_photo)).scalar() or 0

    # Ejecutar eliminaciones
    await session.execute(delete(DailyProduction))
    await session.execute(delete(InventoryWithdrawal))
    await session.execute(delete(PhotoAudit))

    # Reiniciar initial_stock a 0 para todos los productos del catálogo
    for code in PRODUCT_CATALOG.keys():
        stmt = select(InitialStock).where(InitialStock.product_code == code)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.quantity = 0
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_stock = InitialStock(
                product_code=code,
                quantity=0,
                updated_at=datetime.now(timezone.utc)
            )
            session.add(new_stock)

    await session.flush()

    return {
        "deleted_productions": prod_count,
        "deleted_withdrawals": withd_count,
        "deleted_photos": photo_count,
    }



