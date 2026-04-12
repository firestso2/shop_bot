"""
P2P чат: изолированная переписка покупателя и администратора по заказу.
Логика:
  - Все сообщения покупателя (пока order in_work) → пересылаются взявшему заказ админу
  - Все сообщения взявшего админа → пересылаются покупателю
  - Кнопки у админа: запросить данные / возврат / продлить / завершить
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS, ORDER_EXTEND_HOURS, REVIEW_CHANNEL
from db.database import (
    get_order_by_code, update_order_status, extend_order_deadline,
    get_in_work_order_for_user, get_in_work_order_for_admin,
    add_balance, log_action, save_p2p_message,
)
from keyboards.user_kb import review_prompt_kb
from keyboards.admin_kb import p2p_admin_control_kb

router = Router()


# ════════════════════════════════════════════════════════════════════════════
#  RELAY: сообщения от покупателя → взявшему заказ админу
# ════════════════════════════════════════════════════════════════════════════

async def relay_user_to_admin(message: Message, bot: Bot) -> bool:
    """
    Если у пользователя есть активный заказ in_work — пересылаем сообщение админу.
    Возвращает True если сообщение было перехвачено.
    """
    order = await get_in_work_order_for_user(message.from_user.id)
    if not order or not order.get("assigned_admin"):
        return False

    admin_id   = order["assigned_admin"]
    order_code = order["order_code"]
    uname = (f"@{message.from_user.username}"
             if message.from_user.username else str(message.from_user.id))

    header = f"💬 <b>Покупатель {uname}</b> | Заказ <code>{order_code}</code>\n"

    try:
        if message.text:
            sent = await bot.send_message(
                admin_id, header + message.text,
                parse_mode="HTML",
                reply_markup=p2p_admin_control_kb(order_code),
            )
        elif message.document:
            sent = await bot.send_document(
                admin_id, message.document.file_id,
                caption=(header + (message.caption or "")),
                parse_mode="HTML",
                reply_markup=p2p_admin_control_kb(order_code),
            )
        elif message.photo:
            sent = await bot.send_photo(
                admin_id, message.photo[-1].file_id,
                caption=(header + (message.caption or "")),
                parse_mode="HTML",
                reply_markup=p2p_admin_control_kb(order_code),
            )
        else:
            sent = await bot.send_message(
                admin_id,
                header + "[Медиа без текста]",
                parse_mode="HTML",
                reply_markup=p2p_admin_control_kb(order_code),
            )

        await save_p2p_message(order_code, True, message.message_id, sent.message_id)
    except Exception:
        pass

    return True


async def relay_admin_to_user(message: Message, bot: Bot,
                              order: dict) -> bool:
    """
    Пересылаем сообщение от администратора покупателю.
    Возвращает True если перехвачено.
    """
    user_id    = order["user_id"]
    order_code = order["order_code"]

    try:
        if message.text:
            sent = await bot.send_message(
                user_id,
                f"👤 <b>Администратор:</b>\n{message.text}",
                parse_mode="HTML",
            )
        elif message.document:
            sent = await bot.send_document(
                user_id, message.document.file_id,
                caption=f"👤 <b>Администратор:</b>\n{message.caption or ''}",
                parse_mode="HTML",
            )
        elif message.photo:
            sent = await bot.send_photo(
                user_id, message.photo[-1].file_id,
                caption=f"👤 <b>Администратор:</b>\n{message.caption or ''}",
                parse_mode="HTML",
            )
        else:
            sent = await bot.send_message(
                user_id, "👤 <b>Администратор:</b>\n[Медиа]",
                parse_mode="HTML",
            )
        await save_p2p_message(order_code, False, message.message_id, sent.message_id)
    except Exception:
        pass

    return True


# ════════════════════════════════════════════════════════════════════════════
#  КНОПКА «Взять заказ» — из уведомления всем админам
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("take_order_"))
async def take_order(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return

    order_code = call.data[11:]
    order = await get_order_by_code(order_code)

    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order["status"] != "waiting_confirm":
        await call.answer("Заказ уже взят или закрыт.", show_alert=True)
        return

    # Назначаем заказ текущему админу
    await update_order_status(order_code, "in_work",
                               assigned_admin=call.from_user.id)
    await log_action(call.from_user.id, "order_taken", {"order_code": order_code})

    # Редактируем сообщения у ОСТАЛЬНЫХ админов
    for admin_id in ADMIN_IDS:
        if admin_id == call.from_user.id:
            continue
        try:
            await bot.edit_message_text(
                chat_id=admin_id,
                message_id=call.message.message_id,
                text=(
                    f"📦 Заказ <code>{order_code}</code>\n"
                    f"⚠️ <b>Заказ взят другим администратором.</b>"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Обновляем своё сообщение
    uname = order.get("username", str(order["user_id"]))
    await call.message.edit_text(
        f"📦 <b>Заказ {order_code} — В работе</b>\n"
        f"👤 {uname} (ID: {order['user_id']})\n"
        f"📋 Данные: {order.get('user_data','—')}\n\n"
        f"Все сообщения покупателя будут приходить сюда.\n"
        f"Отвечайте <b>обычным текстом</b> — покупатель получит ответ.",
        parse_mode="HTML",
        reply_markup=p2p_admin_control_kb(order_code),
    )

    # Уведомляем покупателя
    try:
        await bot.send_message(
            order["user_id"],
            f"✅ Администратор взял ваш заказ в работу.\n"
            f"🔖 Заказ: <code>{order_code}</code>\n\n"
            f"Вы можете писать сообщения в этот чат — "
            f"администратор их получит.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await call.answer("✅ Заказ взят!")


# ════════════════════════════════════════════════════════════════════════════
#  КНОПКИ УПРАВЛЕНИЯ ЗАКАЗОМ (у администратора)
# ════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("p2p_request_code_"))
async def p2p_request_code(call: CallbackQuery, bot: Bot):
    """Запросить данные/код у покупателя по шаблонному тексту."""
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return

    order_code = call.data[17:]
    order = await get_order_by_code(order_code)
    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return

    request_text = order.get("data_request_text") or "Пожалуйста, отправьте необходимые данные."

    try:
        await bot.send_message(
            order["user_id"],
            f"👤 <b>Администратор:</b>\n{request_text}",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await call.answer("✉️ Запрос отправлен пользователю")


@router.callback_query(F.data.startswith("p2p_refund_"))
async def p2p_refund(call: CallbackQuery, bot: Bot):
    """Сделать возврат и закрыть заказ."""
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return

    order_code = call.data[11:]
    order = await get_order_by_code(order_code)
    if not order or order["status"] not in ("waiting_confirm", "in_work"):
        await call.answer("Заказ уже закрыт", show_alert=True)
        return

    total = float(order["total"])
    await add_balance(order["user_id"], total)
    await update_order_status(order_code, "cancelled")
    await log_action(call.from_user.id, "order_refund",
                     {"order_code": order_code, "amount": total})

    # Уведомляем покупателя
    try:
        await bot.send_message(
            order["user_id"],
            f"↩️ Заказ <code>{order_code}</code> отменён.\n"
            f"Сумма <b>{total:.2f} $</b> возвращена на баланс.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        await call.message.edit_text(
            call.message.text + "\n\n↩️ <b>ВОЗВРАТ СДЕЛАН. Чат закрыт.</b>",
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception:
        pass
    await call.answer("↩️ Возврат выполнен, чат закрыт.")


@router.callback_query(F.data.startswith("p2p_extend_"))
async def p2p_extend(call: CallbackQuery):
    """Продлить дедлайн заказа."""
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return

    order_code = call.data[11:]
    await extend_order_deadline(order_code, ORDER_EXTEND_HOURS)
    await call.answer(f"⏰ Время продлено на {ORDER_EXTEND_HOURS} ч.")


@router.callback_query(F.data.startswith("p2p_complete_"))
async def p2p_complete(call: CallbackQuery, bot: Bot):
    """Завершить заказ: всё готово, просим отзыв."""
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return

    order_code = call.data[13:]
    order = await get_order_by_code(order_code)
    if not order or order["status"] == "completed":
        await call.answer("Уже завершён", show_alert=True)
        return

    await update_order_status(order_code, "completed")
    await log_action(call.from_user.id, "order_completed",
                     {"order_code": order_code})

    # Покупатель получает финальное сообщение + кнопку отзыва
    try:
        await bot.send_message(
            order["user_id"],
            f"✅ <b>Заказ выполнен!</b>\n"
            f"🔖 <code>{order_code}</code>\n\n"
            f"Пожалуйста, оставьте отзыв в {REVIEW_CHANNEL} — "
            f"это очень поможет нам!",
            parse_mode="HTML",
            reply_markup=review_prompt_kb(),
        )
    except Exception:
        pass

    try:
        await call.message.edit_text(
            call.message.text + "\n\n✅ <b>ЗАКАЗ ЗАВЕРШЁН.</b>",
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception:
        pass
    await call.answer("✅ Заказ завершён!")
