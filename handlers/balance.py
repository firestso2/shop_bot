"""
Профиль, баланс, пополнение (CryptoBot / Stars / FreeKassa).
Курсы валют берутся строго из config.py — никаких внешних API.
"""
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, User, LabeledPrice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import (
    MIN_TOPUP, REFERRAL_PERCENT, ADMIN_IDS,
    OWNER_USERNAME, SUPPORT_USERNAME, REVIEW_CHANNEL,
    FREEKASSA_RATE_RUB_PER_USD, STARS_USD_PER_STAR,
)
from db.database import (
    get_user, add_balance, get_referrer_id, add_ref_earned,
    create_payment, mark_payment_paid, log_action,
    get_user_orders, get_orders_count,
)
from keyboards.user_kb import (
    main_kb, balance_kb, topup_go_kb, cancel_kb,
    support_kb, reputation_kb, orders_nav_kb,
)
from utils.payments import (
    cryptobot_create_invoice, cryptobot_get_invoice,
    freekassa_generate_url,
)

router = Router()

ORDERS_PAGE_SIZE = 5


class TopupState(StatesGroup):
    amount_crypto = State()
    amount_fk     = State()
    amount_stars  = State()


# ════════════════════════════════════════════════════════════════════════════
#  ПРОФИЛЬ
# ════════════════════════════════════════════════════════════════════════════

async def send_profile(target: Message, tg_user: User, bot: Bot,
                       offset: int = 0) -> None:
    user = await get_user(tg_user.id)
    if not user:
        await target.answer("Сначала запустите бота: /start")
        return

    uname    = f"@{tg_user.username}" if tg_user.username else tg_user.first_name
    balance  = float(user["balance"])
    ref_e    = float(user["ref_earned"])
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={tg_user.id}"

    total_orders = await get_orders_count(tg_user.id)
    orders       = await get_user_orders(tg_user.id,
                                         limit=ORDERS_PAGE_SIZE, offset=offset)

    status_map = {
        "pending":         "⏳ ожидает",
        "waiting_confirm": "⏳ подтверждение",
        "in_work":         "🔄 в работе",
        "completed":       "✅ выполнен",
        "cancelled":       "❌ отменён",
    }

    orders_text = ""
    if orders:
        orders_text = "\n\n📋 <b>История заказов:</b>\n"
        for o in orders:
            s = status_map.get(o["status"], o["status"])
            orders_text += (
                f"• <code>{o['order_code']}</code> — "
                f"{o['product_name']} × {o['quantity']} — "
                f"{float(o['total']):.2f}$ — {s}\n"
            )

    page_info = ""
    if total_orders > ORDERS_PAGE_SIZE:
        cur  = offset // ORDERS_PAGE_SIZE + 1
        maxp = (total_orders - 1) // ORDERS_PAGE_SIZE + 1
        page_info = f"\n<i>Стр. {cur}/{maxp}</i>"

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"❤️ Имя: {uname}\n"
        f"🔑 ID: <code>{tg_user.id}</code>\n"
        f"💰 Баланс: <b>{balance:.2f} $</b>\n\n"
        f"💸 Заработано с рефералов: <b>{ref_e:.2f} $</b>\n"
        f"📦 Всего заказов: <b>{total_orders}</b>\n\n"
        f"🔗 Реф. ссылка:\n<code>{ref_link}</code>\n"
        f"<i>Вы получаете {REFERRAL_PERCENT}% с пополнений рефералов.</i>"
        f"{orders_text}{page_info}"
    )

    nav_kb = orders_nav_kb(offset, total_orders, ORDERS_PAGE_SIZE)
    await target.answer(
        text,
        parse_mode="HTML",
        reply_markup=nav_kb if nav_kb.inline_keyboard else None,
    )


@router.message(F.text == "👤 Профиль")
async def profile(message: Message, bot: Bot):
    await send_profile(message, message.from_user, bot, offset=0)


@router.callback_query(F.data.startswith("orders_page_"))
async def orders_page(call: CallbackQuery, bot: Bot):
    offset = int(call.data[12:])
    await send_profile(call.message, call.from_user, bot, offset=offset)
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  МЕНЮ БАЛАНСА
# ════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "💰 Баланс")
async def balance_menu(message: Message):
    user = await get_user(message.from_user.id)
    bal  = float(user["balance"]) if user else 0.0
    await message.answer(
        f"💰 <b>Баланс: {bal:.2f} $</b>\n\n"
        f"Минимум: {MIN_TOPUP} $\n\n"
        f"💱 Курсы:\n"
        f"  • FreeKassa: {FREEKASSA_RATE_RUB_PER_USD:.0f} ₽ = 1 $\n"
        f"  • Stars: {STARS_USD_PER_STAR} $ за 1 ⭐\n\n"
        f"<i>Пополнение в ₽ напрямую — через @{OWNER_USERNAME}</i>",
        parse_mode="HTML",
        reply_markup=balance_kb(),
    )


# ════════════════════════════════════════════════════════════════════════════
#  CRYPTOBOT
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "topup_crypto")
async def topup_crypto_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer(
        f"💳 <b>CryptoBot (USDT)</b>\n\n"
        f"Введите сумму в $ (мин. {MIN_TOPUP} $).\n"
        f"<i>Комиссия +3%: зачисляется ровно введённая сумма.</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await state.set_state(TopupState.amount_crypto)
    await call.answer()


@router.message(TopupState.amount_crypto)
async def topup_crypto_amount(message: Message, state: FSMContext):
    try:
        amount = round(float(message.text.replace(",", ".")), 2)
        if amount < MIN_TOPUP:
            raise ValueError
    except ValueError:
        await message.answer(f"❌ Введите сумму от {MIN_TOPUP} $!")
        return

    invoice = await cryptobot_create_invoice(amount, f"Пополнение {amount} $")
    if not invoice:
        await message.answer("❌ Ошибка. Попробуйте позже.")
        await state.clear()
        return

    charge = round(amount / 0.97, 2)
    ext_id = str(invoice["invoice_id"])
    await create_payment(message.from_user.id, charge, amount, "cryptobot", ext_id)
    await log_action(message.from_user.id, "topup_initiated",
                     {"method": "cryptobot", "amount": amount})
    await state.clear()

    await message.answer(
        f"💳 К оплате: <b>{charge} USDT</b>\n"
        f"✅ Будет зачислено: <b>{amount} $</b>\n"
        f"<i>Зачислится автоматически.</i>",
        parse_mode="HTML",
        reply_markup=topup_go_kb(
            pay_url=invoice["pay_url"],
            check_data=f"cb_check_{ext_id}_{int(amount * 100)}",
        ),
    )


@router.callback_query(F.data.startswith("cb_check_"))
async def cryptobot_check_manual(call: CallbackQuery, bot: Bot):
    parts  = call.data.split("_")
    ext_id = parts[2]

    invoice = await cryptobot_get_invoice(int(ext_id))
    if not invoice:
        await call.answer("Ошибка проверки.", show_alert=True)
        return

    if invoice["status"] == "paid":
        result = await mark_payment_paid(ext_id)
        if not result:
            await call.answer("✅ Уже зачислено!", show_alert=True)
            return
        user_id  = result["user_id"]
        credited = result["credited"]
        new_bal  = await add_balance(user_id, credited)
        await _pay_ref_bonus(bot, user_id, credited)
        await log_action(user_id, "topup_paid",
                         {"method": "cryptobot", "credited": credited})
        await call.message.answer(
            f"✅ <b>Пополнено!</b>\n+{credited} $\nБаланс: <b>{new_bal:.2f} $</b>",
            parse_mode="HTML",
        )
        await call.answer("✅", show_alert=True)
        for aid in ADMIN_IDS:
            try:
                uname = (f"@{call.from_user.username}"
                         if call.from_user.username else str(user_id))
                await bot.send_message(aid,
                    f"💳 Пополнение (CB)\n{uname}\n+{credited} $")
            except Exception:
                pass
    elif invoice["status"] == "expired":
        await call.answer("❌ Счёт истёк.", show_alert=True)
    else:
        await call.answer(
            "⏳ Ещё не оплачено. Зачислится автоматически.",
            show_alert=True
        )


# ════════════════════════════════════════════════════════════════════════════
#  FREEKASSA
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "topup_fk")
async def topup_fk_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer(
        f"🏦 <b>FreeKassa (₽)</b>\n\n"
        f"Введите сумму в рублях (мин. 80 ₽).\n"
        f"<i>Курс: {FREEKASSA_RATE_RUB_PER_USD:.0f} ₽ = 1 $</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await state.set_state(TopupState.amount_fk)
    await call.answer()


@router.message(TopupState.amount_fk)
async def topup_fk_amount(message: Message, state: FSMContext):
    try:
        amount_rub = round(float(message.text.replace(",", ".")), 2)
        if amount_rub < 80:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите сумму от 80 ₽!")
        return

    amount_usd = round(amount_rub / FREEKASSA_RATE_RUB_PER_USD, 4)
    order_id   = f"fk_{message.from_user.id}_{uuid.uuid4().hex[:8]}"

    await create_payment(message.from_user.id, amount_rub, amount_usd,
                         "freekassa", order_id)
    await log_action(message.from_user.id, "topup_initiated",
                     {"method": "freekassa", "rub": amount_rub, "usd": amount_usd})
    await state.clear()

    pay_url = freekassa_generate_url(order_id, amount_rub)
    await message.answer(
        f"🏦 К оплате: <b>{amount_rub} ₽</b>\n"
        f"✅ Будет зачислено: ≈<b>{amount_usd:.2f} $</b>",
        parse_mode="HTML",
        reply_markup=topup_go_kb(pay_url=pay_url, check_data="fk_manual_check"),
    )


@router.callback_query(F.data == "fk_manual_check")
async def fk_manual_check(call: CallbackQuery):
    await call.answer(
        "⏳ FK зачисляет автоматически. Если > 5 мин — напишите в поддержку.",
        show_alert=True,
    )


# ════════════════════════════════════════════════════════════════════════════
#  TELEGRAM STARS
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "topup_stars")
async def topup_stars_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer(
        f"⭐ <b>Telegram Stars</b>\n\n"
        f"Введите сумму в $ (мин. 1 $).\n"
        f"<i>Курс: {STARS_USD_PER_STAR} $ за 1 ⭐</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await state.set_state(TopupState.amount_stars)
    await call.answer()


@router.message(TopupState.amount_stars)
async def topup_stars_amount(message: Message, state: FSMContext):
    try:
        amount_usd = round(float(message.text.replace(",", ".")), 2)
        if amount_usd < 1.0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите сумму от 1 $!")
        return

    stars_count = max(1, round(amount_usd / STARS_USD_PER_STAR))
    await state.clear()

    await message.answer_invoice(
        title="Пополнение баланса",
        description=f"Пополнение на {amount_usd:.2f} $",
        payload=f"topup_{message.from_user.id}_{int(amount_usd * 100)}",
        currency="XTR",
        prices=[LabeledPrice(label="Пополнение", amount=stars_count)],
    )


@router.message(
    F.successful_payment &
    F.successful_payment.invoice_payload.startswith("topup_")
)
async def stars_topup_done(message: Message, bot: Bot):
    payload    = message.successful_payment.invoice_payload
    parts      = payload.split("_")
    user_id    = int(parts[1])
    amount_usd = int(parts[2]) / 100

    new_bal = await add_balance(user_id, amount_usd)
    await _pay_ref_bonus(bot, user_id, amount_usd)
    await log_action(user_id, "topup_paid",
                     {"method": "stars", "credited": amount_usd})

    await message.answer(
        f"✅ <b>Баланс пополнен (Stars)!</b>\n+{amount_usd} $\n"
        f"Баланс: <b>{new_bal:.2f} $</b>",
        parse_mode="HTML",
    )
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(
                aid, f"⭐ Stars пополнение\nID: {user_id}\n+{amount_usd} $"
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
#  ПОДДЕРЖКА / РЕПУТАЦИЯ
# ════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "🆘 Поддержка")
async def support(message: Message):
    await message.answer(
        f"🆘 <b>Поддержка</b>\n\n"
        f"👔 Владелец: @{OWNER_USERNAME}\n"
        f"🔧 Поддержка: @{SUPPORT_USERNAME}\n\n"
        f"⏰ Ответ: до 12 часов\n"
        f"🕐 18:00–00:00 МСК",
        parse_mode="HTML",
        reply_markup=support_kb(),
    )


@router.message(F.text == "⭐ Репутация")
async def reputation(message: Message):
    await message.answer(
        f"⭐ <b>Репутация</b>\n\nОтзывы в {REVIEW_CHANNEL}.\n"
        f"Оставьте отзыв — получите купон на скидку!",
        parse_mode="HTML",
        reply_markup=reputation_kb(),
    )


# ════════════════════════════════════════════════════════════════════════════
#  РЕФЕРАЛЬНЫЙ БОНУС
# ════════════════════════════════════════════════════════════════════════════

async def _pay_ref_bonus(bot: Bot, user_id: int, credited: float) -> None:
    ref_id = await get_referrer_id(user_id)
    if not ref_id:
        return
    bonus = round(credited * REFERRAL_PERCENT / 100, 4)
    await add_ref_earned(ref_id, bonus)
    await log_action(ref_id, "ref_bonus", {"from": user_id, "bonus": bonus})
    try:
        await bot.send_message(
            ref_id,
            f"💸 Ваш реферал пополнил баланс!\n🎁 Вам: <b>{bonus:.4f} $</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
