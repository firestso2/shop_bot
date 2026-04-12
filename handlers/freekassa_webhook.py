"""FreeKassa webhook — монтируется как sub-app в main.py."""
from aiohttp import web
from aiogram import Bot
from config import ADMIN_IDS, REFERRAL_PERCENT
from db.database import (
    mark_payment_paid, add_balance,
    get_referrer_id, add_ref_earned, log_action,
)
from utils.payments import freekassa_verify_webhook


async def fk_webhook_handler(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    try:
        params = dict(await request.post())
    except Exception:
        return web.Response(text="BAD", status=400)

    if not freekassa_verify_webhook(params):
        return web.Response(text="INVALID SIGN", status=403)

    order_id = params.get("MERCHANT_ORDER_ID", "")
    result   = await mark_payment_paid(order_id)
    if result is None:
        return web.Response(text="YES")

    user_id  = result["user_id"]
    credited = result["credited"]
    new_bal  = await add_balance(user_id, credited)
    await log_action(user_id, "topup_paid",
                     {"method": "freekassa", "credited": credited})

    ref_id = await get_referrer_id(user_id)
    if ref_id:
        bonus = round(credited * REFERRAL_PERCENT / 100, 4)
        await add_ref_earned(ref_id, bonus)
        try:
            await bot.send_message(ref_id,
                f"💸 Реферал пополнил баланс!\n🎁 Вам: <b>{bonus:.4f} $</b>")
        except Exception:
            pass

    try:
        await bot.send_message(user_id,
            f"✅ <b>Пополнено (FK)!</b>\n+{credited} $\nБаланс: {new_bal:.2f} $")
    except Exception:
        pass
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid,
                f"💳 FK пополнение\nID: {user_id}\n+{credited} $")
        except Exception:
            pass

    return web.Response(text="YES")


def create_fk_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/", fk_webhook_handler)
    return app
