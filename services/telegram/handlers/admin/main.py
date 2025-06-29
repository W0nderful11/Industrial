import logging
from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command,StateFilter
from aiogram.types import CallbackQuery, InlineQueryResultArticle, InputTextMessageContent, InlineQuery, Message, \
    InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.i18n import I18n
from services.telegram.handlers.states import BroadcastStates, AdminStates, TokenTopUpStates
from aiogram.fsm.context import FSMContext
from services.telegram.misc.callbacks import BroadcastLangCallback,BroadcastCallback, MassTokenLangCallback, UserListPagination, UserSearchPagination
from database.models import User, Transaction
from decimal import Decimal, InvalidOperation
from database.repo.exceptions import InvalidAmountError


from database.database import ORM
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import AdminCallback, RenewSubscription
from services.telegram.misc.keyboards import Keyboards
import asyncio
from config import Environ
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(RoleFilter(roles=["admin"]))
router.callback_query.filter(RoleFilter(roles=["admin"]))
router.inline_query.filter(RoleFilter(roles=["admin"]))


# @router.callback_query(AdminCallback.filter(F.action == "renew_subscription"))
# async def renew_subscription_for_user(callback: CallbackQuery,
#                        callback_data: AdminCallback,
#                        orm: ORM,
#                        i18n: I18n):
#     await callback.message.edit_text(i18n.gettext("Введите id пользователя"))

@router.inline_query(F.query.startswith('user '))
async def find_user(inq: InlineQuery, orm: ORM, i18n: I18n):
    query = inq.query[5:]
    user_lang = inq.from_user.language_code if inq.from_user.language_code in i18n.available_locales else 'ru'

    results = []
    users = await orm.user_repo.find_all()
    users = filter(lambda x: (x.username and query.lower() in x.username.lower())
                             or (x.fullname and query.lower() in x.fullname.lower())
                             or str(x.user_id).find(query) != -1, users)

    if query:
        for user in users:
            name_label = i18n.gettext("Имя:", locale=user_lang)
            workplace_label = i18n.gettext("Место работы:", locale=user_lang)
            country_label = i18n.gettext("Страна:", locale=user_lang)
            city_label = i18n.gettext("Город:", locale=user_lang)
            number_label = i18n.gettext("Номер:", locale=user_lang)
            
            message_text = (
                f"/find Имя пользователя @{user.username or 'N/A'}\n"
                f"{name_label} {user.fullname or i18n.gettext('Не указано', locale=user_lang)}\n"
                f"{workplace_label} {user.affiliate or i18n.gettext('Не указано', locale=user_lang)}\n"
                f"{country_label} {user.country or i18n.gettext('Не указано', locale=user_lang)}\n"
                f"{city_label} {user.city or i18n.gettext('Не указано', locale=user_lang)}\n"
                f"{number_label} {user.phone_number or i18n.gettext('Не указано', locale=user_lang)}"
            )

            results.append(
                InlineQueryResultArticle(
                    id=str(user.id),
                    title=f'{user.fullname or "N/A"} - @{user.username or "N/A"}',
                    input_message_content=InputTextMessageContent(
                        message_text=message_text,
                        parse_mode=ParseMode.HTML
                    ),
                    description=f"{user.city or ''} {user.affiliate or ''}"
                )
            )
    await inq.answer(results=results, cache_time=10)

@router.message(Command("find"))
async def find_command(message: Message, orm: ORM, i18n: I18n):
    username = message.text.split("\n")[0].split()[-1].replace('@', '')
    user = await orm.user_repo.find_user_by_username(username)
    await message.answer(i18n.gettext("Выберите длительность подписки", locale=user.lang),
                         reply_markup=Keyboards.months(user, i18n))

@router.callback_query(RenewSubscription.filter())
async def renew_user_subscription(callback: CallbackQuery, callback_data: RenewSubscription, orm: ORM, i18n: I18n):
    sub = await orm.subscription_repo.set_subscription(callback_data.user_id, period=callback_data.months*30)
    user = await orm.user_repo.find_user_by_user_id(callback_data.user_id)
    await callback.message.edit_text(i18n.gettext("Вы успешно продлили подписку пользователя @{}", locale=user.lang).format(user.username),
                                     reply_markup=Keyboards.back_to_home(i18n, user))
    await callback.bot.send_message(callback_data.user_id, i18n.gettext("Вам продлили подписку \nСрок ее окончания: \n{}", locale=user.lang).format(sub.date_end),
                                    reply_markup=Keyboards.back_to_home(i18n, user))

@router.callback_query(F.data == "broadcast")
async def handle_broadcast(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    if user.role != 'admin':
        await callback.answer(i18n.gettext("У вас нет доступа к этой функции", locale=user.lang))
        return

    await callback.message.answer(
        i18n.gettext("Выберите язык рассылки:", locale='ru'),  # Forcing Russian for admin panel
        reply_markup=Keyboards.broadcast_lang_options(i18n)
    )
    await state.set_state(BroadcastStates.waiting_for_language)

@router.callback_query(BroadcastLangCallback.filter())
async def select_broadcast_language(callback: CallbackQuery, callback_data: BroadcastLangCallback, state: FSMContext, i18n: I18n, user: User):
    if user.role != 'admin':
        await callback.answer(i18n.gettext("У вас нет доступа к этой функции", locale=user.lang))
        return

    selected_lang = callback_data.lang
    await state.update_data(broadcast_language=selected_lang)

    prompt = {
        'en': i18n.gettext("Enter the message in English:", locale='ru'),
        'ru': i18n.gettext("Введите сообщение на русском языке:", locale='ru'),
    }
    
    # Удаляем сообщение с кнопками выбора языка
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение при выборе языка рассылки: {e}")

    # Отправляем новое сообщение с запросом текста
    await callback.message.answer(prompt.get(selected_lang, "Введите сообщение:"))
    await state.set_state(BroadcastStates.waiting_for_message)
    await callback.answer() # Отвечаем на коллбек

@router.message(BroadcastStates.waiting_for_message,F.text)
async def confirm_broadcast_message(message: Message,
                                   state: FSMContext,
                                   user: User,
                                   i18n: I18n):
    if len(message.text) > 4096:
        await message.answer(
            i18n.gettext("Сообщение слишком длинное. Максимальная длина - 4096 символов.", locale=user.lang)
        )
        return

    await state.update_data(broadcast_message=message.text)

    # Используем user.lang для локализации кнопок подтверждения, если это язык админа
    # Если нужен строго русский интерфейс для админки, оставляем locale='ru'
    # Судя по вашему запросу на локализацию других частей админки, лучше использовать язык админа.
    # Убедимся, что объект user здесь - это админ, а не целевой пользователь рассылки.
    # В данном контексте message.from_user это админ.
    admin_lang = message.from_user.language_code if message.from_user.language_code in ['ru', 'en'] else 'ru'

    builder = Keyboards.broadcast_confirmation(message.from_user.id, i18n, lang_code=admin_lang) # Передаем язык админа

    await message.answer(
        i18n.gettext("Предварительный просмотр сообщения:\n\n{}\n\nПодтвердить рассылку?", locale=admin_lang).format(message.text),
        reply_markup=builder
    )
    await state.set_state(BroadcastStates.confirming_message)

@router.callback_query(BroadcastCallback.filter(F.action == "accept"), BroadcastStates.confirming_message)
async def perform_broadcast(callback: CallbackQuery,
                            callback_data: BroadcastCallback,
                            state: FSMContext,
                            orm: ORM,
                            i18n: I18n,
                            env: Environ):
    data = await state.get_data()
    broadcast_message = data.get("broadcast_message")
    broadcast_language = data.get("broadcast_language")
    admin_lang = callback.from_user.language_code if callback.from_user.language_code in ['ru', 'en'] else 'ru'

    if not broadcast_message or not broadcast_language:
        await callback.message.edit_text(i18n.gettext("Ошибка: Не удалось получить данные для рассылки.", locale=admin_lang))
        await state.clear()
        return

    if callback_data.action == "accept":
        await callback.message.delete()
        users = await orm.user_repo.get_users_by_language(broadcast_language)
        
        # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
        logger.info(f"Запущена рассылка для языка '{broadcast_language}'. Найдено пользователей: {len(users)}")
        if not users:
            logger.warning(f"Не найдено пользователей для рассылки на языке: {broadcast_language}")
        # --- КОНЕЦ ЛОГИРОВАНИЯ ---

        sent_count = 0
        failed_count = 0
        for user_in_list in users: # Изменено имя переменной цикла во избежание конфликта с user из аргументов функции
            try:
                await callback.bot.send_message(chat_id=user_in_list.user_id, text=broadcast_message)
                sent_count += 1
                await asyncio.sleep(0.1)  # Небольшая задержка для избежания флуда
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения пользователю {user_in_list.user_id}: {e}")
                failed_count += 1

        lang_name_map = {"ru": "русского", "en": "английского"}
        target_lang_readable = lang_name_map.get(broadcast_language, broadcast_language)

        report_text = (
            f"Рассылка для языка '{target_lang_readable}' завершена.\n"
            f"Успешно отправлено: {sent_count}\n"
            f"Не удалось отправить: {failed_count}\n\n"
            f"Текст сообщения:\n{broadcast_message}"
        )

        # Отправка отчета всем администраторам и в канал
        admins = await orm.user_repo.get_admins()
        for admin in admins:
            try:
                await callback.bot.send_message(admin.user_id, report_text)
            except Exception as e:
                logger.error(f"Не удалось отправить отчет о рассылке администратору {admin.user_id}: {e}")
        
        if env.channel_id:
            try:
                await callback.bot.send_message(env.channel_id, report_text)
            except Exception as e:
                logger.error(f"Не удалось отправить отчет о рассылке в канал {env.channel_id}: {e}")

    await state.clear()

@router.callback_query(BroadcastCallback.filter(F.action == "cancel"), BroadcastStates.confirming_message)
async def cancel_broadcast(callback: CallbackQuery,
                           callback_data: BroadcastCallback,
                           state: FSMContext,
                           i18n: I18n,
                           user: User):
    await callback.message.answer(
        i18n.gettext("Рассылка отменена", locale='ru')
    )
    await state.clear()

@router.callback_query(F.data == "topup_balance")
async def ask_user_balance(callback: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    await state.set_state("waiting_for_user_id_balance")
    await callback.message.answer(i18n.gettext("Введите user_id и сумму через пробел:", locale=user.lang))

async def _parse_user_input(text: str) -> tuple[int, Decimal]:
    try:
        user_id_str, amount_str = text.strip().split()
        return int(user_id_str), Decimal(amount_str)
    except (ValueError, InvalidOperation) as e:
        logger.error(f"Invalid input format: {text} - {str(e)}")
        raise
    
@router.message(StateFilter("waiting_for_user_id_balance"))
async def process_topup_balance(message: Message, orm: ORM, i18n: I18n):
    try:
        user_id, amount = await _parse_user_input(message.text)
        if await orm.user_repo.update_balance(user_id, amount):
            await message.answer(i18n.gettext("balance_updated", locale=message.from_user.language_code))
        else:
            await message.answer(i18n.gettext("update_failed", locale=message.from_user.language_code))
    except (ValueError, InvalidOperation) as e:
        await message.answer(i18n.gettext("invalid_input_format", locale=message.from_user.language_code))

        
@router.callback_query(lambda c: c.data == "admin_deduct_tokens", RoleFilter(roles=["admin"]))
async def start_deduction(callback: CallbackQuery, state: FSMContext, i18n: I18n):
    admin_lang = callback.from_user.language_code if callback.from_user.language_code in ['ru', 'en'] else 'ru'
    # await state.set_state(AdminStates.waiting_for_deduction) # Убираем установку состояния
    # Отправляем простое сообщение-инструкцию
    await callback.message.answer(
        i18n.gettext("Для списания токенов используйте команду: `- [ID] [Количество]`, например: `-123456789 10`", locale=admin_lang)
    )
    await callback.answer()

# Комментируем обработчик для состояния, так как кнопка его больше не устанавливает
# @router.message(StateFilter(AdminStates.waiting_for_deduction))
# async def process_deduction(message: Message, state: FSMContext, orm: ORM, i18n: I18n):
#     # ... (код обработчика остается, но он не будет вызван через кнопку) ...

@router.callback_query(lambda c: c.data == "topup_user")
async def ask_user_id_for_topup(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID пользователя и сумму через пробел (пример: 123456789 100):")
    await state.set_state(AdminStates.waiting_for_topup)

@router.message(StateFilter(AdminStates.waiting_for_topup))
async def process_topup(message: Message, orm: ORM, state: FSMContext, i18n: I18n):
    print(f"Получен ввод от пользователя: {message.text}")  

    try:
        user_id, amount = message.text.split()
        user_id, amount = int(user_id), Decimal(amount)
        print(f"🔹 Разобранный ID: {user_id}, сумма: {amount}") 

        user = await orm.user_repo.get_user(user_id)
        if not user:
            print("Пользователь не найден!") 
            await message.answer(i18n.gettext("Пользователь не найден!", locale=message.from_user.language_code))
            return

        await orm.user_repo.update_balance(user_id, amount)
        print(f"Баланс обновлен!")

        await message.answer(i18n.gettext(f"Баланс пользователя {user_id} пополнен на {amount}₸", locale=message.from_user.language_code))

    except ValueError:
        print("Ошибка парсинга данных!")  
        await message.answer(i18n.gettext("Ошибка! Введите корректные данные (пример: 123456789 100)", locale=message.from_user.language_code))
    finally:
        await state.clear()

@router.callback_query(lambda c: c.data == "admin_topup", RoleFilter(roles=["admin"]))
async def start_topup(callback: CallbackQuery, state: FSMContext, i18n: I18n):
    await callback.message.answer(i18n.gettext("Выберите действие:", locale=callback.from_user.language_code),
                                 reply_markup=Keyboards.admin_topup())
    await state.set_state(TokenTopUpStates.waiting_for_action)

@router.callback_query(F.data == "add_tokens", RoleFilter(roles=["admin"]))
async def ask_user_id_for_token_topup(callback: CallbackQuery, state: FSMContext, i18n: I18n):
    """Запрашивает ID пользователя и количество токенов для начисления."""
    try:
        await state.set_state(TokenTopUpStates.waiting_for_user_id_amount)
        await callback.message.answer(
            i18n.gettext("Введите ID пользователя и количество токенов через пробел (например, 123456789 10):", locale=callback.from_user.language_code)
        )
        await callback.answer() # Отвечаем на колбэк, чтобы убрать часики
    except Exception as e:
        logger.error(f"Error in ask_user_id_for_token_topup: {e}", exc_info=True)
        await callback.message.answer(i18n.gettext("server_error", locale=callback.from_user.language_code))

@router.message(TokenTopUpStates.waiting_for_user_id_amount, F.text, RoleFilter(roles=["admin"]))
async def process_token_topup(message: Message, state: FSMContext, orm: ORM, i18n: I18n):
    """Обрабатывает ввод ID/количества и начисляет токены."""
    try:
        user_id_str, amount_str = message.text.strip().split()
        target_user_id = int(user_id_str)
        tokens_to_add = int(amount_str)

        if tokens_to_add <= 0:
            await message.answer(i18n.gettext("Количество токенов должно быть положительным.", locale=message.from_user.language_code))
            return

        # Проверяем, существует ли пользователь
        target_user = await orm.user_repo.find_user_by_user_id(target_user_id)
        if not target_user:
            await message.answer(i18n.gettext("Пользователь с ID {} не найден.", locale=message.from_user.language_code).format(target_user_id))
            await state.clear()
            return

        # Начисляем токены
        success = await orm.user_repo.add_tokens(user_id=target_user_id, tokens_to_add=tokens_to_add, admin_id=message.from_user.id)
        
        if success:
            new_token_balance = await orm.user_repo.get_token_balance(target_user_id)
            # Сообщение администратору
            await message.answer(i18n.gettext("✅ Успешно добавлено {} токенов пользователю {}. Новый баланс: {} токенов.", locale=message.from_user.language_code).format(tokens_to_add, target_user_id, new_token_balance))
            # --- ДОБАВЛЕНО: Уведомление пользователю --- 
            try:
                user_locale = target_user.lang or 'en' # Используем язык пользователя или 'en' по умолчанию
                await message.bot.send_message(
                    chat_id=target_user_id,
                    text=i18n.gettext("🎉 Вам начислено {} токенов! Ваш новый баланс: {} токенов.", locale=user_locale).format(tokens_to_add, new_token_balance)
                )
                logging.info(f"Отправлено уведомление о пополнении {tokens_to_add} токенов пользователю {target_user_id}.")
            except Exception as notify_err:
                logging.error(f"Не удалось отправить уведомление о пополнении пользователю {target_user_id}: {notify_err}")
            # --- КОНЕЦ ДОБАВЛЕННОГО --- 
        else:
            # Ошибка могла произойти внутри add_tokens (например, пользователь не найден, хотя мы проверили)
            await message.answer(i18n.gettext("Не удалось добавить токены. Проверьте логи.", locale=message.from_user.language_code))
        
    except ValueError:
        await message.answer(i18n.gettext("Неверный формат. Введите ID пользователя и количество токенов через пробел (например, 123456789 10).", locale=message.from_user.language_code))
    except Exception as e:
        logger.error(f"Error processing token topup: {e}", exc_info=True)
        await message.answer(i18n.gettext("Произошла ошибка при начислении токенов.", locale=message.from_user.language_code))
    finally:
        await state.clear()

@router.callback_query(F.data == "set_pricing", RoleFilter(roles=["admin"])) # Добавил фильтр роли
async def set_pricing(callback: CallbackQuery, state: FSMContext, i18n: I18n): # Добавил i18n
    # Эта функция, вероятно, относится к старой логике цен за анализ
    await callback.message.answer(i18n.gettext("Эта функция (set_pricing) больше не используется.", locale=callback.from_user.language_code))
    # await state.set_state(BalanceStates.waiting_for_pricing)
    await callback.answer()

class BalanceService:
    @staticmethod
    async def validate_input(text: str, i18n: I18n) -> tuple[int, Decimal]:
        parts = text.strip().split()
        if len(parts) != 2:
            raise InvalidAmountError(i18n.gettext("invalid_input_format"))

        user_id_str, amount_str = parts
        
        try:
            user_id = int(user_id_str)
            amount = Decimal(amount_str)
        except (ValueError, InvalidOperation):
            raise InvalidAmountError(i18n.gettext("invalid_amount_format"))

        if amount <= Decimal('0'):
            raise InvalidAmountError(i18n.gettext("amount_positive_required"))

        return user_id, amount

@router.message(F.text.startswith('-'), RoleFilter(roles=["admin"]))
async def admin_deduct_tokens_command(message: Message, orm: ORM, i18n: I18n):
    """Обрабатывает команду списания токенов вида '- [id] [количество]'."""
    admin_lang = message.from_user.language_code if message.from_user.language_code in ['ru', 'en'] else 'ru' # Используем язык админа
    try:
        # Убираем '-', лишние пробелы в начале/конце и разделяем
        command_parts = message.text[1:].strip().split()
        if len(command_parts) != 2:
            await message.answer(i18n.gettext("❌ Invalid format. Use: - [User ID] [Number of Tokens]", locale=admin_lang))
            return

        user_id_str, amount_str = command_parts
        target_user_id = int(user_id_str) # ID не должен содержать '-'
        tokens_to_deduct = int(amount_str)

        if tokens_to_deduct <= 0:
            await message.answer(i18n.gettext("The number of tokens to deduct must be positive.", locale=admin_lang))
            return

        user_db = await orm.user_repo.find_user_by_user_id(target_user_id)
        if not user_db:
            await message.answer(i18n.gettext("User with ID {user_id} not found.", locale=admin_lang).format(user_id=target_user_id))
            return
            
        current_token_balance = await orm.user_repo.get_token_balance(target_user_id)
        if current_token_balance < tokens_to_deduct:
             await message.answer(i18n.gettext("User {user_id} does not have enough tokens to deduct ({current_balance} < {deduct_amount}).", locale=admin_lang).format(
                  user_id=target_user_id, current_balance=current_token_balance, deduct_amount=tokens_to_deduct
             ))
             return
        
        # Проверяем, есть ли метод deduct_tokens
        if not hasattr(orm.user_repo, 'deduct_tokens'):
             logger.error("Метод UserRepo.deduct_tokens не реализован!")
             await message.answer(i18n.gettext("Error: Token deduction function is not configured on the server.", locale=admin_lang))
             return
             
        success = await orm.user_repo.deduct_tokens(user_id=target_user_id, tokens_to_deduct=tokens_to_deduct, admin_id=message.from_user.id)

        if success:
            new_token_balance = await orm.user_repo.get_token_balance(target_user_id)
            await message.answer(i18n.gettext("✅ {tokens} tokens deducted from user {user_id}. New balance: {new_balance} tokens.", locale=admin_lang).format(
                user_id=target_user_id, tokens=tokens_to_deduct, new_balance=new_token_balance
            ))
        else:
            await message.answer(i18n.gettext("⚠️ An error occurred while deducting tokens.", locale=admin_lang))

    except ValueError:
        # Эта ошибка теперь будет ловиться если user_id_str или amount_str не являются числами
        await message.answer(i18n.gettext("❌ Format error. User ID and token amount must be numbers.", locale=admin_lang))
    except Exception as e:
        logger.error(f"Ошибка при списании токенов через команду: {e}", exc_info=True)
        await message.answer(i18n.gettext("⚠️ A system error occurred while deducting tokens.", locale=admin_lang))

# --- ОБНОВЛЕННЫЙ БЛОК: Массовое начисление токенов ---

# 1. Нажатие кнопки "Начислить токены всем"
@router.callback_query(F.data == "mass_token_topup", RoleFilter(roles=["admin"]))
async def ask_mass_token_language(callback: CallbackQuery, state: FSMContext, i18n: I18n):
    admin_lang = callback.from_user.language_code
    await callback.message.edit_text(
        i18n.gettext("Выберите язык пользователей для начисления токенов:", locale=admin_lang),
        reply_markup=Keyboards.mass_token_lang_options(i18n)
    )
    await state.set_state(AdminStates.waiting_for_mass_token_language)
    await callback.answer()

# 2. Получение языка от админа
@router.callback_query(MassTokenLangCallback.filter(F.action == 'select'), AdminStates.waiting_for_mass_token_language, RoleFilter(roles=["admin"]))
async def ask_mass_token_amount(callback: CallbackQuery, callback_data: MassTokenLangCallback, state: FSMContext, i18n: I18n):
    selected_lang = callback_data.lang
    await state.update_data(mass_token_selected_language=selected_lang)
    admin_lang = callback.from_user.language_code

    lang_name_map = {"ru": "русского", "en": "английского"}
    target_lang_readable = lang_name_map.get(selected_lang, selected_lang)

    await callback.message.edit_text(
        i18n.gettext("Введите количество токенов для начисления КАЖДОМУ пользователю с {lang} языком:", locale=admin_lang).format(lang=target_lang_readable)
    )
    await state.set_state(AdminStates.waiting_for_mass_token_amount)
    await callback.answer()

# 3. Получение количества токенов от админа
@router.message(AdminStates.waiting_for_mass_token_amount, F.text, RoleFilter(roles=["admin"]))
async def ask_mass_token_confirmation(message: Message, state: FSMContext, i18n: I18n, orm: ORM):
    admin_lang = message.from_user.language_code
    try:
        token_amount = int(message.text.strip())
        if token_amount <= 0:
            await message.answer(i18n.gettext("Количество токенов должно быть положительным числом.", locale=admin_lang))
            return

        data = await state.get_data()
        selected_lang = data.get("mass_token_selected_language")
        if not selected_lang:
            await message.answer(i18n.gettext("Ошибка: язык не выбран. Начните заново.", locale=admin_lang))
            await state.clear()
            return

        # Получаем количество пользователей для выбранного языка
        users_for_lang = await orm.user_repo.get_users_by_language(selected_lang)
        count_users_for_lang = len(users_for_lang)

        await state.update_data(mass_token_amount=token_amount, count_users_for_lang=count_users_for_lang)
        
        lang_name_map = {"ru": "русского", "en": "английского"}
        target_lang_readable = lang_name_map.get(selected_lang, selected_lang)

        confirm_text = i18n.gettext(
            "Вы уверены, что хотите начислить {amount} токенов каждому из {count} пользователей с {lang} языком?\nЭто действие НЕОБРАТИМО.",
            locale=admin_lang
        ).format(amount=token_amount, count=count_users_for_lang, lang=target_lang_readable)

        await message.answer(confirm_text, reply_markup=Keyboards.confirm_mass_token_topup(i18n, admin_lang))
        await state.set_state(AdminStates.waiting_for_mass_token_confirmation)

    except ValueError:
        await message.answer(i18n.gettext("Пожалуйста, введите корректное целое число.", locale=admin_lang))
    except Exception as e:
        logging.error(f"Ошибка при запросе подтверждения массового начисления: {e}", exc_info=True)
        await message.answer(i18n.gettext("Произошла ошибка. Попробуйте снова.", locale=admin_lang))
        await state.clear()

# 4. Обработка подтверждения или отмены
@router.callback_query(AdminStates.waiting_for_mass_token_confirmation, RoleFilter(roles=["admin"]))
async def process_mass_token_topup(callback: CallbackQuery, state: FSMContext, i18n: I18n, orm: ORM, env: Environ):
    await callback.message.edit_reply_markup(reply_markup=None) # Убираем кнопки
    admin_lang = callback.from_user.language_code

    if callback.data == "confirm_mass_token_topup":
        data = await state.get_data()
        token_amount = data.get("mass_token_amount")
        selected_lang = data.get("mass_token_selected_language")
        # count_users_for_lang = data.get("count_users_for_lang") # Уже есть в data, но будем получать список ID

        if not token_amount or not isinstance(token_amount, int) or token_amount <= 0 or not selected_lang:
            await callback.message.answer(i18n.gettext("Ошибка: Неверные данные для начисления. Начните заново.", locale=admin_lang))
            await state.clear()
            await callback.answer()
            return
        
        lang_name_map = {"ru": "русского", "en": "английского"}
        target_lang_readable = lang_name_map.get(selected_lang, selected_lang)

        await callback.message.answer(i18n.gettext("Начинаю начисление {amount} токенов пользователям с {lang} языком... Это может занять некоторое время.", locale=admin_lang).format(amount=token_amount, lang=target_lang_readable))
        await callback.answer()

        success_count = 0
        fail_count = 0
        processed_users = 0

        try:
            users_to_topup = await orm.user_repo.get_users_by_language(selected_lang)
            if users_to_topup is None: # get_users_by_language вернет [], а не None, но проверим
                users_to_topup = []
            
            actual_user_count = len(users_to_topup)
            logging.info(f"Массовое начисление: язык={selected_lang}, токенов={token_amount}, найдено пользователей={actual_user_count}")

            admin_id = callback.from_user.id

            for user_obj in users_to_topup:
                try:
                    # Уведомление теперь будет отправляться отсюда, а не из репозитория
                    added = await orm.user_repo.add_tokens(user_obj.user_id, token_amount, admin_id, notify_user=False)
                    if added:
                        success_count += 1
                        try:
                            # Уведомление пользователю о начислении
                            user_notify_lang = user_obj.lang # Язык конкретного пользователя
                            notify_text = i18n.gettext("🎉 Вам было начислено {amount} токенов администратором!", locale=user_notify_lang).format(amount=token_amount)
                            await callback.bot.send_message(user_obj.user_id, notify_text)
                        except Exception as notify_err:
                            logging.warning(f"Не удалось уведомить пользователя {user_obj.user_id} о массовом начислении: {notify_err}")
                    else:
                        fail_count += 1
                        logging.warning(f"Не удалось начислить токены пользователю {user_obj.user_id} (add_tokens вернул False) для языка {selected_lang}")
                except Exception as user_err:
                    fail_count += 1
                    logging.error(f"Ошибка при начислении токенов пользователю {user_obj.user_id} (язык {selected_lang}): {user_err}", exc_info=False)
                
                processed_users += 1
                if processed_users % 30 == 0: # Задержка каждые 30 пользователей
                     await asyncio.sleep(1)

            result_text = i18n.gettext(
                "Массовое начисление {amount} токенов для пользователей с {lang} языком завершено.\nУспешно начислено: {success}\nНе удалось начислить: {fail}",
                locale=admin_lang
            ).format(amount=token_amount, lang=target_lang_readable, success=success_count, fail=fail_count)
            
            # Отправка отчета всем администраторам и в канал
            admins = await orm.user_repo.get_admins()
            for admin in admins:
                try:
                    await callback.bot.send_message(admin.user_id, result_text)
                except Exception as e:
                    logger.error(f"Не удалось отправить отчет о начислении токенов администратору {admin.user_id}: {e}")
            
            if env.channel_id:
                try:
                    await callback.bot.send_message(env.channel_id, result_text)
                except Exception as e:
                    logger.error(f"Не удалось отправить отчет о начислении токенов в канал {env.channel_id}: {e}")

        except Exception as e:
            logging.error(f"Критическая ошибка во время массового начисления токенов (язык {selected_lang}): {e}", exc_info=True)
            error_text = i18n.gettext("Произошла критическая ошибка во время начисления ({lang}). Часть токенов могла быть не начислена. Проверьте логи.", locale=admin_lang).format(lang=target_lang_readable)
            await callback.message.answer(error_text)

    elif callback.data == "cancel_mass_token_topup":
        await callback.message.edit_text(i18n.gettext("Массовое начисление токенов отменено.", locale=admin_lang))
        await callback.answer()
    else:
        await callback.answer(i18n.gettext("Неизвестное действие.", locale=admin_lang))

    await state.clear()

# --- КОНЕЦ ОБНОВЛЕННОГО БЛОКА ---

@router.callback_query(AdminCallback.filter(F.action == "reply_to_user"))
async def start_reply_to_user(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext, i18n: I18n):
    """
    Начинает процесс ответа пользователю от имени администратора.
    """
    await state.update_data(reply_to_user_id=callback_data.user_id)
    await state.set_state(AdminStates.waiting_for_reply)
    
    # Удаляем клавиатуру у исходного сообщения и просим ввести ответ
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(i18n.gettext("Введите ваше сообщение для пользователя:", locale='ru'))
    await callback.answer()


@router.message(AdminStates.waiting_for_reply, F.text)
async def send_reply_to_user(message: Message, state: FSMContext, orm: ORM, bot, i18n: I18n):
    """
    Отправляет сообщение от администратора пользователю.
    """
    data = await state.get_data()
    target_user_id = data.get('reply_to_user_id')

    if not target_user_id:
        await message.answer(i18n.gettext("Ошибка: ID пользователя для ответа не найден. Начните заново.", locale='ru'))
        await state.clear()
        return

    target_user = await orm.user_repo.find_user_by_user_id(target_user_id)
    if not target_user:
        await message.answer(i18n.gettext("Ошибка: Не удалось найти пользователя для ответа в базе данных.", locale='ru'))
        await state.clear()
        return
        
    user_lang = target_user.lang if target_user.lang in i18n.available_locales else 'ru'

    try:
        # Формируем текст с префиксом, переведенным на язык пользователя
        reply_text = i18n.gettext("Сообщение от администратора:", locale=user_lang) + f"\n\n{message.text}"
        
        await bot.send_message(
            chat_id=target_user_id,
            text=reply_text
        )
        await message.answer(i18n.gettext("Сообщение успешно отправлено.", locale='ru'))
    except Exception as e:
        logger.error(f"Не удалось отправить ответ пользователю {target_user_id}: {e}")
        await message.answer(i18n.gettext("Не удалось отправить сообщение. Проверьте логи.", locale='ru'))
    finally:
        await state.clear()

# --- User Search ---

async def format_user_list_message(users: list[User], i18n: I18n) -> str:
    """Formats the list of users into a readable string."""
    if not users:
        return i18n.gettext("Нет зарегистрированных пользователей.")
    
    user_lines = []
    for user in users:
        user_info = (
            f"👤 <b>{user.fullname or 'N/A'}</b> (<code>{user.user_id}</code>)\n"
            f"   - Ник: @{user.username or 'N/A'}\n"
            f"   - Роль: {user.role}, Язык: {user.lang}\n"
            f"   - Баланс: {user.token_balance} 🪙"
        )
        user_lines.append(user_info)
    
    return "\n\n".join(user_lines)


@router.callback_query(F.data == "users_list")
async def get_users_list(callback: CallbackQuery, orm: ORM, i18n: I18n, user: User):
    """Handles the 'List of Users' button click, showing the first page."""
    users, total_pages = await orm.user_repo.get_paged_users(page=0)
    
    if total_pages == 0:
        await callback.message.answer(i18n.gettext("Нет зарегистрированных пользователей."))
        await callback.answer()
        return

    message_text = await format_user_list_message(users, i18n)
    reply_markup = Keyboards.get_users_list_keyboard(total_pages, 0, i18n, user)
    
    await callback.message.answer(text=message_text, reply_markup=reply_markup)
    await callback.answer()


@router.callback_query(UserListPagination.filter())
async def paginate_users_list(callback: CallbackQuery, callback_data: UserListPagination, orm: ORM, i18n: I18n, user: User):
    """Handles pagination for the user list."""
    new_page = callback_data.page
    users, total_pages = await orm.user_repo.get_paged_users(page=new_page)
    
    message_text = await format_user_list_message(users, i18n)
    
    await callback.message.edit_text(text=message_text)
    await callback.message.edit_reply_markup(reply_markup=Keyboards.get_users_list_keyboard(total_pages, new_page, i18n, user))
    await callback.answer()

# --- Back to Admin Panel ---

@router.callback_query(F.data == "back_to_admin_panel")
async def back_to_admin_panel_handler(callback: CallbackQuery, i18n: I18n, user: User):
    await callback.message.edit_text(
        i18n.gettext("Admin panel"),
        reply_markup=Keyboards.admin_panel(i18n, user)
    )
    await callback.answer()