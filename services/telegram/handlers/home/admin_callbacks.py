from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message # Message для callback.message
from aiogram.utils.i18n import I18n
from aiogram.utils.markdown import hcode

from database.database import ORM
from database.models import User
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import UserListPagination
from services.telegram.misc.keyboards import Keyboards
from services.telegram.handlers.states import DeleteUserStates, BalanceStates, AdminStates

# Импорт логгера из __init__.py текущего пакета
from . import logger

router = Router()
# Все callback хэндлеры в этом файле предназначены для админов
router.callback_query.filter(RoleFilter(roles=["admin"]))


# Этот хэндлер используется как точка входа для users_list и для пагинации.
# Он не регистрируется сам по себе как callback, а вызывается другими хэндлерами.
async def show_users_page(callback: CallbackQuery, orm: ORM, i18n: I18n, user: User, page: int):
    users_db = await orm.user_repo.find_all()

    users_per_page = 5
    total_pages = (len(users_db) + users_per_page - 1) // users_per_page
    start_idx = page * users_per_page
    end_idx = start_idx + users_per_page
    page_users = users_db[start_idx:end_idx]

    admin_lang = user.lang # Язык админа, который просматривает список

    message_parts = [i18n.gettext("📊 Список всех пользователей:", locale=admin_lang) + "\n\n"]

    for idx, list_user_item in enumerate(page_users, start=start_idx + 1):
        phone_number_display = list_user_item.phone_number or i18n.gettext('Не указан', locale=admin_lang)
        user_info = (
            f"🔹 <b>{idx}. {hcode(list_user_item.username or i18n.gettext('Без username', locale=admin_lang))}</b>\n"
            f"🆔 <i>{i18n.gettext('ID', locale=admin_lang)}:</i> {hcode(list_user_item.user_id)}\n"
            f"👤 <i>{i18n.gettext('Роль', locale=admin_lang)}:</i> {hcode(list_user_item.role)}\n"
            f"🌍 <i>{i18n.gettext('Язык', locale=admin_lang)}:</i> {hcode(list_user_item.lang)}\n"
            f"📱 <i>{i18n.gettext('Телефон', locale=admin_lang)}:</i> {hcode(phone_number_display)}\n"
            f"💰 {i18n.gettext('Баланс токенов', locale=admin_lang)}: {list_user_item.token_balance}\n"
            f"<i>{'─' * 30}</i>\n"
        )
        message_parts.append(user_info)

    message_parts.append(f"\n{i18n.gettext('Всего пользователей', locale=admin_lang)}: {len(users_db)}")

    full_message = "".join(message_parts)
    keyboard = Keyboards.get_users_list_keyboard(total_pages, page, i18n, user)

    # Важно: callback.message может быть None, если это первый вызов (не редактирование)
    # Однако, show_users_list и navigate_users_list используют callback.message.edit_text или answer
    if callback.message: 
        try:
            await callback.message.edit_text(
                full_message,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        except Exception as e: # Если не удалось отредактировать (например, сообщение слишком старое)
            logger.warning(f"Could not edit message for users list, sending new one: {e}")
            await callback.bot.send_message( # Отправляем новое сообщение, если редактирование не удалось
                callback.from_user.id,
                full_message,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
    else: # На случай, если callback.message действительно None (хотя это маловероятно для этих хэндлеров)
         await callback.bot.send_message(
            callback.from_user.id,
            full_message,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    await callback.answer()


@router.callback_query(F.data == "users_list")
async def show_users_list(callback: CallbackQuery, orm: ORM, i18n: I18n, user: User):
    # user здесь - админ, который нажал кнопку
    await show_users_page(callback, orm, i18n, user, page=0)


@router.callback_query(UserListPagination.filter())
async def navigate_users_list(callback: CallbackQuery, callback_data: UserListPagination, orm: ORM, i18n: I18n, user: User):
    # user здесь - админ
    await show_users_page(callback, orm, i18n, user, page=callback_data.page)


@router.callback_query(F.data == "back_to_admin")
async def back_to_admin_panel(callback: CallbackQuery, i18n: I18n, user: User):
    # user здесь - админ
    await callback.message.edit_text(
        i18n.gettext("Добро пожаловать в админ панель!", locale=user.lang),
        reply_markup=Keyboards.admin_panel(i18n, user)
    )
    await callback.answer()


@router.callback_query(F.data == "delete_user_by_id")
async def ask_for_user_id_to_delete(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    # user здесь - админ
    await state.set_state(DeleteUserStates.waiting_for_user_id)
    await callback.message.answer( # Используем answer, чтобы не редактировать предыдущее меню
        i18n.gettext("Введите user_id пользователя, которого хотите удалить:", locale=user.lang)
    )
    await callback.answer() # Отвечаем на коллбэк, чтобы убрать часики


@router.callback_query(F.data == "set_pricing")
async def ask_for_new_price(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    # user здесь - админ
    await callback.message.answer(
        i18n.gettext("Введите новую стоимость анализа:", locale=user.lang)
    )
    await state.set_state(BalanceStates.waiting_for_pricing)
    await callback.answer()


@router.callback_query(F.data == "admin_topup")
async def start_admin_topup(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    # user здесь - админ
    await state.set_state(AdminStates.admin_topup_wait)
    await callback.message.answer(
        i18n.gettext(
            "enter_user_id_and_amount", # Эта строка должна быть в файлах локализации
            locale=user.lang 
        ),
        parse_mode=ParseMode.HTML # Как было в оригинале
    )
    await callback.answer()


@router.callback_query(F.data == "admin_check_balance")
async def ask_user_id_for_check(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    # user здесь - админ
    await state.set_state("admin_check_balance_wait") # Используем строковое имя состояния как в оригинале
    await callback.message.answer(
        i18n.gettext("Введите user_id для проверки:", locale=user.lang)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_history")
async def ask_user_id_for_history(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    # user здесь - админ
    await state.set_state("admin_history_wait") # Строковое имя состояния
    await callback.message.answer(
        i18n.gettext("Введите user_id для просмотра истории:", locale=user.lang)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_reset_balance")
async def ask_user_id_for_reset(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    # user здесь - админ
    await state.set_state("admin_reset_wait") # Строковое имя состояния
    await callback.message.answer(
        i18n.gettext("Введите user_id для обнуления баланса:", locale=user.lang)
    )
    await callback.answer()


@router.callback_query(F.data == "nothing")
async def nothing_callback(callback: CallbackQuery):
    await callback.answer() 