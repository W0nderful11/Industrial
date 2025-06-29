import logging
from decimal import Decimal, InvalidOperation
from math import floor

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.telegram.filters.role import RoleFilter
# Импортируем keyboards позже, когда добавим кнопки
# from services.telegram.misc.keyboards import Keyboards 

logger = logging.getLogger(__name__)

admin_topup_router = Router()
admin_topup_router.message.filter(RoleFilter(roles=["admin"]))
admin_topup_router.callback_query.filter(RoleFilter(roles=["admin"]))

BASE_PRICE_USD = Decimal("1.0") # Базовая цена 1 токена в USD

class AdminTopUpStates(StatesGroup):
    waiting_for_user_identifier = State()
    waiting_for_topup_type = State()
    waiting_for_currency_amount = State()
    waiting_for_token_amount = State()

# --- Command Handler --- 
@admin_topup_router.message(Command("topup_user"))
async def start_admin_topup(message: Message, state: FSMContext, i18n: I18n):
    logger.info(f"Admin {message.from_user.id} initiated top-up process.")
    await state.clear() # Очищаем предыдущее состояние на всякий случай
    await message.answer(i18n.gettext("Введите ID или @username пользователя, которому хотите пополнить баланс:", locale='ru')) # Используем ru для админа
    await state.set_state(AdminTopUpStates.waiting_for_user_identifier)

# --- State Handlers --- 
@admin_topup_router.message(AdminTopUpStates.waiting_for_user_identifier)
async def process_user_identifier(message: Message, state: FSMContext, orm: ORM, i18n: I18n):
    identifier = message.text.strip()
    logger.info(f"Admin {message.from_user.id} entered identifier: {identifier}")
    target_user = None
    
    # TODO: Implement orm.user_repo.find_user_by_username_or_id(identifier)
    # Пока заглушка:
    # try:
    #     target_user = await orm.user_repo.find_user_by_username_or_id(identifier)
    # except Exception as e:
    #     logger.error(f"Error finding user by identifier '{identifier}': {e}", exc_info=True)
    #     await message.answer(i18n.gettext("Ошибка при поиске пользователя в базе данных.", locale='ru'))
    #     return
    
    # --- ЗАГЛУШКА - УДАЛИТЬ ПОСЛЕ РЕАЛИЗАЦИИ РЕПО --- 
    if identifier.isdigit():
         target_user = await orm.user_repo.find_user_by_user_id(int(identifier))
    elif identifier.startswith('@'):
         target_user = await orm.user_repo.find_user_by_username(identifier[1:])
    else:
         target_user = await orm.user_repo.find_user_by_username(identifier) 
    # --- КОНЕЦ ЗАГЛУШКИ --- 

    if not target_user:
        logger.warning(f"User with identifier '{identifier}' not found by admin {message.from_user.id}.")
        await message.answer(i18n.gettext("Пользователь с ID/именем '{id}' не найден. Попробуйте снова.", locale='ru').format(id=identifier))
        await state.set_state(AdminTopUpStates.waiting_for_user_identifier) # Остаемся в том же состоянии
        return

    logger.info(f"Target user found: ID={target_user.user_id}, Username={target_user.username}")
    await state.update_data(target_user_id=target_user.user_id, target_username=target_user.username, target_user_lang=target_user.lang, target_user_country=target_user.country)

    # Создаем кнопки выбора типа пополнения
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Валютой", callback_data="topup_currency")],
        [InlineKeyboardButton(text="Токены", callback_data="topup_tokens")]
    ])

    await message.answer(
        i18n.gettext("Пользователь @{username} (ID: {user_id}) найден. Выберите тип пополнения:", locale='ru').format(
            username=target_user.username or "(нет username)", user_id=target_user.user_id
        ),
        reply_markup=keyboard
    )
    await state.set_state(AdminTopUpStates.waiting_for_topup_type)

@admin_topup_router.callback_query(AdminTopUpStates.waiting_for_topup_type)
async def process_topup_type(callback: CallbackQuery, state: FSMContext, orm: ORM, i18n: I18n):
    data = await state.get_data()
    target_username = data.get('target_username', "N/A")
    target_user_id = data.get('target_user_id')
    target_user_country = data.get('target_user_country', 'DEFAULT').upper()

    if not target_user_id:
        logger.error(f"Target user ID not found in state for callback {callback.id} from admin {callback.from_user.id}")
        await callback.message.edit_text(i18n.gettext("Произошла ошибка состояния. Пожалуйста, начните процесс пополнения заново с /topup_user.", locale='ru'))
        await state.clear()
        return
        
    if callback.data == "topup_currency":
        logger.info(f"Admin {callback.from_user.id} chose 'Currency' top-up for user {target_user_id}.")
        # Получаем региональные настройки
        region_config = await orm.regional_pricing_repo.get_pricing_by_country(target_user_country)
        if not region_config:
            logger.warning(f"Region config for {target_user_country} not found, using DEFAULT for user {target_user_id}.")
            region_config = await orm.regional_pricing_repo.get_default_pricing()
            if not region_config:
                 logger.error(f"DEFAULT region config not found! Cannot proceed with currency top-up for user {target_user_id}.")
                 await callback.message.edit_text(i18n.gettext("Ошибка: Не найдена конфигурация цен по умолчанию.", locale='ru'))
                 await state.clear()
                 return
        
        currency_code = region_config['currency']
        currency_symbol = region_config['symbol']
        # Сохраняем в состояние для расчета
        await state.update_data(currency_code=currency_code, currency_symbol=currency_symbol, coefficient=str(region_config['coefficient']), exchange_rate=str(region_config['exchange_rate']))
        
        await callback.message.edit_text(i18n.gettext(
            "Введите сумму пополнения в {currency_code} ({currency_symbol}) для пользователя @{username}:", 
            locale='ru'
        ).format(currency_code=currency_code, currency_symbol=currency_symbol, username=target_username))
        await state.set_state(AdminTopUpStates.waiting_for_currency_amount)

    elif callback.data == "topup_tokens":
        logger.info(f"Admin {callback.from_user.id} chose 'Tokens' top-up for user {target_user_id}.")
        await callback.message.edit_text(i18n.gettext("Введите количество токенов для пополнения пользователя @{username}:", locale='ru').format(username=target_username))
        await state.set_state(AdminTopUpStates.waiting_for_token_amount)
    else:
        await callback.answer("Неизвестный выбор.") # Игнорируем другие колбеки
        
    await callback.answer() # Убираем часики

@admin_topup_router.message(AdminTopUpStates.waiting_for_currency_amount)
async def process_currency_amount(message: Message, state: FSMContext, orm: ORM, i18n: I18n, bot: Bot):
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    target_username = data.get('target_username', "N/A")
    target_user_lang = data.get('target_user_lang')
    currency_code = data.get('currency_code')
    currency_symbol = data.get('currency_symbol')
    coefficient_str = data.get('coefficient')
    exchange_rate_str = data.get('exchange_rate')
    admin_id = message.from_user.id

    if not all([target_user_id, currency_code, currency_symbol, coefficient_str, exchange_rate_str]):
        logger.error(f"Missing data in state for currency amount processing for admin {admin_id}, target user {target_user_id}.")
        await message.answer(i18n.gettext("Произошла ошибка состояния (отсутствуют данные). Пожалуйста, начните процесс пополнения заново с /topup_user.", locale='ru'))
        await state.clear()
        return

    try:
        amount_decimal = Decimal(message.text.strip().replace(',', '.'))
        if amount_decimal <= 0:
            raise ValueError("Amount must be positive")
        logger.info(f"Admin {admin_id} entered amount: {amount_decimal} {currency_code} for user {target_user_id}.")
    except (InvalidOperation, ValueError):
        logger.warning(f"Invalid currency amount entered by admin {admin_id}: {message.text}")
        await message.answer(i18n.gettext("Неверный формат суммы. Пожалуйста, введите положительное число (например, 100 или 50.5):", locale='ru'))
        return

    try:
        coefficient = Decimal(coefficient_str)
        exchange_rate = Decimal(exchange_rate_str)
        
        # Расчет цены токена в локальной валюте
        price_per_token_local = BASE_PRICE_USD * coefficient * exchange_rate
        
        if price_per_token_local <= 0:
             logger.error(f"Calculated price per token is zero or negative for user {target_user_id} (coeff: {coefficient}, rate: {exchange_rate}). Aborting.")
             await message.answer(i18n.gettext("Ошибка расчета цены токена (цена не положительная). Обратитесь к разработчику.", locale='ru'))
             await state.clear()
             return
        
        # Расчет количества токенов и округление вниз
        tokens_to_add = floor(amount_decimal / price_per_token_local)
        
        logger.info(f"Calculated tokens for user {target_user_id}: {amount_decimal} {currency_code} / ({BASE_PRICE_USD}$ * {coefficient} * {exchange_rate}) = {tokens_to_add} tokens (floor)")

        if tokens_to_add <= 0:
             logger.warning(f"Calculated tokens is zero or negative for user {target_user_id} based on amount {amount_decimal} {currency_code}.")
             await message.answer(i18n.gettext("Введенной суммы недостаточно для покупки даже 1 токена.", locale='ru'))
             # Можно предложить ввести большую сумму или очистить состояние
             await state.set_state(AdminTopUpStates.waiting_for_currency_amount)
             return

        # Пополнение баланса пользователя
        # TODO: Implement orm.user_repo.add_tokens(user_id, amount, admin_id)
        # Пока заглушка:
        success = await orm.user_repo.add_tokens(user_id=target_user_id, amount=tokens_to_add, admin_id=admin_id)
        # --- КОНЕЦ ЗАГЛУШКИ --- 
        
        if success:
            logger.info(f"Successfully added {tokens_to_add} tokens to user {target_user_id} by admin {admin_id}.")
            # Уведомление админу
            await message.answer(i18n.gettext(
                "✅ Успешно пополнено {tokens} токенов для пользователя @{username} (ID: {user_id}).", 
                locale='ru'
                ).format(tokens=tokens_to_add, username=target_username, user_id=target_user_id))
            
            # Уведомление пользователю
            try:
                await bot.send_message(target_user_id, i18n.gettext(
                    "🎉 Ваш баланс пополнен администратором на {tokens} токенов!", 
                    locale=target_user_lang
                    ).format(tokens=tokens_to_add))
            except Exception as e:
                 logger.error(f"Failed to send top-up notification to user {target_user_id}: {e}")
            
            await state.clear()
        else:
            logger.error(f"Failed to add tokens to user {target_user_id} in DB by admin {admin_id}.")
            await message.answer(i18n.gettext("Не удалось обновить баланс пользователя в базе данных.", locale='ru'))
            await state.clear()
            
    except Exception as e:
        logger.error(f"Error during currency top-up calculation or DB update for admin {admin_id}, target user {target_user_id}: {e}", exc_info=True)
        await message.answer(i18n.gettext("Произошла внутренняя ошибка при расчете или пополнении токенов.", locale='ru'))
        await state.clear()

@admin_topup_router.message(AdminTopUpStates.waiting_for_token_amount)
async def process_token_amount(message: Message, state: FSMContext, orm: ORM, i18n: I18n, bot: Bot):
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    target_username = data.get('target_username', "N/A")
    target_user_lang = data.get('target_user_lang')
    admin_id = message.from_user.id
    
    if not target_user_id:
        logger.error(f"Missing target_user_id in state for token amount processing for admin {admin_id}.")
        await message.answer(i18n.gettext("Произошла ошибка состояния. Пожалуйста, начните процесс пополнения заново с /topup_user.", locale='ru'))
        await state.clear()
        return

    try:
        tokens_to_add = int(message.text.strip())
        if tokens_to_add <= 0:
            raise ValueError("Token amount must be positive")
        logger.info(f"Admin {admin_id} entered token amount: {tokens_to_add} for user {target_user_id}.")
    except ValueError:
        logger.warning(f"Invalid token amount entered by admin {admin_id}: {message.text}")
        await message.answer(i18n.gettext("Неверный формат количества. Пожалуйста, введите положительное целое число (например, 10):", locale='ru'))
        return

    # Пополнение баланса пользователя
    # TODO: Implement orm.user_repo.add_tokens(user_id, amount, admin_id)
    # Пока заглушка:
    success = await orm.user_repo.add_tokens(user_id=target_user_id, amount=tokens_to_add, admin_id=admin_id)
    # --- КОНЕЦ ЗАГЛУШКИ --- 

    if success:
        logger.info(f"Successfully added {tokens_to_add} tokens to user {target_user_id} by admin {admin_id}.")
        # Уведомление админу
        await message.answer(i18n.gettext(
            "✅ Успешно пополнено {tokens} токенов для пользователя @{username} (ID: {user_id}).", 
            locale='ru'
            ).format(tokens=tokens_to_add, username=target_username, user_id=target_user_id))
        
        # Уведомление пользователю
        try:
            await bot.send_message(target_user_id, i18n.gettext(
                "🎉 Ваш баланс пополнен администратором на {tokens} токенов!", 
                locale=target_user_lang
                ).format(tokens=tokens_to_add))
        except Exception as e:
             logger.error(f"Failed to send top-up notification to user {target_user_id}: {e}")
        
        await state.clear()
    else:
        logger.error(f"Failed to add tokens to user {target_user_id} in DB by admin {admin_id}.")
        await message.answer(i18n.gettext("Не удалось обновить баланс пользователя в базе данных.", locale='ru'))
        await state.clear() 