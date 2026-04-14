"""
Точка входа.
- Webhook mode для минимальной задержки
- Redis FSM Storage с TTL
- PostgreSQL pool
- APScheduler для фоновых задач
"""
import logging
import logging.handlers
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import (
    BOT_TOKEN, WEBHOOK_BASE_URL, WEBHOOK_BOT_PATH,
    WEBHOOK_HOST, WEBHOOK_PORT,
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


async def on_startup(bot: Bot) -> None:
    webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_BOT_PATH}"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    log.info(f"Webhook set: {webhook_url}")


async def on_shutdown(bot: Bot) -> None:
    await bot.delete_webhook()
    await close_pool()
    log.info("Bot stopped.")


def main() -> None:
    setup_logging()

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

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Роутеры — порядок важен!
    dp.include_router(start_router)
    dp.include_router(p2p_router)
    dp.include_router(shop_router)
    dp.include_router(balance_router)
    dp.include_router(admin_router)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_BOT_PATH)
    setup_application(app, dp, bot=bot)

    async def _on_startup_pg(app):
        await init_pool()
        pool = get_pool()
        await run_migrations(pool)
        log.info("Database ready.")
        scheduler = setup_scheduler(bot)
        scheduler.start()
        app["scheduler"] = scheduler
        log.info("Scheduler started.")

    async def _on_shutdown_pg(app):
        scheduler = app.get("scheduler")
        if scheduler:
            scheduler.shutdown(wait=False)

    app.on_startup.append(_on_startup_pg)
    app.on_shutdown.append(_on_shutdown_pg)

    log.info(f"Starting webhook server on {WEBHOOK_HOST}:{WEBHOOK_PORT}")
    web.run_app(app, host=WEBHOOK_HOST, port=WEBHOOK_PORT)


if __name__ == "__main__":
    main()
