from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from services.telegram.filters.role import RoleFilter

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.callback_query(lambda c: c.data.startswith("reply_to_user:"))
async def reply_to_user_handler(callback: CallbackQuery, state: FSMContext):
    # Извлекаем ID пользователя из callback_data
    user_id = int(callback.data.split(":", 1)[1])

    # Сохраняем ID пользователя в состоянии для последующего ответа
    await state.set_state("waiting_for_reply")
    await state.update_data(target_user_id=user_id)

    await callback.message.answer(f"Введите сообщение для отправки пользователю {user_id}:")
    await callback.answer()


@router.message(StateFilter("waiting_for_reply"))
async def send_reply_to_user(message: Message, state: FSMContext):
    # Получаем ID пользователя из состояния
    data = await state.get_data()
    target_user_id = data.get("target_user_id")

    if not target_user_id:
        await message.answer("Ошибка: не найден ID пользователя для ответа.")
        await state.clear()
        return

    try:
        # Отправляем сообщение пользователю
        await message.bot.send_message(
            chat_id=target_user_id,
            text=f"*Сообщение от администратора*:\n\n{message.text}",
            parse_mode=ParseMode.MARKDOWN
        )

        await message.answer(f"✅ Сообщение успешно отправлено пользователю {target_user_id}.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке сообщения: {e}")

    # Очищаем состояние
    await state.clear()
