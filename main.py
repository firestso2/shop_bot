"""
Точка входа.
- Polling mode (вместо webhook) — работает на любом хостинге без домена
- Redis FSM Storage с TTL
- PostgreSQL pool
- APScheduler для фоновых задач
"""
import asyncio
import logging
import logging.handlers
 
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
 
from config import (
    BOT_TOKEN,
    REDIS_DSN, FSM_TTL_SEC, LOG_FILE,
)
from db.pool import init_pool, close_pool
from db.migrations import run_migrations
from db.pool import get_pool
from handlers.start import router as start_router
from handlers.shop import router as shop_router
from handlers.balance import router as balance_router
from handlers.admin import router as admin_router
from handlers.p2p import router as p2p_router
from services.scheduler import setup_scheduler
 
 
def setup_logging():
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
 
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
 
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
 
 
log = logging.getLogger(__name__)
 
 
async def main() -> None:
    setup_logging()
 
    # ── PostgreSQL ─────────────────────────────────────────────────────────
    await init_pool()
    pool = get_pool()
    await run_migrations(pool)
    log.info("Database ready.")
 
    # ── Redis FSM storage с TTL ────────────────────────────────────────────
    storage = RedisStorage.from_url(
        REDIS_DSN,
        key_builder=DefaultKeyBuilder(with_bot_id=True, with_destiny=True),
        state_ttl=FSM_TTL_SEC,
        data_ttl=FSM_TTL_SEC,
    )
 
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher(storage=storage)
 
    # Роутеры — порядок важен!
    dp.include_router(start_router)
    dp.include_router(p2p_router)    # P2P перехват ПЕРЕД shop
    dp.include_router(shop_router)
    dp.include_router(balance_router)
    dp.include_router(admin_router)
 
    # ── Scheduler ─────────────────────────────────────────────────────────
    scheduler = setup_scheduler(bot)
    scheduler.start()
    log.info("Scheduler started.")
 
    # Сбрасываем старый webhook если был
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Starting polling...")
 
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await close_pool()
        await bot.session.close()
        log.info("Bot stopped.")
 
 
if __name__ == "__main__":
    asyncio.run(main())
