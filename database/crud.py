from datetime import date, datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.models import (
    DailyProduction, InventoryWithdrawal, InitialStock, PhotoAudit, PRODUCT_CATALOG
)

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

        # Buscar si ya existe el registro para esa fecha y producto
        stmt = select(DailyProduction).where(
            DailyProduction.date == rec_date,
            DailyProduction.product_code == rec_code
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.quantity = rec_qty
            existing.is_worked_day = rec_worked
            existing.updated_at = datetime.utcnow()
        else:
            new_prod = DailyProduction(
                date=rec_date,
                product_code=rec_code,
                quantity=rec_qty,
                is_worked_day=rec_worked,
                updated_at=datetime.utcnow()
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
    """
    Registra un retiro/descuento de mercadería.
    """
    w_date = withdrawal_date or date.today()
    withdrawal = InventoryWithdrawal(
        date=w_date,
        product_code=product_code.upper(),
        quantity=quantity,
        withdrawal_type=withdrawal_type,
        customer_or_reason=customer_or_reason,
        created_at=datetime.utcnow()
    )
    session.add(withdrawal)
    return withdrawal

async def set_initial_stock(
    session: AsyncSession,
    stock_dict: Dict[str, int]
) -> Dict[str, int]:
    """
    Establece el inventario inicial o base para los códigos de producto.
    """
    for code, qty in stock_dict.items():
        code_upper = code.upper()
        if code_upper not in PRODUCT_CATALOG:
            continue
        
        stmt = select(InitialStock).where(InitialStock.product_code == code_upper)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        
        if existing:
            existing.quantity = qty
            existing.updated_at = datetime.utcnow()
        else:
            new_stock = InitialStock(
                product_code=code_upper,
                quantity=qty,
                updated_at=datetime.utcnow()
            )
            session.add(new_stock)
            
    return stock_dict

async def get_consolidated_inventory(session: AsyncSession) -> Dict[str, Dict[str, Any]]:
    """
    Calcula el inventario consolidado actual para cada producto del catálogo:
    Stock Neto = Inventario Inicial + Total Producido - Total Retirado
    """
    # 1. Obtener Inventario Inicial
    stmt_init = select(InitialStock.product_code, InitialStock.quantity)
    res_init = await session.execute(stmt_init)
    initial_map = {row[0]: row[1] for row in res_init.all()}

    # 2. Obtener Total Producido por Producto
    stmt_prod = select(
        DailyProduction.product_code,
        func.coalesce(func.sum(DailyProduction.quantity), 0)
    ).group_by(DailyProduction.product_code)
    res_prod = await session.execute(stmt_prod)
    produced_map = {row[0]: row[1] for row in res_prod.all()}

    # 3. Obtener Total Retirado por Producto
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
    """
    Obtiene los registros de producción de los últimos N días registrados.
    """
    # Obtener las fechas más recientes
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

    # Agrupar por fecha
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
        created_at=datetime.utcnow()
    )
    session.add(audit)
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
