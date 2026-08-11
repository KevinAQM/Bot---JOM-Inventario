from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import config
from database.models import Base

# Soporte para PostgreSQL y SQLite de forma asíncrona
db_url = config.DATABASE_URL
connect_args = {}

# Adaptar el esquema de conexión para asyncpg
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+asyncpg://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Si se usa PostgreSQL con asyncpg (Neon/Supabase), corregir el parámetro sslmode
if "asyncpg" in db_url:
    parsed = urlparse(db_url)
    query_params = parse_qs(parsed.query)
    
    # asyncpg no acepta 'sslmode' en la query string, usa connect_args={"ssl": ...}
    if "sslmode" in query_params:
        sslmode_val = query_params.pop("sslmode")[0]
        new_query = urlencode(query_params, doseq=True)
        db_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        if sslmode_val in ("require", "verify-ca", "verify-full", "prefer"):
            connect_args["ssl"] = "require"
    elif "neon.tech" in db_url or "supabase" in db_url:
        connect_args["ssl"] = "require"

# Configuración robusta del pool de conexiones para Serverless DB (Neon.tech)
engine_kwargs = {
    "echo": False,
    "future": True,
    "connect_args": connect_args,
}

if not db_url.startswith("sqlite"):
    engine_kwargs.update({
        "pool_pre_ping": True,     # Verifica que la conexión con Neon esté viva antes de cada consulta
        "pool_recycle": 280,       # Recicla conexiones inactivas cada 4.6 min (evita desconexiones silenciosas de Neon)
        "pool_size": 5,            # Tamaño del pool
        "max_overflow": 10,        # Exceso máximo
        "pool_timeout": 30,        # Tiempo de espera por conexión
    })
else:
    engine_kwargs.update({
        "pool_pre_ping": True,
    })

engine = create_async_engine(db_url, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    """Inicializa la estructura de tablas en la base de datos si no existen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@asynccontextmanager
async def get_db():
    """Context manager para obtener sesiones de base de datos asíncronas de forma segura."""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
