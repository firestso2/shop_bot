"""
Глобальный пул соединений PostgreSQL.
Инициализируется один раз в main.py, используется везде.
"""
import asyncpg
from config import DB_DSN

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=10)


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool not initialized. Call init_pool() first.")
    return _pool


async def close_pool() -> None:
    if _pool:
        await _pool.close()
