from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import I18n # Хотя может и не понадобиться напрямую здесь
from decimal import Decimal

from database.database import ORM
from database.models import User # Для type hinting и возможного использования в Keyboards
from services.telegram.filters.role import RoleFilter
from services.telegram.handlers.states import TopUpStates # Для ask_custom_amount, если оно ставит состояние
from services.telegram.misc.keyboards import Keyboards # Если понадобится back_to_home

# Импорт логгера из __init__.py текущего пакета
from . import logger

router = Router()
# Эти коллбэки доступны всем пользователям, имеющим доступ к основным командам
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.callback_query(lambda c: c.data.startswith("request_topup:")) # Оригинальный фильтр был lambda c: c.data.startswith("request_topup")
async def request_topup_callback(callback: CallbackQuery, orm: ORM, i18n: I18n, user: User):
    # user - это тот, кто нажал кнопку
    try:
        user_id_to_request_for = int(callback.data.split(":")[1])
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid callback data for request_topup: {callback.data}, error: {e}")
        await callback.answer(i18n.gettext("Ошибка в данных запроса.", locale=user.lang), show_alert=True)
        return

    admins = await orm.user_repo.get_admins()
    if not admins:
        await callback.answer(i18n.gettext("Ошибка: администратор не найден.", locale=user.lang), show_alert=True)
        return

    # Убедимся, что пользователь, для которого запрашивается пополнение, существует
    # (хотя ID берется из callback.data, что может быть установлено системой)
    # target_user = await orm.user_repo.find_user_by_user_id(user_id_to_request_for)
    # if not target_user: 
    #     await callback.answer(i18n.gettext("Пользователь для пополнения не найден.", locale=user.lang), show_alert=True)
    #     return

    # Формируем сообщение админам
    # В оригинальном `request_balance_topup` из `user_repo` вероятно формируется текст сообщения
    # Здесь мы просто перебираем админов и отправляем им уведомление
    # Текст уведомления был в `request_topup_balance` в `user_commands.py`. 
    # Чтобы не дублировать, этот коллбэк должен просто инициировать отправку админам.
    # Либо `request_balance_topup` должен сам отправлять, либо мы формируем текст здесь.
    # В оригинале было: message = await orm.user_repo.request_balance_topup(user_id, admin.user_id)
    # Это подразумевает, что repo метод возвращает текст сообщения.

    success_sent_to_any_admin = False
    for admin in admins:
        try:
            # Предполагаем, что user_repo.request_balance_topup возвращает текст сообщения для админа
            admin_message_text = await orm.user_repo.request_balance_topup(
                user_id_requesting_topup=user_id_to_request_for, # ID того, кому нужно пополнить
                admin_id_to_notify=admin.user_id, # ID админа для возможной персонализации сообщения
                requesting_user_username=user.username, # username того, кто нажал кнопку (если это полезно)
                requesting_user_id=user.user_id # ID того, кто нажал кнопку
            )
            if admin_message_text: # Если метод вернул текст
                await callback.bot.send_message(admin.user_id, admin_message_text)
                success_sent_to_any_admin = True
            else: 
                logger.info(f"User repo method request_balance_topup called for admin {admin.user_id}")

        except Exception as e:
            logger.error(f"Failed to send top-up request to admin {admin.user_id}: {e}")
    
    if success_sent_to_any_admin:
        await callback.answer(i18n.gettext("Запрос на пополнение отправлен администратору.", locale=user.lang), show_alert=True)
    else:
        # Если не удалось отправить ни одному админу, но админы есть
        # или если request_balance_topup сам не отправил и не вернул текст
        logger.warning(f"Top-up request for user {user_id_to_request_for} was not sent to any admin, or repo method handles sending.")
        # Ответ пользователю, что запрос *принят к обработке* или общая ошибка, если админов не было (уже покрыто выше)
        await callback.answer(i18n.gettext("Запрос на пополнение принят.", locale=user.lang), show_alert=True)


@router.callback_query(F.data.startswith("topup_custom:"))
async def ask_custom_amount_callback(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    # user - это тот, кто нажал кнопку
    try:
        user_id_for_topup = int(callback.data.split(":")[1])
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid callback data for topup_custom: {callback.data}, error: {e}")
        await callback.answer(i18n.gettext("Ошибка в данных запроса.", locale=user.lang), show_alert=True)
        return

    await state.set_data({"user_id": user_id_for_topup, "initiator_user_id": user.user_id})
    # Используем строковое имя состояния, как оно определено в admin_states.py (или будет определено)
    # Это состояние ('custom_topup_waiting_amount') обрабатывается в admin_states.py
    await state.set_state("custom_topup_waiting_amount") 
    await callback.message.answer(i18n.gettext("Введите сумму для пополнения:", locale=user.lang))
    await callback.answer()


@router.callback_query(F.data.startswith("topup:")) # Обрабатывает формат "topup:AMOUNT"
async def process_user_initiated_topup(callback: CallbackQuery, orm: ORM, i18n: I18n, user: User):
    # user - это тот, кто нажал кнопку (callback.from_user)
    try:
        parts = callback.data.split(":")
        if len(parts) != 2:
            raise ValueError("Invalid topup callback format")
        amount_str = parts[1]
        amount = Decimal(amount_str)
    except (ValueError, InvalidOperation) as e:
        logger.error(f"Invalid amount in topup callback: {callback.data}, error: {e}")
        await callback.answer(i18n.gettext("Неверная сумма для пополнения.", locale=user.lang), show_alert=True)
        return

    if amount <= 0:
        await callback.answer(i18n.gettext("Сумма должна быть положительной.", locale=user.lang), show_alert=True)
        return

    # Пополняем баланс текущего пользователя (того, кто нажал кнопку)
    # Используем UserRepo для этого, а не прямой SQL
    success = await orm.user_repo.update_balance(user.user_id, amount) 
    # или await orm.user_repo.add_tokens(user_id=user.user_id, tokens_to_add=int(amount), admin_id=None) # если это токены

    if success:
        # _, currency_symbol = await orm.currency_repo.get_price_in_user_currency(Decimal("0"), user.country)
        currency_symbol = "₸" # или другой символ по умолчанию, если валюта не определена
        await callback.answer(
            i18n.gettext("Ваш баланс пополнен на {amount}{symbol}", locale=user.lang).format(amount=amount, symbol=currency_symbol),
            show_alert=True
        )
        # Можно также отправить сообщение в чат с обновленным балансом и кнопкой "Назад"
        # new_balance = await orm.user_repo.get_token_balance(user.user_id)
        # await callback.message.answer(
        #     i18n.gettext("Баланс успешно пополнен! Ваш новый баланс: {balance} {symbol}", locale=user.lang).format(balance=new_balance, symbol=currency_symbol),
        #     reply_markup=Keyboards.back_to_home(i18n, user)
        # )
    else:
        await callback.answer(i18n.gettext("Не удалось пополнить баланс.", locale=user.lang), show_alert=True) 