fromfrom aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import OP_CHANNEL
from db.database import ensure_user, get_user, set_subscribed, log_action
from keyboards.user_kb import welcome_inline_kb, op_check_kb

router = Router()


async def _is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(OP_CHANNEL, user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception:
        return False


async def _send_welcome(target: Message) -> None:
    await target.answer(
        "👋 <b>Добро пожаловать в магазин!</b>\n\n🔽 <b>Быстрый доступ:</b>",
        reply_markup=welcome_inline_kb(),
    )


async def _finish_start(target: Message, state: FSMContext,
                        user_id: int, deeplink: str | None = None) -> None:
    data = await state.get_data()
    ref_id = data.get("pending_ref_id")
    await set_subscribed(user_id, ref_id)
    await state.clear()
    await _send_welcome(target)
    if deeplink:
        from handlers.shop import handle_start_deeplink
        await handle_start_deeplink(target, deeplink)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    user_id  = message.from_user.id
    username = message.from_user.username or ""
    args     = message.text.split(maxsplit=1)
    param    = args[1].strip() if len(args) > 1 else ""

    ref_id: int | None = None
    deeplink: str | None = None

    if param.startswith("cat_") or param.startswith("prod_"):
        deeplink = param
    elif param.isdigit():
        ref_id = int(param)
        if ref_id == user_id:
            ref_id = None

    await ensure_user(user_id, username)
    await log_action(user_id, "start", {"param": param})
    await state.update_data(pending_ref_id=ref_id, deeplink=deeplink)

    user = await get_user(user_id)
    if user and user["is_subscribed"]:
        await _send_welcome(message)
        if deeplink:
            from handlers.shop import handle_start_deeplink
            await handle_start_deeplink(message, deeplink)
        return

    if await _is_subscribed(bot, user_id):
        await _finish_start(message, state, user_id, deeplink)
        return

    await message.answer(
        "👋 Для доступа нужно подписаться:",
        reply_markup=op_check_kb(),
    )


@router.callback_query(F.data == "check_sub")
async def callback_check_sub(call: CallbackQuery, state: FSMContext, bot: Bot):
    user_id  = call.from_user.id
    username = call.from_user.username or ""
    await ensure_user(user_id, username)

    if not await _is_subscribed(bot, user_id):
        await call.answer("❌ Вы ещё не подписались.", show_alert=True)
        return

    await call.answer("✅ Подписка подтверждена!")
    try:
        await call.message.delete()
    except Exception:
        pass

    data = await state.get_data()
    deeplink = data.get("deeplink")
    await _finish_start(call.message, state, user_id, deeplink)


@router.callback_query(F.data == "topup_menu")
async def topup_menu(call: CallbackQuery):
    from keyboards.user_kb import balance_kb
    from db.database import get_user as gu
    user = await gu(call.from_user.id)
    bal = float(user["balance"]) if user else 0.0
    await call.message.answer(
        f"💰 <b>Баланс: {bal:.2f} $</b>\n\nВыберите способ пополнения:",
        reply_markup=balance_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "profile_inline")
async def profile_inline(call: CallbackQuery, bot: Bot):
    from handlers.balance import send_profile
    await send_profile(call.message, call.from_user, bot)
    await call.answer()

