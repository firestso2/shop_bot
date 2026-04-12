"""
Панель администратора — полная версия с CRM и топом рефералов.
"""
from datetime import datetime, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS, BULK_MIN_QTY, BULK_DISCOUNT_PCT
from db.database import (
    get_all_categories_flat, get_root_categories, get_child_categories,
    get_all_products, get_product, get_draft_products,
    create_category, delete_category,
    create_product, update_product_instruction, update_product_data_request,
    update_product_price, delete_product,
    add_items, add_file_to_group, get_next_item_group, get_stock_count,
    get_user, admin_set_balance, get_all_user_ids, get_stats,
    get_pending_data_orders, get_order_by_code,
    create_coupon, delete_coupon, list_coupons,
    get_users_with_balance_above, get_users_bought_product,
    get_audit_log, log_action,
    get_user_crm, get_top_referrers,
    update_order_status, add_balance,
)
from keyboards.admin_kb import (
    admin_main_kb, back_to_admin_kb, cancel_kb,
    select_category_kb, select_product_kb,
    product_manage_kb, restock_type_kb,
    file_group_done_kb, coupon_admin_kb,
    broadcast_type_kb, order_confirm_kb,
    new_order_admin_kb, stats_kb,
)

router = Router()


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ════════════════════════════════════════════════════════════════════════════
#  FSM
# ════════════════════════════════════════════════════════════════════════════

class AdminState(StatesGroup):
    new_cat_name    = State()
    prod_name       = State()
    prod_desc       = State()
    prod_price      = State()
    prod_bulk       = State()
    prod_data_req   = State()
    itext           = State()
    ifile_wait      = State()
    links           = State()
    file_group_wait = State()
    rst_links       = State()
    edit_price_val  = State()
    broadcast_text  = State()
    bc_balance_thr  = State()
    bc_product_sel  = State()
    cpn_code        = State()
    cpn_value       = State()
    cpn_max_uses    = State()
    cpn_expire_days = State()
    grant_uid       = State()
    grant_amount    = State()
    datareq_text    = State()
    crm_uid         = State()


# ════════════════════════════════════════════════════════════════════════════
#  ВХОД
# ════════════════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🔧 Панель администратора:", reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm_back")
async def adm_back(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    await call.message.answer("🔧 Панель администратора:", reply_markup=admin_main_kb())
    await call.answer()


@router.callback_query(F.data == "adm_cancel")
async def adm_cancel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    await call.message.answer("❌ Отменено.", reply_markup=admin_main_kb())
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  ОЖИДАЮЩИЕ ЗАКАЗЫ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_pending_orders")
async def adm_pending_orders(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    orders = await get_pending_data_orders()
    if not orders:
        await call.answer("Нет ожидающих заказов.", show_alert=True)
        return
    for o in orders:
        uname = f"@{o['username']}" if o["username"] else str(o["user_id"])
        await call.message.answer(
            f"📬 <b>Заказ ожидает</b>\n"
            f"🔖 <code>{o['order_code']}</code>\n"
            f"👤 {uname} (ID: <code>{o['user_id']}</code>)\n"
            f"📦 {o['product_name']} × {o['quantity']} шт.\n"
            f"💰 {float(o['total']):.2f} $\n\n"
            f"📋 <b>Данные:</b>\n{o.get('user_data') or '—'}",
            parse_mode="HTML",
            reply_markup=new_order_admin_kb(o["order_code"]),
        )
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  КАТЕГОРИИ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_cats")
async def adm_cats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cats = await get_root_categories()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = [[InlineKeyboardButton(text=f"📂 {c['name']}",
                                   callback_data=f"adm_catv_{c['id']}")] for c in cats]
    rows.append([InlineKeyboardButton(text="➕ Новая категория",
                                       callback_data="adm_newrootcat")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    await call.message.answer("📂 Категории:",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.startswith("adm_catv_"))
async def adm_cat_view(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data[9:])
    children = await get_child_categories(cat_id)
    all_products = await get_all_products()
    cat_prods = [p for p in all_products if p["category_id"] == cat_id]

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = []
    for c in children:
        rows.append([InlineKeyboardButton(text=f"📂 {c['name']}",
                                           callback_data=f"adm_catv_{c['id']}")])
    for p in cat_prods:
        icon = "🟢" if p["status"] == "active" else "🔴"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {p['name']} ({p['stock']} шт.)",
            callback_data=f"adm_prodv_{p['id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Подкатегория",
                                       callback_data=f"adm_newsub_{cat_id}")])
    rows.append([InlineKeyboardButton(text="🗑 Удалить",
                                       callback_data=f"adm_delcat_{cat_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_cats")])
    await call.message.answer(f"📂 ID={cat_id}:",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data == "adm_newrootcat")
async def adm_newrootcat(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(new_cat_parent=None)
    await state.set_state(AdminState.new_cat_name)
    await call.message.answer("📝 Название:", reply_markup=cancel_kb())
    await call.answer()


@router.callback_query(F.data.startswith("adm_newsub_"))
async def adm_newsub(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(new_cat_parent=int(call.data[11:]))
    await state.set_state(AdminState.new_cat_name)
    await call.message.answer("📝 Название подкатегории:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.new_cat_name)
async def adm_save_cat(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    d = await state.get_data()
    cat_id = await create_category(message.text.strip(), d.get("new_cat_parent"))
    await state.clear()
    await message.answer(f"✅ Категория создана (ID={cat_id}).", reply_markup=admin_main_kb())


@router.callback_query(F.data.startswith("adm_delcat_"))
async def adm_delcat(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    ok = await delete_category(int(call.data[11:]))
    if ok:
        await call.message.answer("✅ Удалена.", reply_markup=admin_main_kb())
    else:
        await call.answer("❌ Нельзя удалить непустую!", show_alert=True)
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  ПРОСМОТР ТОВАРА В АДМИНКЕ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("adm_prodv_"))
async def adm_prod_view(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data[10:])
    p = await get_product(prod_id)
    if not p:
        await call.answer("Не найден", show_alert=True)
        return
    await call.message.answer(
        f"🛍 <b>{p['name']}</b>\n"
        f"💰 {float(p['price']):.2f} $ | Остаток: {p['stock']}\n"
        f"📊 {'🟢 active' if p['status']=='active' else '🔴 draft'}\n"
        f"📦 Опт: от {p['bulk_min_qty']} шт. — {float(p['bulk_discount_pct']):.1f}%\n"
        f"📋 Данные: {'✅' if p['needs_data'] else '❌'}\n"
        f"📝 Инструкция: {'✅' if p['instruction_text'] else '❌'}",
        parse_mode="HTML",
        reply_markup=product_manage_kb(prod_id),
    )
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  НОВЫЙ ТОВАР
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_new_prod")
async def adm_new_prod(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    cats = await get_all_categories_flat()
    if not cats:
        await call.answer("Создайте категорию!", show_alert=True)
        return
    await call.message.answer("📂 Выберите категорию:",
                               reply_markup=select_category_kb(cats, "adm_prodcat_"))
    await call.answer()


@router.callback_query(F.data.startswith("adm_prodcat_"))
async def adm_prod_cat(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(cat_id=int(call.data[12:]))
    await state.set_state(AdminState.prod_name)
    await call.message.answer("📝 Название товара:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.prod_name)
async def adm_prod_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(prod_name=message.text.strip())
    await state.set_state(AdminState.prod_desc)
    await message.answer("📄 Описание (или «-»):", reply_markup=cancel_kb())


@router.message(AdminState.prod_desc)
async def adm_prod_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    desc = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(prod_desc=desc)
    await state.set_state(AdminState.prod_price)
    await message.answer("💰 Цена в $:", reply_markup=cancel_kb())


@router.message(AdminState.prod_price)
async def adm_prod_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = float(message.text.strip())
        assert price > 0
    except (ValueError, AssertionError):
        await message.answer("❌ Введите положительное число!")
        return
    await state.update_data(prod_price=price)
    await state.set_state(AdminState.prod_bulk)
    await message.answer(
        f"📦 Оптовые условия (или «-» для {BULK_MIN_QTY} шт. / {BULK_DISCOUNT_PCT}%):\n"
        f"Формат: «кол-во скидка%» — например «5 10»",
        reply_markup=cancel_kb(),
    )


@router.message(AdminState.prod_bulk)
async def adm_prod_bulk(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip()
    if text == "-":
        bulk_min, bulk_pct = BULK_MIN_QTY, BULK_DISCOUNT_PCT
    else:
        try:
            parts = text.split()
            bulk_min, bulk_pct = int(parts[0]), float(parts[1])
        except Exception:
            await message.answer("❌ Формат: «5 10» или «-».")
            return
    await state.update_data(bulk_min=bulk_min, bulk_pct=bulk_pct)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да — требует данных",
                               callback_data="adm_needsdata_yes")],
        [InlineKeyboardButton(text="❌ Нет — цифровой товар",
                               callback_data="adm_needsdata_no")],
    ])
    await message.answer("📋 Товар требует данных от покупателя?", reply_markup=kb)


@router.callback_query(F.data.startswith("adm_needsdata_"))
async def adm_needsdata(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    needs = call.data.endswith("_yes")
    await state.update_data(needs_data=needs)
    if needs:
        await state.set_state(AdminState.prod_data_req)
        await call.message.answer(
            "📋 Текст запроса данных (например: «Отправьте ссылку на аккаунт»):",
            reply_markup=cancel_kb(),
        )
    else:
        await _finalize_product(call.message, state)
    await call.answer()


@router.message(AdminState.prod_data_req)
async def adm_prod_data_req(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(data_req_text=message.text.strip())
    await _finalize_product(message, state)


async def _finalize_product(target: Message, state: FSMContext):
    d = await state.get_data()
    prod_id = await create_product(
        cat_id=d["cat_id"], name=d["prod_name"], description=d.get("prod_desc"),
        price=d["prod_price"], needs_data=d.get("needs_data", False),
        data_request_text=d.get("data_req_text"),
        bulk_min_qty=d.get("bulk_min", BULK_MIN_QTY),
        bulk_discount_pct=d.get("bulk_pct", BULK_DISCOUNT_PCT),
    )
    await log_action(None, "create_product", {"id": prod_id, "name": d["prod_name"]})
    await state.clear()
    await target.answer(
        f"✅ Товар «{d['prod_name']}» создан (ID={prod_id}).\nДобавьте контент:",
        reply_markup=product_manage_kb(prod_id),
    )


# ════════════════════════════════════════════════════════════════════════════
#  КОНТЕНТ ТОВАРА
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("adm_itext_"))
async def adm_itext_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(target_prod=int(call.data[10:]))
    await state.set_state(AdminState.itext)
    await call.message.answer("📝 Текст инструкции:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.itext)
async def adm_itext_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    d = await state.get_data()
    await update_product_instruction(d["target_prod"], text=message.text)
    await state.clear()
    await message.answer("✅ Инструкция (текст) сохранена!",
                          reply_markup=product_manage_kb(d["target_prod"]))


@router.callback_query(F.data.startswith("adm_ifile_"))
async def adm_ifile_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(target_prod=int(call.data[10:]))
    await state.set_state(AdminState.ifile_wait)
    await call.message.answer("📎 Отправьте файл:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.ifile_wait, F.document)
async def adm_ifile_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    d = await state.get_data()
    await update_product_instruction(d["target_prod"], file_id=message.document.file_id)
    await state.clear()
    await message.answer("✅ Инструкция (файл) сохранена!",
                          reply_markup=product_manage_kb(d["target_prod"]))


@router.callback_query(F.data.startswith("adm_datareq_"))
async def adm_datareq_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(target_prod=int(call.data[12:]))
    await state.set_state(AdminState.datareq_text)
    await call.message.answer("📋 Новый текст запроса:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.datareq_text)
async def adm_datareq_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    d = await state.get_data()
    await update_product_data_request(d["target_prod"], message.text.strip())
    await state.clear()
    await message.answer("✅ Текст запроса обновлён!",
                          reply_markup=product_manage_kb(d["target_prod"]))


@router.callback_query(F.data.startswith("adm_addlinks_"))
async def adm_addlinks_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(target_prod=int(call.data[13:]))
    await state.set_state(AdminState.links)
    await call.message.answer("🔗 Список ссылок/текста:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.links)
async def adm_links_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    from utils.text_parser import _parse_raw_links
    links = _parse_raw_links(message.text)
    if not links:
        await message.answer("❌ Не удалось распознать.")
        return
    d = await state.get_data()
    prod_id   = d["target_prod"]
    item_type = "link" if all(l.startswith("http") for l in links) else "text"
    count     = await add_items(prod_id, links, item_type)
    stock     = await get_stock_count(prod_id)
    await state.clear()
    await message.answer(
        f"✅ +{count} шт. Итого: <b>{stock}</b>",
        parse_mode="HTML",
        reply_markup=product_manage_kb(prod_id),
    )


# ════════════════════════════════════════════════════════════════════════════
#  ФАЙЛЫ С ГРУППАМИ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("adm_addfiles_"))
async def adm_addfiles_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data[13:])
    group   = await get_next_item_group(prod_id)
    await state.update_data(target_prod=prod_id, current_group=group, group_files=0)
    await state.set_state(AdminState.file_group_wait)
    await call.message.answer(f"📁 Файл для единицы #{group}:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.file_group_wait, F.document)
async def adm_file_recv(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    d = await state.get_data()
    prod_id = d["target_prod"]
    group   = d["current_group"]
    count   = d.get("group_files", 0) + 1
    await add_file_to_group(prod_id, message.document.file_id, group)
    await state.update_data(group_files=count)
    stock = await get_stock_count(prod_id)
    await message.answer(
        f"✅ Файл {count} → единица #{group}. Всего единиц: {stock}",
        reply_markup=file_group_done_kb(prod_id, group),
    )


@router.callback_query(F.data.startswith("adm_morefile_"))
async def adm_morefile(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split("_")
    await call.message.answer(f"📁 Ещё файл для единицы #{parts[3]}:",
                               reply_markup=cancel_kb())
    await call.answer()


@router.callback_query(F.data.startswith("adm_nextunit_"))
async def adm_nextunit(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data.split("_")[2])
    new_g   = await get_next_item_group(prod_id)
    await state.update_data(current_group=new_g, group_files=0)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Следующая единица",
                               callback_data=f"adm_startunit_{prod_id}")],
        [InlineKeyboardButton(text="✅ Завершить",
                               callback_data=f"adm_fdone_{prod_id}")],
    ])
    stock = await get_stock_count(prod_id)
    await call.message.answer(f"📦 Единиц: {stock}. Что дальше?", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("adm_startunit_"))
async def adm_startunit(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data[14:])
    group   = await get_next_item_group(prod_id)
    await state.update_data(target_prod=prod_id, current_group=group, group_files=0)
    await state.set_state(AdminState.file_group_wait)
    await call.message.answer(f"📁 Файл для единицы #{group}:", reply_markup=cancel_kb())
    await call.answer()


@router.callback_query(F.data.startswith("adm_fdone_"))
async def adm_fdone(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data[10:])
    await state.clear()
    stock = await get_stock_count(prod_id)
    await call.message.answer(
        f"✅ Готово! Итого: <b>{stock} шт.</b>",
        parse_mode="HTML",
        reply_markup=product_manage_kb(prod_id),
    )
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  ПОПОЛНЕНИЕ ОСТАТКОВ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_restock")
async def adm_restock(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    products = await get_all_products()
    if not products:
        await call.answer("Товаров нет.", show_alert=True)
        return
    await call.message.answer("📦 Выберите товар:",
                               reply_markup=select_product_kb(products, "adm_rst_"))
    await call.answer()


@router.callback_query(F.data.startswith("adm_rst_links_"))
async def adm_rst_links(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(target_prod=int(call.data[14:]))
    await state.set_state(AdminState.rst_links)
    await call.message.answer("🔗 Список:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.rst_links)
async def adm_rst_links_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    from utils.text_parser import _parse_raw_links
    links = _parse_raw_links(message.text)
    if not links:
        await message.answer("❌ Не удалось распознать.")
        return
    d = await state.get_data()
    prod_id   = d["target_prod"]
    item_type = "link" if all(l.startswith("http") for l in links) else "text"
    count     = await add_items(prod_id, links, item_type)
    stock     = await get_stock_count(prod_id)
    await state.clear()
    await message.answer(
        f"✅ +{count} ед. Итого: <b>{stock}</b>",
        parse_mode="HTML", reply_markup=admin_main_kb(),
    )


@router.callback_query(F.data.startswith("adm_rst_files_"))
async def adm_rst_files(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data[14:])
    group   = await get_next_item_group(prod_id)
    await state.update_data(target_prod=prod_id, current_group=group, group_files=0)
    await state.set_state(AdminState.file_group_wait)
    await call.message.answer(f"📁 Файл для единицы #{group}:", reply_markup=cancel_kb())
    await call.answer()


# Обработчик выбора товара для restock (без явного суффикса links/files)
@router.callback_query(F.data.startswith("adm_rst_"))
async def adm_rst_sel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    suffix = call.data[8:]
    if suffix.startswith("links_") or suffix.startswith("files_"):
        return
    prod_id = int(suffix)
    p = await get_product(prod_id)
    if not p:
        await call.answer("Не найден", show_alert=True)
        return
    await call.message.answer(
        f"📦 <b>{p['name']}</b>\nОстаток: {p['stock']} ед.\n\nЧто добавить?",
        parse_mode="HTML",
        reply_markup=restock_type_kb(prod_id),
    )
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  ЦЕНА / УДАЛЕНИЕ / ЧЕРНОВИКИ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_edit_price")
async def adm_edit_price(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    products = await get_all_products()
    await call.message.answer("✏️ Выберите товар:",
                               reply_markup=select_product_kb(products, "adm_ep_"))
    await call.answer()


@router.callback_query(F.data.startswith("adm_ep_"))
async def adm_ep_sel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data[7:])
    p = await get_product(prod_id)
    await state.update_data(target_prod=prod_id)
    await state.set_state(AdminState.edit_price_val)
    await call.message.answer(
        f"Текущая: {float(p['price']):.2f} $\nНовая:", reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(AdminState.edit_price_val)
async def adm_ep_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = float(message.text.strip())
        assert price > 0
    except (ValueError, AssertionError):
        await message.answer("❌ Введите число!")
        return
    d = await state.get_data()
    await update_product_price(d["target_prod"], price)
    await state.clear()
    await message.answer(f"✅ {price} $", reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm_del_prod")
async def adm_del_prod(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    products = await get_all_products()
    await call.message.answer("🗑 Выберите товар:",
                               reply_markup=select_product_kb(products, "adm_dp_"))
    await call.answer()


@router.callback_query(F.data.startswith("adm_dp_"))
async def adm_dp_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data[7:])
    p = await get_product(prod_id)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"adm_dpyes_{prod_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="adm_back")],
    ])
    await call.message.answer(f"⚠️ Удалить «{p['name']}»?", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("adm_dpyes_"))
async def adm_dp_do(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await delete_product(int(call.data[10:]))
    await call.message.answer("✅ Удалено.", reply_markup=admin_main_kb())
    await call.answer()


@router.callback_query(F.data == "adm_drafts")
async def adm_drafts(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    drafts = await get_draft_products()
    if not drafts:
        await call.answer("Черновиков нет.", show_alert=True)
        return
    lines = ["📁 <b>Черновики:</b>\n"]
    for p in drafts:
        lines.append(f"• [{p['id']}] {p['name']} — {float(p['price']):.2f}$ | {p['cat_name']}")
    await call.message.answer("\n".join(lines), parse_mode="HTML",
                               reply_markup=back_to_admin_kb())
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  КУПОНЫ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_coupons")
async def adm_coupons(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("🎟 Купоны:", reply_markup=coupon_admin_kb())
    await call.answer()


@router.callback_query(F.data.startswith("adm_cpn_create_"))
async def adm_cpn_create(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    cpn_type = "percent" if call.data.endswith("_percent") else "fixed"
    await state.update_data(cpn_type=cpn_type)
    await state.set_state(AdminState.cpn_code)
    unit = "%" if cpn_type == "percent" else "$"
    await call.message.answer(f"🎟 Купон {unit} — введите код:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.cpn_code)
async def adm_cpn_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    code = message.text.strip().upper()
    if await get_coupon(code):
        await message.answer("❌ Такой купон уже есть.")
        return
    await state.update_data(cpn_code=code)
    await state.set_state(AdminState.cpn_value)
    d = await state.get_data()
    unit = "%" if d["cpn_type"] == "percent" else "$"
    await message.answer(f"💰 Значение ({unit}):", reply_markup=cancel_kb())


@router.message(AdminState.cpn_value)
async def adm_cpn_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        value = float(message.text.strip())
        assert value > 0
    except (ValueError, AssertionError):
        await message.answer("❌ Введите положительное число!")
        return
    await state.update_data(cpn_value=value)
    await state.set_state(AdminState.cpn_max_uses)
    await message.answer("🔢 Макс. использований (0 = ∞):", reply_markup=cancel_kb())


@router.message(AdminState.cpn_max_uses)
async def adm_cpn_max(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uses = int(message.text.strip())
        assert uses >= 0
    except (ValueError, AssertionError):
        await message.answer("❌ Целое число ≥ 0.")
        return
    await state.update_data(cpn_max=uses)
    await state.set_state(AdminState.cpn_expire_days)
    await message.answer("📅 Срок в днях (0 = ∞):", reply_markup=cancel_kb())


@router.message(AdminState.cpn_expire_days)
async def adm_cpn_expire(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        days = int(message.text.strip())
        assert days >= 0
    except (ValueError, AssertionError):
        await message.answer("❌ Целое число ≥ 0.")
        return
    d = await state.get_data()
    await create_coupon(d["cpn_code"], d["cpn_type"], d["cpn_value"], d["cpn_max"], days)
    await log_action(message.from_user.id, "create_coupon", {"code": d["cpn_code"]})
    await state.clear()
    unit = "%" if d["cpn_type"] == "percent" else "$"
    await message.answer(
        f"✅ Купон <b>{d['cpn_code']}</b>: {d['cpn_value']}{unit} | "
        f"Лимит: {d['cpn_max'] or '∞'} | Срок: {days or '∞'} дн.",
        parse_mode="HTML", reply_markup=admin_main_kb(),
    )


async def get_coupon(code: str):
    from db.database import get_coupon as _gc
    return await _gc(code)


@router.callback_query(F.data == "adm_cpn_list")
async def adm_cpn_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    coupons = await list_coupons()
    if not coupons:
        await call.answer("Купонов нет.", show_alert=True)
        return
    now = datetime.now(tz=timezone.utc)
    lines = ["📋 <b>Купоны:</b>\n"]
    for c in coupons:
        unit = "%" if c["type"] == "percent" else "$"
        exp  = ""
        if c["expire_at"]:
            exp = " ❌" if now > c["expire_at"] \
                  else f" ({(c['expire_at']-now).days} дн.)"
        lines.append(f"• <b>{c['code']}</b> {float(c['value'])}{unit} | "
                     f"{c['uses']}/{c['max_uses'] or '∞'}{exp}")
    await call.message.answer("\n".join(lines), parse_mode="HTML",
                               reply_markup=back_to_admin_kb())
    await call.answer()


@router.callback_query(F.data == "adm_cpn_delete")
async def adm_cpn_delete_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    coupons = await list_coupons()
    if not coupons:
        await call.answer("Купонов нет.", show_alert=True)
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🗑 {c['code']}", callback_data=f"adm_cpdel_{c['code']}")]
        for c in coupons
    ] + [[InlineKeyboardButton(text="❌ Отмена", callback_data="adm_cancel")]])
    await call.message.answer("Выберите купон:", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("adm_cpdel_"))
async def adm_cpdel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    code = call.data[10:]
    await delete_coupon(code)
    await call.message.answer(f"✅ Купон <b>{code}</b> удалён.", parse_mode="HTML",
                               reply_markup=admin_main_kb())
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  УМНАЯ РАССЫЛКА
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("📢 Аудитория:", reply_markup=broadcast_type_kb())
    await call.answer()


@router.callback_query(F.data == "bc_all")
async def bc_all(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(bc_uids=None)
    await state.set_state(AdminState.broadcast_text)
    await call.message.answer("📢 Текст рассылки:", reply_markup=cancel_kb())
    await call.answer()


@router.callback_query(F.data == "bc_balance")
async def bc_balance(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminState.bc_balance_thr)
    await call.message.answer("💰 Минимальный баланс в $:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.bc_balance_thr)
async def bc_balance_thr(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        thr = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    uids = await get_users_with_balance_above(thr)
    await state.update_data(bc_uids=uids)
    await state.set_state(AdminState.broadcast_text)
    await message.answer(f"✅ {len(uids)} пользователей. Введите текст:",
                         reply_markup=cancel_kb())


@router.callback_query(F.data.startswith("bc_product_"))
async def bc_product_sel_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    since_month = call.data == "bc_product_month"
    await state.update_data(bc_since_month=since_month)
    products = await get_all_products()
    await call.message.answer("🛍 Выберите товар:",
                               reply_markup=select_product_kb(products, "bc_prod_sel_"))
    await state.set_state(AdminState.bc_product_sel)
    await call.answer()


@router.callback_query(AdminState.bc_product_sel, F.data.startswith("bc_prod_sel_"))
async def bc_product_chosen(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data[12:])
    d = await state.get_data()
    since_days = 30 if d.get("bc_since_month") else None
    uids = await get_users_bought_product(prod_id, since_days=since_days)
    await state.update_data(bc_uids=uids)
    await state.set_state(AdminState.broadcast_text)
    await call.message.answer(
        f"✅ Покупателей: {len(uids)}. Введите текст:", reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(AdminState.broadcast_text)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    d    = await state.get_data()
    uids = d.get("bc_uids") or await get_all_user_ids()
    await state.clear()

    sent, failed = 0, 0
    for uid in uids:
        try:
            await bot.send_message(uid, message.text)
            sent += 1
        except Exception:
            failed += 1

    await log_action(message.from_user.id, "broadcast",
                     {"sent": sent, "failed": failed})
    await message.answer(
        f"✅ Рассылка!\nОтправлено: {sent} | Ошибок: {failed}",
        reply_markup=admin_main_kb(),
    )


# ════════════════════════════════════════════════════════════════════════════
#  НАЧИСЛИТЬ БАЛАНС
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_grant")
async def adm_grant(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminState.grant_uid)
    await call.message.answer("💰 Telegram ID:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.grant_uid)
async def adm_grant_uid(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID.")
        return
    user = await get_user(uid)
    if not user:
        await message.answer(f"❌ Пользователь {uid} не найден.")
        return
    await state.update_data(grant_uid=uid, grant_uname=user["username"])
    await state.set_state(AdminState.grant_amount)
    await message.answer(
        f"👤 @{user['username']} (баланс: {float(user['balance']):.2f} $)\n"
        f"Сумма (+ зачислить, - списать):",
        reply_markup=cancel_kb(),
    )


@router.message(AdminState.grant_amount)
async def adm_grant_amount(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    try:
        delta = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите число!")
        return
    d = await state.get_data()
    uid = d["grant_uid"]
    new_bal = await admin_set_balance(uid, delta)
    await log_action(message.from_user.id, "admin_grant",
                     {"uid": uid, "delta": delta})
    await state.clear()
    sign = "+" if delta >= 0 else ""
    await message.answer(
        f"✅ @{d['grant_uname']}: {sign}{delta:.2f} $\nБаланс: {new_bal:.2f} $",
        reply_markup=admin_main_kb(),
    )
    try:
        await bot.send_message(uid,
            f"💰 {'Начислено' if delta >= 0 else 'Списано'}: {sign}{delta:.2f} $\n"
            f"Баланс: {new_bal:.2f} $")
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
#  СТАТИСТИКА + ТОП РЕФЕРАЛОВ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    s = await get_stats()
    await call.message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего: <b>{s['users_total']}</b>\n"
        f"👤 Сегодня: <b>{s['users_today']}</b>\n\n"
        f"💰 Выручка: <b>{s['revenue']:.2f} $</b>\n"
        f"  — крипто: <b>{s['crypto_topup']:.2f} $</b>\n"
        f"💸 Рефералам: <b>{s['ref_paid']:.2f} $</b>\n"
        f"📦 Заказов: <b>{s['orders_count']}</b>",
        parse_mode="HTML",
        reply_markup=stats_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "adm_top_refs")
async def adm_top_refs(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    top = await get_top_referrers(limit=10)
    if not top:
        await call.answer("Рефералов пока нет.", show_alert=True)
        return
    lines = ["🏆 <b>Топ-10 рефералов</b>\n"]
    for i, r in enumerate(top, 1):
        lines.append(
            f"{i}. @{r['username'] or r['id']} — "
            f"👥 {r['ref_count']} чел. | 💸 {float(r['ref_earned']):.2f} $"
        )
    await call.message.answer("\n".join(lines), parse_mode="HTML",
                               reply_markup=back_to_admin_kb())
    await call.answer()


# ════════════════════════════════════════════════════════════════════════════
#  CRM — ПОИСК ПОЛЬЗОВАТЕЛЯ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_crm")
async def adm_crm(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminState.crm_uid)
    await call.message.answer("🔍 Введите Telegram ID пользователя:", reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminState.crm_uid)
async def adm_crm_result(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID.")
        return

    profile = await get_user_crm(uid)
    if not profile:
        await message.answer(f"❌ Пользователь {uid} не найден.")
        await state.clear()
        return

    await state.clear()
    user = profile["user"]
    orders = profile["orders"]
    refs   = profile["referrals"]

    status_map = {
        "pending": "⏳", "waiting_confirm": "⏳ ожид.",
        "in_work": "🔄", "completed": "✅", "cancelled": "❌"
    }

    orders_text = ""
    for o in orders[:10]:
        s = status_map.get(o["status"], o["status"])
        orders_text += (
            f"\n  • <code>{o['order_code']}</code> "
            f"{o['product_name']} {float(o['total']):.2f}$ {s}"
        )

    refs_text = ""
    for r in refs[:10]:
        refs_text += f"\n  • @{r['username'] or r['id']}"

    text = (
        f"🔍 <b>CRM: пользователь {uid}</b>\n\n"
        f"👤 @{user['username'] or '—'}\n"
        f"💰 Баланс: <b>{float(user['balance']):.2f} $</b>\n"
        f"💸 Реф. заработок: <b>{float(user['ref_earned']):.2f} $</b>\n"
        f"📅 Зарегистрирован: {user['joined_at'].strftime('%d.%m.%Y') if user.get('joined_at') else '—'}\n\n"
        f"📦 Заказов: <b>{len(orders)}</b>"
        + (orders_text or "\n  — нет заказов")
        + f"\n\n👥 Рефералов: <b>{len(refs)}</b>"
        + (refs_text or "\n  — нет рефералов")
    )
    await message.answer(text, parse_mode="HTML", reply_markup=back_to_admin_kb())


# ════════════════════════════════════════════════════════════════════════════
#  ЛОГ ДЕЙСТВИЙ
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_audit")
async def adm_audit(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    logs = await get_audit_log(limit=20)
    if not logs:
        await call.answer("Лог пуст.", show_alert=True)
        return
    lines = ["📜 <b>Последние 20 действий:</b>\n"]
    for entry in logs:
        ts = entry["created_at"].strftime("%d.%m %H:%M") if entry.get("created_at") else "—"
        uid = entry["user_id"] or "sys"
        lines.append(f"• <code>{ts}</code> [{uid}] {entry['action']}")
    await call.message.answer("\n".join(lines), parse_mode="HTML",
                               reply_markup=back_to_admin_kb())
    await call.answer()
