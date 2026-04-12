"""
Фоновые задачи: автопроверка платежей, low stock, бэкап, автовозврат заказов.
"""
import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    ADMIN_IDS, LOW_STOCK_THRESHOLD,
    PAYMENT_CHECK_INTERVAL, BACKUP_DIR, BACKUP_INTERVAL_HOURS,
)
from db.database import (
    get_pending_cryptobot_payments, mark_payment_paid,
    add_balance, get_referrer_id, add_ref_earned,
    get_low_stock_products, get_stock_count,
    get_orders_past_deadline, update_order_status, log_action,
)
from utils.payments import cryptobot_get_invoice

log = logging.getLogger(__name__)

_notified_low: set[int] = set()


# ════════════════════════════════════════════════════════════════════════════
#  АВТОПРОВЕРКА ПЛАТЕЖЕЙ
# ════════════════════════════════════════════════════════════════════════════

async def auto_check_payments(bot: Bot) -> None:
    try:
        pending = await get_pending_cryptobot_payments()
        for p in pending:
            try:
                invoice = await cryptobot_get_invoice(int(p["external_id"]))
                if not invoice or invoice["status"] != "paid":
                    continue

                result = await mark_payment_paid(p["external_id"])
                if not result:
                    continue

                user_id  = result["user_id"]
                credited = result["credited"]
                new_bal  = await add_balance(user_id, credited)

                from config import REFERRAL_PERCENT
                ref_id = await get_referrer_id(user_id)
                if ref_id:
                    bonus = round(credited * REFERRAL_PERCENT / 100, 4)
                    await add_ref_earned(ref_id, bonus)
                    try:
                        await bot.send_message(
                            ref_id,
                            f"💸 Ваш реферал пополнил баланс!\n🎁 Вам: <b>{bonus:.4f} $</b>"
                        )
                    except Exception:
                        pass

                await log_action(user_id, "auto_topup",
                                 {"credited": credited, "ext_id": p["external_id"]})

                await bot.send_message(
                    user_id,
                    f"✅ <b>Баланс пополнен автоматически!</b>\n"
                    f"💰 +{credited} $\nБаланс: <b>{new_bal:.2f} $</b>"
                )
                for aid in ADMIN_IDS:
                    try:
                        await bot.send_message(
                            aid, f"💳 Автопополнение\nID: {user_id}\n+{credited} $"
                        )
                    except Exception:
                        pass
            except Exception as e:
                log.warning(f"Auto-check error {p['external_id']}: {e}")
    except Exception as e:
        log.error(f"auto_check_payments: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  АВТОВОЗВРАТ ПРОСРОЧЕННЫХ ЗАКАЗОВ
# ════════════════════════════════════════════════════════════════════════════

async def auto_cancel_expired_orders(bot: Bot) -> None:
    """
    Находит заказы (waiting_confirm или in_work) у которых истёк дедлайн.
    Возвращает средства, меняет статус на cancelled.
    """
    try:
        expired = await get_orders_past_deadline()
        for order in expired:
            try:
                total = float(order["total"])
                await add_balance(order["user_id"], total)
                await update_order_status(order["order_code"], "cancelled")
                await log_action(None, "auto_cancel",
                                 {"order_code": order["order_code"], "total": total})

                # Уведомляем покупателя
                try:
                    await bot.send_message(
                        order["user_id"],
                        f"↩️ Заказ <code>{order['order_code']}</code> отменён автоматически "
                        f"(истёк дедлайн).\n"
                        f"Средства <b>{total:.2f} $</b> возвращены на баланс.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

                # Уведомляем администраторов
                for aid in ADMIN_IDS:
                    try:
                        await bot.send_message(
                            aid,
                            f"⏰ <b>Автовозврат</b>\n"
                            f"Заказ <code>{order['order_code']}</code> отменён по дедлайну.\n"
                            f"Возвращено: {total:.2f} $ пользователю ID: {order['user_id']}",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
            except Exception as e:
                log.warning(f"auto_cancel order {order.get('order_code')}: {e}")
    except Exception as e:
        log.error(f"auto_cancel_expired_orders: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  LOW STOCK
# ════════════════════════════════════════════════════════════════════════════

async def check_low_stock(bot: Bot) -> None:
    try:
        low = await get_low_stock_products(LOW_STOCK_THRESHOLD)
        for p in low:
            if p["id"] in _notified_low:
                continue
            _notified_low.add(p["id"])
            for aid in ADMIN_IDS:
                try:
                    await bot.send_message(
                        aid,
                        f"⚠️ <b>Мало товара!</b>\n"
                        f"📦 {p['name']}\nОстаток: <b>{p['stock']} шт.</b>"
                    )
                except Exception:
                    pass

        notified_copy = set(_notified_low)
        for prod_id in notified_copy:
            count = await get_stock_count(prod_id)
            if count > LOW_STOCK_THRESHOLD:
                _notified_low.discard(prod_id)
    except Exception as e:
        log.error(f"check_low_stock: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  БЭКАП
# ════════════════════════════════════════════════════════════════════════════

async def backup_database(bot: Bot) -> None:
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BACKUP_DIR, f"backup_{ts}.sql")

        from config import DB_DSN
        ret = os.system(f'pg_dump "{DB_DSN}" > "{path}"')
        if ret != 0:
            log.error("pg_dump failed")
            return

        size_kb = os.path.getsize(path) // 1024
        for aid in ADMIN_IDS:
            try:
                with open(path, "rb") as f:
                    await bot.send_document(
                        aid,
                        document=("backup.sql", f),
                        caption=f"💾 Бэкап БД\n🕐 {ts}\n📁 {size_kb} KB"
                    )
            except Exception as e:
                log.warning(f"Backup send to {aid}: {e}")

        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(".sql")]
        )
        for old in backups[:-10]:
            os.remove(os.path.join(BACKUP_DIR, old))
    except Exception as e:
        log.error(f"backup_database: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  ИНИЦИАЛИЗАЦИЯ
# ════════════════════════════════════════════════════════════════════════════

def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        auto_check_payments, "interval",
        seconds=PAYMENT_CHECK_INTERVAL,
        kwargs={"bot": bot}, id="auto_check", max_instances=1,
    )
    scheduler.add_job(
        auto_cancel_expired_orders, "interval",
        minutes=5,
        kwargs={"bot": bot}, id="auto_cancel", max_instances=1,
    )
    scheduler.add_job(
        check_low_stock, "interval",
        minutes=10,
        kwargs={"bot": bot}, id="low_stock", max_instances=1,
    )
    scheduler.add_job(
        backup_database, "interval",
        hours=BACKUP_INTERVAL_HOURS,
        kwargs={"bot": bot}, id="backup", max_instances=1,
    )
    return scheduler
