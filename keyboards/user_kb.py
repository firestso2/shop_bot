fromffrom aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from config import REVIEW_CHANNEL, OWNER_USERNAME, SUPPORT_USERNAME, CATALOG_PAGE_SIZE


def main_kb():
    """Убрана reply-клавиатура — используем только inline."""
    return None


def welcome_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Каталог",          callback_data="shop_root"),
         InlineKeyboardButton(text="📋 Наличие",          callback_data="stock_root")],
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="topup_menu"),
         InlineKeyboardButton(text="👤 Профиль",          callback_data="profile_inline")],
        [InlineKeyboardButton(text="⭐ Репутация",        callback_data="reputation_inline")],
        [InlineKeyboardButton(text="🆘 Поддержка",
                              url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])


def op_check_kb() -> InlineKeyboardMarkup:
    from config import OP_CHANNEL
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться",
                              url=f"https://t.me/{OP_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def categories_kb(categories: list, back_data: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📂 {c['name']}", callback_data=f"cat_{c['id']}")]
        for c in categories
    ]
    if back_data:
        rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_kb(products: list, total: int, cat_id: int,
                parent_cat_id: int | None, offset: int = 0,
                back_to_stock: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for p in products:
        label = f"🛍 {p['name']} | {float(p['price']):.2f}$"
        if not p.get("needs_data"):
            label += f" | {p['stock']} шт."
        rows.append([InlineKeyboardButton(label, callback_data=f"prod_{p['id']}")])

    nav = []
    if offset > 0:
        prev_off = max(0, offset - CATALOG_PAGE_SIZE)
        nav.append(InlineKeyboardButton(
            text="◀️", callback_data=f"catpage_{cat_id}_{prev_off}"
        ))
    nav.append(InlineKeyboardButton(
        text=f"{offset // CATALOG_PAGE_SIZE + 1}/{(total - 1) // CATALOG_PAGE_SIZE + 1}",
        callback_data="noop"
    ))
    if offset + CATALOG_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            text="▶️", callback_data=f"catpage_{cat_id}_{offset + CATALOG_PAGE_SIZE}"
        ))
    if len(nav) > 1:
        rows.append(nav)

    if back_to_stock:
        rows.append([InlineKeyboardButton(text="◀️ К наличию", callback_data="stock_root")])
    elif parent_cat_id is not None:
        rows.append([InlineKeyboardButton(text="◀️ Назад",
                                           callback_data=f"cat_{parent_cat_id}")])
    else:
        rows.append([InlineKeyboardButton(text="◀️ К категориям",
                                           callback_data="shop_root")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_detail_kb(product_id: int, cat_id: int,
                      back_to_stock: bool = False,
                      out_of_stock: bool = False) -> InlineKeyboardMarkup:
    back_data = "stock_root" if back_to_stock else f"view_cat_{cat_id}"
    rows = []
    if out_of_stock:
        rows.append([InlineKeyboardButton(
            text="🔔 Уведомить о поступлении",
            callback_data=f"notify_{product_id}"
        )])
    else:
        rows.append([InlineKeyboardButton(
            text="🛒 Купить", callback_data=f"buy_{product_id}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def balance_kb() -> InlineKeyboardMarkup:
    """Только CryptoBot — Stars и FreeKassa убраны."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 CryptoBot (USDT) +3%", callback_data="topup_crypto")],
    ])


def topup_go_kb(pay_url: str, check_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить ↗", url=pay_url)],
        [InlineKeyboardButton(text="✅ Проверить вручную", callback_data=check_data)],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def insufficient_funds_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="topup_menu")],
        [InlineKeyboardButton(text="❌ Отмена",    callback_data="cancel")],
    ])


def support_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👔 Владелец ↗",
                              url=f"https://t.me/{OWNER_USERNAME}")],
        [InlineKeyboardButton(text="🔧 Поддержка ↗",
                              url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])


def reputation_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Написать отзыв ↗",
                              url=f"https://t.me/{REVIEW_CHANNEL.lstrip('@')}")],
    ])


def review_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оставить отзыв ↗",
                              url=f"https://t.me/{REVIEW_CHANNEL.lstrip('@')}")],
    ])


def coupon_apply_kb(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Применить купон",
                              callback_data=f"apply_coupon_{product_id}")],
        [InlineKeyboardButton(text="➡️ Без купона",
                              callback_data=f"buy_no_coupon_{product_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def orders_nav_kb(offset: int, total: int, page_size: int = 5) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(
            text="◀️", callback_data=f"orders_page_{offset - page_size}"
        ))
    if offset + page_size < total:
        nav.append(InlineKeyboardButton(
            text="▶️", callback_data=f"orders_page_{offset + page_size}"
        ))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else InlineKeyboardMarkup(inline_keyboard=[])
