"""
Каталог, Наличие, покупка (баланс + Stars), P2P relay.
"""
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import (
    ADMIN_IDS, REVIEW_CHANNEL,
    BULK_MIN_QTY, BULK_DISCOUNT_PCT,
    CATALOG_PAGE_SIZE, STARS_USD_PER_STAR,
)
from db.database import (
    get_root_categories, get_child_categories, get_category,
    get_active_products, count_active_products,
    get_all_categories_with_products,
    get_product, get_user, pop_items,
    create_order, create_order_no_deduct,
    update_order_status, get_order_by_code,
    get_coupon, coupon_use_count, user_used_coupon,
    record_coupon_use, apply_discount,
    add_stock_notify, log_action, add_balance,
)
from keyboards.user_kb import (
    categories_kb, products_kb, product_detail_kb,
    cancel_kb, insufficient_funds_kb, review_prompt_kb,
    coupon_apply_kb,
)
from keyboards.admin_kb import new_order_admin_kb, order_confirm_kb
from utils.text_parser import get_block_for_delivery
from services.antispam import check_spam
from handlers.p2p import relay_user_to_admin

router = Router()


class BuyState(StatesGroup):
    quantity  = State()
    coupon    = State()
    user_data = State()


# ════════════════════════════════════════════════════════════════════════════
#  НАЛИЧИЕ
# ════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📋 Наличие")
async def stock_view(message: Message):
    await _send_stock(message)


@router.callback_query(F.data == "stock_root")
async def cb_stock_root(call: CallbackQuery):
    await _send_stock(call.message)
    await call.answer()


async def _send_stock(target: Message):
    cats, prods = await get_all_categories_with_products()
    if not cats:
        await target.answer("😔 Товаров пока нет.")
        return

    prod_by_cat: dict[int, list] = {}
    for p in prods:
        prod_by_cat.setdefault(p["category_id"], []).append(p)

    cat_by_parent: dict = {}
    for c in cats:
        cat_by_parent.setdefault(c["parent_id"], []).append(c)

    bot_info = await target.bot.get_me()
    bot_username = bot_info.username
    lines: list[str] = []

    def render_cat(cat_id: int, depth: int = 0):
        cat = next((c for c in cats if c["id"] == cat_id), None)
        if not cat:
            return
        indent = "  " * depth
        url = f"https://t.me/{bot_username}?start=cat_{cat_id}"
        lines.append(f"\n{indent}📂 <a href='{url}'><b>{cat['name']}</b></a>")
        for p in prod_by_cat.get(cat_id, []):
            s = "∞" if p.get("needs_data") else f"{p['stock']} шт."
            purl = f"https://t.me/{bot_username}?start=prod_{p['id']}"
            lines.append(
                f"{indent}  🛍 <a href='{purl}'>{p['name']}</a> — "
                f"{float(p['price']):.2f}$ | {s}"
            )
        for child in cat_by_parent.get(cat_id, []):
            render_cat(child["id"], depth + 1)

    for root in cat_by_parent.get(None, []):
        render_cat(root["id"])

    body = "\n".join(lines) if lines else "\n😔 Активных товаров нет."
    full = "📋 <b>Наличие товаров</b>" + body

    if len(full) <= 4000:
        await target.answer(full, parse_mode="HTML", disable_web_page_preview=True)
    else:
        chunk = "📋 <b>Наличие товаров</b>\n"
        for line in lines:
            if len(chunk) + len(line) > 3900:
                await target.answer(chunk, parse_mode="HTML",
                                    disable_web_page_preview=True)
                chunk = ""
            chunk += line + "\n"
        if chunk.strip():
            await target.answer(chunk, parse_mode="HTML",
                                disable_web_page_preview=True)


# ════════════════════════════════════════════════════════════════════════════
#  КАТАЛОГ
# ════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "🛒 Товары")
async def shop_root(message: Message):
    cats = await get_root_categories()
    if not cats:
        await message.answer("😔 Товаров пока нет.")
        return
    await message.answer("🛒 Выберите категорию:", reply_markup=categories_kb(cats))


@router.callback_query(F.data == "shop_root")
async def cb_shop_root(call: CallbackQuery):
    cats = await get_root_categories()
    text = "🛒 Выберите категорию:" if cats else "😔 Товаров пока нет."
    kb = categories_kb(cats) if cats else None
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("cat_"))
async def cb_category(call: CallbackQuery):
    cat_id = int(call.data[4:])
    await _show_category(call, cat_id, offset=0, back_to_stock=False)


@router.callback_query(F.data.startswith("view_cat_"))
async def cb_view_cat(call: CallbackQuery):
    cat_id = int(call.data[9:])
    await _show_category(call, cat_id, offset=0, back_to_stock=False)


@router.callback_query(F.data.startswith("catpage_"))
async def cb_catpage(call: CallbackQuery):
    """Пагинация: catpage_{cat_id}_{offset}"""
    parts  = call.data.split("_")
    cat_id = int(parts[1])
    offset = int(parts[2])
    await _show_category(call, cat_id, offset=offset, back_to_stock=False)


async def _show_category(call: CallbackQuery, cat_id: int,
                         offset: int = 0, back_to_stock: bool = False):
    cat      = await get_category(cat_id)
    children = await get_child_categories(cat_id)

    if not cat:
        await call.answer("Категория не найдена", show_alert=True)
        return

    parent_id = cat["parent_id"]

    if children:
        back = "stock_root" if back_to_stock else (
            f"cat_{parent_id}" if parent_id else "shop_root"
        )
        kb   = categories_kb(children, back_data=back)
        text = f"📂 {cat['name']}"
        try:
            await call.message.edit_text(text, reply_markup=kb)
        except Exception:
            await call.message.answer(text, reply_markup=kb)
        await call.answer()
        return

    # Нет подкатегорий — показываем товары с пагинацией
    total    = await count_active_products(cat_id)
    products = await get_active_products(cat_id, limit=CATALOG_PAGE_SIZE, offset=offset)

    if not products and total == 0:
        await call.answer("😔 В этой категории пусто.", show_alert=True)
        return

    kb   = products_kb(products, total, cat_id, parent_id, offset, back_to_stock)
    text = f"📂 {cat['name']} ({total} товаров)"
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except Exception:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  КАРТОЧКА ТОВАРА
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("prod_"))
async def cb_product(call: CallbackQuery):
    prod_id = int(call.data[5:])
    await _show_product(call, prod_id, back_to_stock=False)


async def _show_product(call: CallbackQuery, prod_id: int, back_to_stock: bool):
    p = await get_product(prod_id)
    if not p:
        await call.answer("Товар не найден", show_alert=True)
        return

    user    = await get_user(call.from_user.id)
    balance = float(user["balance"]) if user else 0.0
    price   = float(p["price"])
    oos     = (not p["needs_data"] and p["stock"] == 0)

    bulk_min = int(p.get("bulk_min_qty", BULK_MIN_QTY))
    bulk_pct = float(p.get("bulk_discount_pct", BULK_DISCOUNT_PCT))

    stock_str = "∞" if p["needs_data"] else f"{p['stock']} шт."
    bal_str   = (f"\n💳 С балансом: <b>{round(price - min(balance, price), 2)} $</b>"
                 if balance > 0 and not oos else "")
    bulk_str  = f"\n📦 Опт от {bulk_min} шт. — {bulk_pct}%" if bulk_pct > 0 else ""

    text = (
        f"🛍 <b>{p['name']}</b>\n"
        f"💰 Цена: <b>{price:.2f} $</b>{bal_str}{bulk_str}\n"
        f"📦 В наличии: <b>{stock_str}</b>"
        + (f"\n\n📝 {p['description']}" if p.get("description") else "")
        + (f"\n\n📋 <b>Инструкция:</b>\n{p['instruction_text']}"
           if p.get("instruction_text") else "")
    )
    kb = product_detail_kb(prod_id, p["category_id"],
                           back_to_stock=back_to_stock, out_of_stock=oos)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")

    if p.get("instruction_file"):
        await call.message.answer_document(p["instruction_file"], caption="📎 Инструкция")
    await call.answer()


@router.callback_query(F.data.startswith("notify_"))
async def notify_restock(call: CallbackQuery):
    prod_id = int(call.data[7:])
    await add_stock_notify(call.from_user.id, prod_id)
    await call.answer("🔔 Уведомим вас о поступлении!", show_alert=True)


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  ПОКУПКА — шаг 1
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("buy_"))
async def buy_start(call: CallbackQuery, state: FSMContext):
    if not check_spam(call.from_user.id, "buy"):
        await call.answer("⏳ Не так быстро!", show_alert=True)
        return

    prod_id = int(call.data[4:])
    p = await get_product(prod_id)
    if not p or p["status"] != "active":
        await call.answer("Товар недоступен.", show_alert=True)
        return
    if not p["needs_data"] and p["stock"] == 0:
        await call.answer("😔 Товар закончился!", show_alert=True)
        return

    await state.update_data(
        product_id=prod_id, product_name=p["name"],
        price=float(p["price"]), stock=int(p.get("stock", 0)),
        needs_data=bool(p["needs_data"]),
        data_request_text=p.get("data_request_text") or "Отправьте необходимые данные:",
        instruction_text=p.get("instruction_text"),
        instruction_file=p.get("instruction_file"),
        bulk_min=int(p.get("bulk_min_qty", BULK_MIN_QTY)),
        bulk_pct=float(p.get("bulk_discount_pct", BULK_DISCOUNT_PCT)),
        coupon=None,
    )
    await state.set_state(BuyState.quantity)

    max_str = "" if p["needs_data"] else f" (1–{p['stock']})"
    await call.message.answer(
        f"🛍 <b>{p['name']}</b>\n"
        f"💰 Цена: <b>{float(p['price']):.2f} $</b>\n\n"
        f"Введите количество{max_str}:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  ПОКУПКА — шаг 2: количество
# ════════════════════════════════════════════════════════════════════════════

@router.message(BuyState.quantity)
async def buy_quantity(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        qty = int(message.text.strip())
        if qty < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое число ≥ 1.")
        return

    if not data.get("needs_data") and qty > data["stock"]:
        await message.answer(f"❌ Доступно только {data['stock']} шт.")
        return

    await state.update_data(qty=qty)
    await message.answer(
        f"🔢 Кол-во: <b>{qty}</b>\n"
        f"💰 Базовая сумма: <b>{round(data['price'] * qty, 2)} $</b>\n\n"
        f"Хотите применить купон?",
        parse_mode="HTML",
        reply_markup=coupon_apply_kb(data["product_id"]),
    )


@router.callback_query(F.data.startswith("apply_coupon_"))
async def ask_coupon(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🎟 Введите код купона:", reply_markup=cancel_kb())
    await state.set_state(BuyState.coupon)
    await call.answer()


@router.message(BuyState.coupon)
async def process_coupon(message: Message, state: FSMContext):
    code    = message.text.strip().upper()
    data    = await state.get_data()
    user_id = message.from_user.id
    coupon  = await get_coupon(code)
    error   = None

    from datetime import timezone
    from datetime import datetime
    now = datetime.now(tz=timezone.utc)

    if not coupon:
        error = "❌ Купон не найден."
    elif coupon.get("expire_at") and coupon["expire_at"] < now:
        error = "❌ Купон истёк."
    elif await user_used_coupon(code, user_id):
        error = "❌ Вы уже использовали этот купон."
    elif coupon["max_uses"] > 0 and await coupon_use_count(code) >= coupon["max_uses"]:
        error = "❌ Лимит купона исчерпан."

    if error:
        await message.answer(error)
        await message.answer("Продолжить без купона?",
                             reply_markup=coupon_apply_kb(data["product_id"]))
        await state.set_state(BuyState.quantity)
        return

    await state.update_data(coupon=dict(coupon))
    await state.set_state(BuyState.quantity)
    await _confirm_purchase(message, state)


@router.callback_query(F.data.startswith("buy_no_coupon_"))
async def buy_no_coupon(call: CallbackQuery, state: FSMContext):
    await state.update_data(coupon=None)
    await _confirm_purchase(call.message, state)
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  ПОДТВЕРЖДЕНИЕ И ВЫБОР СПОСОБА ОПЛАТЫ
# ════════════════════════════════════════════════════════════════════════════

async def _confirm_purchase(message: Message, state: FSMContext):
    data    = await state.get_data()
    qty     = data["qty"]
    price   = data["price"]
    coupon  = data.get("coupon")
    user_id = message.from_user.id

    total, disc_pct, disc_desc = apply_discount(
        price, qty, coupon,
        data.get("bulk_min", BULK_MIN_QTY),
        data.get("bulk_pct", BULK_DISCOUNT_PCT),
    )
    user    = await get_user(user_id)
    balance = float(user["balance"]) if user else 0.0

    disc_line = (f"\n🏷 Скидка: <b>{disc_pct:.1f}%</b> ({disc_desc})"
                 if disc_pct > 0 else "")

    if balance < total:
        shortage = round(total - balance, 2)
        await message.answer(
            f"💸 К оплате: <b>{total} $</b>{disc_line}\n"
            f"💼 Ваш баланс: <b>{balance:.2f} $</b>\n\n"
            f"❌ Не хватает <b>{shortage} $</b>.",
            parse_mode="HTML",
            reply_markup=insufficient_funds_kb(),
        )
        await state.clear()
        return

    stars = max(1, round(total / STARS_USD_PER_STAR))
    await state.update_data(
        total=total, disc_pct=disc_pct,
        coupon_code=coupon["code"] if coupon else None,
        user_id=user_id, stars_count=stars,
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💼 С баланса ({total} $)",
                               callback_data="pay_balance")],
        [InlineKeyboardButton(text=f"⭐ Stars ({stars} XTR)",
                               callback_data=f"pay_stars")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])
    await message.answer(
        f"📋 <b>Итого</b>\n\n"
        f"📦 {data['product_name']} × {qty} шт.\n"
        f"💰 <b>{total} $</b>{disc_line}\n"
        f"💼 Баланс: <b>{balance:.2f} $</b>\n\n"
        f"Выберите способ оплаты:",
        parse_mode="HTML",
        reply_markup=kb,
    )


# ════════════════════════════════════════════════════════════════════════════
#  ОПЛАТА С БАЛАНСА
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "pay_balance")
async def pay_balance(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("product_id"):
        await call.answer("Сессия устарела.", show_alert=True)
        await state.clear()
        return

    if data.get("needs_data"):
        await call.message.answer(
            f"📋 {data.get('data_request_text', 'Отправьте необходимые данные:')}",
            reply_markup=cancel_kb(),
        )
        await state.set_state(BuyState.user_data)
    else:
        await _execute_balance_purchase(call.message, state)
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  ОПЛАТА STARS — транзакционная безопасность
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "pay_stars")
async def pay_stars(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    stars = data.get("stars_count", 1)
    await call.message.answer_invoice(
        title=data["product_name"],
        description=f"{data['product_name']} × {data['qty']} шт.",
        payload=f"buy_{data['product_id']}_{data['qty']}_{data.get('coupon_code','')}_"
                f"{int(data['total']*100)}_{int(data['disc_pct']*100)}",
        currency="XTR",
        prices=[LabeledPrice(label=data["product_name"], amount=stars)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def stars_payment_done(message: Message, state: FSMContext, bot: Bot):
    """
    Транзакционная логика Stars:
    1. Создаём pending-заказ (без списания с баланса — Stars уже списаны Telegram)
    2. Пытаемся выдать товар
    3. Если успех → статус completed
    4. Если ошибка → автоматический refund через telegram_payment_charge_id
    """
    payload = message.successful_payment.invoice_payload
    parts   = payload.split("_")
    prod_id     = int(parts[1])
    qty         = int(parts[2])
    coupon_code = parts[3] if len(parts) > 3 and parts[3] else None
    total       = int(parts[4]) / 100 if len(parts) > 4 else 0.0
    disc_pct    = int(parts[5]) / 100 if len(parts) > 5 else 0.0

    charge_id = message.successful_payment.telegram_payment_charge_id
    user_id   = message.from_user.id

    p = await get_product(prod_id)
    if not p:
        # Возвращаем Stars
        await bot.refund_star_payment(user_id, charge_id)
        await message.answer("❌ Ошибка: товар не найден. Stars возвращены.")
        return

    # 1. Создаём заказ (pending, без списания с баланса)
    order_code = await create_order_no_deduct(
        user_id=user_id, product_id=prod_id, qty=qty, total=total,
        status="pending", discount_pct=disc_pct, coupon_code=coupon_code,
        stars_charge_id=charge_id,
    )

    # 2. Пробуем выдать товар
    try:
        groups = await pop_items(prod_id, qty)
        if groups is None:
            raise RuntimeError("Out of stock")
    except Exception as e:
        # 3. Ошибка — делаем refund и отменяем заказ
        await update_order_status(order_code, "cancelled")
        try:
            await bot.refund_star_payment(user_id, charge_id)
            await message.answer(
                f"❌ Не удалось выдать товар (нет в наличии). "
                f"Stars возвращены автоматически."
            )
        except Exception:
            await message.answer(
                f"❌ Ошибка выдачи. Обратитесь в поддержку, код заказа: "
                f"<code>{order_code}</code>",
                parse_mode="HTML"
            )
        await log_action(user_id, "stars_refund",
                         {"order_code": order_code, "reason": str(e)})
        return

    # 4. Успех — помечаем completed
    await update_order_status(order_code, "completed")
    if coupon_code:
        await record_coupon_use(coupon_code, user_id)
    await log_action(user_id, "purchase_stars",
                     {"order_code": order_code, "stars": message.successful_payment.total_amount})

    await message.answer(
        f"✅ <b>Оплата Stars принята!</b>\n🔖 <code>{order_code}</code>",
        parse_mode="HTML"
    )
    await _deliver_items(message, groups, p, order_code, user_id, bot)
    await state.clear()


# ════════════════════════════════════════════════════════════════════════════
#  ДАННЫЕ ОТ ПОЛЬЗОВАТЕЛЯ (needs_data / P2P)
# ════════════════════════════════════════════════════════════════════════════

@router.message(BuyState.user_data)
async def buy_user_data(message: Message, state: FSMContext, bot: Bot):
    data      = await state.get_data()
    user_data = message.text.strip() if message.text else "[файл/медиа]"
    user_id   = message.from_user.id
    qty       = data["qty"]
    total     = data["total"]
    prod_id   = data["product_id"]
    disc_pct  = data.get("disc_pct", 0)
    coupon_code = data.get("coupon_code")

    order_code = await create_order(
        user_id=user_id, product_id=prod_id, qty=qty, total=total,
        status="waiting_confirm", discount_pct=disc_pct, coupon_code=coupon_code,
    )
    await update_order_status(order_code, "waiting_confirm", user_data=user_data)

    if coupon_code:
        await record_coupon_use(coupon_code, user_id)

    await log_action(user_id, "order_data_submitted", {"order_code": order_code})
    await state.clear()

    await message.answer(
        f"✅ Данные получены!\n"
        f"🔖 Заказ: <code>{order_code}</code>\n\n"
        f"⏳ Ожидайте — администратор скоро возьмёт ваш заказ.",
        parse_mode="HTML",
    )

    # Уведомляем ВСЕХ администраторов с кнопкой «Взять заказ»
    uname = f"@{message.from_user.username}" if message.from_user.username else str(user_id)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📬 <b>Новый заказ!</b>\n"
                f"🔖 <code>{order_code}</code>\n"
                f"👤 {uname} (ID: <code>{user_id}</code>)\n"
                f"📦 {data['product_name']} × {qty} шт.\n"
                f"💰 {total} $"
                + (f" (скидка {disc_pct:.1f}%)" if disc_pct > 0 else "")
                + f"\n\n📋 <b>Данные:</b>\n{user_data}",
                parse_mode="HTML",
                reply_markup=new_order_admin_kb(order_code),
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
#  P2P RELAY — перехват сообщений пользователей и администраторов
# ════════════════════════════════════════════════════════════════════════════

@router.message(F.text & ~F.text.startswith("/"))
async def intercept_user_message(message: Message, bot: Bot, state: FSMContext):
    """
    Если у пользователя активный P2P-заказ — перехватываем сообщение.
    Если у администратора активный P2P-заказ — тоже перехватываем.
    """
    user_id = message.from_user.id

    # Проверяем FSM — если в каком-то состоянии, не перехватываем
    current_state = await state.get_state()
    if current_state is not None:
        return

    # Пользователь → админ
    if user_id not in ADMIN_IDS:
        intercepted = await relay_user_to_admin(message, bot)
        if intercepted:
            return
        # Иначе — стандартная обработка (будет обработана другими хэндлерами)

    # Администратор → пользователь
    elif user_id in ADMIN_IDS:
        from db.database import get_in_work_order_for_admin
        order = await get_in_work_order_for_admin(user_id)
        if order:
            from handlers.p2p import relay_admin_to_user
            await relay_admin_to_user(message, bot, order)


@router.message(F.document | F.photo)
async def intercept_media(message: Message, bot: Bot, state: FSMContext):
    """Перехват медиа для P2P."""
    current_state = await state.get_state()
    if current_state is not None:
        return

    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await relay_user_to_admin(message, bot)
    elif user_id in ADMIN_IDS:
        from db.database import get_in_work_order_for_admin
        order = await get_in_work_order_for_admin(user_id)
        if order:
            from handlers.p2p import relay_admin_to_user
            await relay_admin_to_user(message, bot, order)


# ════════════════════════════════════════════════════════════════════════════
#  ЦИФРОВАЯ ВЫДАЧА
# ════════════════════════════════════════════════════════════════════════════

async def _execute_balance_purchase(message: Message, state: FSMContext):
    data    = await state.get_data()
    user_id = data["user_id"]
    qty     = data["qty"]
    total   = data["total"]
    prod_id = data["product_id"]
    disc_pct    = data.get("disc_pct", 0)
    coupon_code = data.get("coupon_code")

    groups = await pop_items(prod_id, qty)
    if groups is None:
        await message.answer("😔 Товар разобрали. Попробуйте снова.")
        await state.clear()
        return

    order_code = await create_order(
        user_id=user_id, product_id=prod_id, qty=qty, total=total,
        status="completed", discount_pct=disc_pct, coupon_code=coupon_code,
    )
    if coupon_code:
        await record_coupon_use(coupon_code, user_id)
    await log_action(user_id, "purchase_balance",
                     {"order_code": order_code, "total": total})
    await state.clear()

    p = await get_product(prod_id)
    if data.get("instruction_text"):
        await message.answer(f"📝 <b>Инструкция:</b>\n{data['instruction_text']}")
    if data.get("instruction_file"):
        await message.answer_document(data["instruction_file"], caption="📎 Инструкция")

    await message.answer(
        f"✅ <b>Оплата принята!</b>\n🔖 <code>{order_code}</code>",
        parse_mode="HTML",
    )
    await _deliver_items(message, groups, p, order_code, user_id, message.bot)


async def _deliver_items(message: Message, groups: list[list[dict]], p: dict,
                         order_code: str, user_id: int, bot: Bot):
    for idx, group_items in enumerate(groups, start=1):
        if len(group_items) == 1:
            item = group_items[0]
            if item["type"] == "file":
                await message.answer_document(item["content"], caption=f"✅ Товар #{idx}")
            elif item["type"] == "link":
                await message.answer(f"✅ <b>#{idx}:</b>\n🔗 {item['content']}")
            else:
                block = get_block_for_delivery(item["content"], idx)
                await message.answer(f"✅ <b>#{idx}:</b>\n<code>{block}</code>")
        else:
            await message.answer(f"✅ <b>#{idx}</b> (комплект {len(group_items)} файлов):")
            for sub, item in enumerate(group_items, 1):
                if item["type"] == "file":
                    await message.answer_document(item["content"],
                                                  caption=f"📁 {sub}/{len(group_items)}")
                else:
                    await message.answer(f"🔗 {item['content']}")

    await message.answer(
        f"⭐ Оставьте отзыв в {REVIEW_CHANNEL} и получите купон!",
        reply_markup=review_prompt_kb(),
    )

    uname = (f"@{message.from_user.username}"
             if message.from_user.username else str(user_id))
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🛒 <b>Покупка!</b>\n🔖 <code>{order_code}</code>\n"
                f"👤 {uname}\n📦 {p['name']} × {len(groups)} шт.",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
#  DEEPLINK
# ════════════════════════════════════════════════════════════════════════════

async def handle_start_deeplink(message: Message, param: str):
    if param.startswith("cat_"):
        try:
            cat_id = int(param[4:])
        except ValueError:
            return
        total    = await count_active_products(cat_id)
        products = await get_active_products(cat_id, limit=CATALOG_PAGE_SIZE)
        cat = await get_category(cat_id)
        if not cat:
            await message.answer("Категория не найдена.")
            return
        kb = products_kb(products, total, cat_id, cat["parent_id"],
                         offset=0, back_to_stock=True)
        await message.answer(f"📂 {cat['name']}", reply_markup=kb)

    elif param.startswith("prod_"):
        try:
            prod_id = int(param[5:])
        except ValueError:
            return
        p = await get_product(prod_id)
        if not p or p["status"] != "active":
            await message.answer("Товар недоступен.")
            return
        oos = not p["needs_data"] and p["stock"] == 0
        await message.answer(
            f"🛍 <b>{p['name']}</b>\n💰 {float(p['price']):.2f} $",
            parse_mode="HTML",
            reply_markup=product_detail_kb(prod_id, p["category_id"],
                                           back_to_stock=True, out_of_stock=oos),
        )


@router.callback_query(F.data == "go_balance")
async def go_balance(call: CallbackQuery):
    from keyboards.user_kb import balance_kb
    await call.message.answer("💰 Выберите способ пополнения:", reply_markup=balance_kb())
    await call.answer()
