from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, Boolean, Date, DateTime, Text, BigInteger, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class DailyProduction(Base):
    """
    Registro diario de producción por fecha y código de producto.
    Usa la clave compuesta (fecha, product_code) para facilitar UPSERT.
    """
    __tablename__ = "daily_production"

    date = Column(Date, primary_key=True, nullable=False)
    product_code = Column(String(10), primary_key=True, nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    is_worked_day = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('date', 'product_code', name='uq_date_product'),
    )

class InventoryWithdrawal(Base):
    """
    Registro de salidas/retiros de mercadería (manuales o extraídos de la pizarra).
    """
    __tablename__ = "inventory_withdrawals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, default=date.today)
    product_code = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    withdrawal_type = Column(String(30), nullable=False, default="MANUAL")  # MANUAL, CLIENTE_PIZARRA, AJUSTE
    customer_or_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class InitialStock(Base):
    """
    Inventario inicial base o ajustes manuales por producto.
    """
    __tablename__ = "initial_stock"

    product_code = Column(String(10), primary_key=True, nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class PhotoAudit(Base):
    """
    Auditoría de imágenes procesadas mediante Telegram.
    """
    __tablename__ = "photo_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_file_id = Column(Text, nullable=False)
    telegram_user_id = Column(BigInteger, nullable=False)
    extracted_summary = Column(Text, nullable=True)
    status = Column(String(20), default="PENDIENTE")  # PENDIENTE, CONFIRMADO, DESCARTADO
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

# Mapeo descriptivo para la interfaz de usuario en español
PRODUCT_CATALOG = {
    "R": {"name": "Rojo", "emoji": "🔴"},
    "V": {"name": "Verde", "emoji": "🟢"},
    "A": {"name": "Amarillo", "emoji": "🟡"},
    "NC": {"name": "No Color", "emoji": "⚪"},
    "N": {"name": "Negro", "emoji": "⬛"},
}
