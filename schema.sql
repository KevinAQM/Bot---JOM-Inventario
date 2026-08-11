-- ============================================================
-- SCRIPT DE INICIALIZACIÓN DE BASE DE DATOS (PostgreSQL & SQLite)
-- Bot de Gestión e Inventario de Producción Diaria en Campo
-- ============================================================

-- 1. Tabla de Producción Diaria por Fecha y Producto (UPSERT Key: date + product_code)
CREATE TABLE IF NOT EXISTS daily_production (
    date DATE NOT NULL,
    product_code VARCHAR(10) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    is_worked_day BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, product_code)
);

-- Index para búsquedas rápidas por fecha
CREATE INDEX IF NOT EXISTS idx_production_date ON daily_production(date);

-- 2. Tabla de Retiros / Salidas de Mercadería
CREATE TABLE IF NOT EXISTS inventory_withdrawals (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    product_code VARCHAR(10) NOT NULL,
    quantity INTEGER NOT NULL,
    withdrawal_type VARCHAR(30) NOT NULL DEFAULT 'MANUAL', -- 'MANUAL', 'CLIENTE_PIZARRA', 'AJUSTE'
    customer_or_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_withdrawals_product ON inventory_withdrawals(product_code);

-- 3. Tabla de Inventario Base Inicial
CREATE TABLE IF NOT EXISTS initial_stock (
    product_code VARCHAR(10) PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabla de Auditoría de Fotos de Pizarra
CREATE TABLE IF NOT EXISTS photo_audit (
    id SERIAL PRIMARY KEY,
    telegram_file_id TEXT NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    extracted_summary TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE', -- 'PENDIENTE', 'CONFIRMADO', 'DESCARTADO'
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Cargar catálogo inicial de productos con saldo inicial 0 por defecto
INSERT INTO initial_stock (product_code, quantity) VALUES
    ('R', 0),
    ('V', 0),
    ('A', 0),
    ('NC', 0),
    ('N', 0)
ON CONFLICT (product_code) DO NOTHING;
