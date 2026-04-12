from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Категории",           callback_data="adm_cats")],
        [InlineKeyboardButton(text="➕ Новый товар",         callback_data="adm_new_prod")],
        [InlineKeyboardButton(text="📦 Пополнить товар",     callback_data="adm_restock")],
        [InlineKeyboardButton(text="✏️ Изменить цену",       callback_data="adm_edit_price")],
        [InlineKeyboardButton(text="🗑 Удалить товар",       callback_data="adm_del_prod")],
        [InlineKeyboardButton(text="📁 Черновики",           callback_data="adm_drafts")],
        [InlineKeyboardButton(text="📋 Ожидающие заказы",    callback_data="adm_pending_orders")],
        [InlineKeyboardButton(text="🎟 Купоны",              callback_data="adm_coupons")],
        [InlineKeyboardButton(text="📢 Умная рассылка",      callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="💰 Начислить баланс",    callback_data="adm_grant")],
        [InlineKeyboardButton(text="📊 Статистика",          callback_data="adm_stats")],
        [InlineKeyboardButton(text="🔍 CRM — поиск юзера",   callback_data="adm_crm")],
        [InlineKeyboardButton(text="📜 Лог действий",        callback_data="adm_audit")],
    ])


def back_to_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В панель", callback_data="adm_back")],
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm_cancel")],
    ])


def select_category_kb(cats: list,
                       prefix: str = "adm_cat_sel_") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📂 {c['name']}",
                              callback_data=f"{prefix}{c['id']}")]
        for c in cats
    ]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="adm_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def select_product_kb(products: list, prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{'🟢' if p['status']=='active' else '🔴'} {p['name']} ({p['stock']} шт.)",
            callback_data=f"{prefix}{p['id']}"
        )]
        for p in products
    ]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="adm_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_manage_kb(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Инструкция (текст)",
                              callback_data=f"adm_itext_{pid}")],
        [InlineKeyboardButton(text="📎 Инструкция (файл)",
                              callback_data=f"adm_ifile_{pid}")],
        [InlineKeyboardButton(text="🔗 Добавить ссылки",
                              callback_data=f"adm_addlinks_{pid}")],
        [InlineKeyboardButton(text="📁 Добавить файлы",
                              callback_data=f"adm_addfiles_{pid}")],
        [InlineKeyboardButton(text="✏️ Текст запроса данных",
                              callback_data=f"adm_datareq_{pid}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
    ])


def restock_type_kb(pid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Ссылки/Текст",
                              callback_data=f"adm_rst_links_{pid}")],
        [InlineKeyboardButton(text="📁 Файлы",
                              callback_data=f"adm_rst_files_{pid}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm_cancel")],
    ])


def file_group_done_kb(pid: int, group: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ещё файл к этой единице",
                               callback_data=f"adm_morefile_{pid}_{group}")],
        [InlineKeyboardButton(text="✅ Следующая единица / Готово",
                               callback_data=f"adm_nextunit_{pid}_{group}")],
    ])


def new_order_admin_kb(order_code: str) -> InlineKeyboardMarkup:
    """Кнопки под уведомлением о новом заказе (needs_data)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤝 Взять заказ",
                               callback_data=f"take_order_{order_code}")],
    ])


def p2p_admin_control_kb(order_code: str) -> InlineKeyboardMarkup:
    """Кнопки управления заказом для взявшего его администратора."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Запросить данные",
                               callback_data=f"p2p_request_code_{order_code}")],
        [InlineKeyboardButton(text="⏰ Продлить время",
                               callback_data=f"p2p_extend_{order_code}"),
         InlineKeyboardButton(text="↩️ Сделать возврат",
                               callback_data=f"p2p_refund_{order_code}")],
        [InlineKeyboardButton(text="✅ Завершить заказ",
                               callback_data=f"p2p_complete_{order_code}")],
    ])


def order_confirm_kb(order_code: str) -> InlineKeyboardMarkup:
    """Старые кнопки подтверждения (для заказов БЕЗ P2P-режима)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить выдачу",
                               callback_data=f"adm_ord_confirm_{order_code}")],
        [InlineKeyboardButton(text="❌ Отклонить",
                               callback_data=f"adm_ord_reject_{order_code}")],
    ])


def coupon_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Купон %",      callback_data="adm_cpn_create_percent")],
        [InlineKeyboardButton(text="➕ Купон $",      callback_data="adm_cpn_create_fixed")],
        [InlineKeyboardButton(text="📋 Список",       callback_data="adm_cpn_list")],
        [InlineKeyboardButton(text="🗑 Удалить",      callback_data="adm_cpn_delete")],
        [InlineKeyboardButton(text="◀️ Назад",        callback_data="adm_back")],
    ])


def broadcast_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Всем",                  callback_data="bc_all")],
        [InlineKeyboardButton(text="💰 По балансу (≥ N$)",     callback_data="bc_balance")],
        [InlineKeyboardButton(text="🛍 Покупали товар (месяц)", callback_data="bc_product_month")],
        [InlineKeyboardButton(text="🛍 Покупали товар (всё)",   callback_data="bc_product_all")],
        [InlineKeyboardButton(text="❌ Отмена",                 callback_data="adm_cancel")],
    ])


def stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Топ рефералов",
                               callback_data="adm_top_refs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
    ])
