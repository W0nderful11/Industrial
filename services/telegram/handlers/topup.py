import logging
import json
import asyncio # Добавлен импорт asyncio
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.i18n import I18n
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from decimal import Decimal # Добавлен импорт Decimal

from database.database import ORM
from database.models import User
# from services.telegram.handlers.states import TopUpStates # TODO: Создать этот класс состояний

logger = logging.getLogger(__name__)
router = Router()

# --- Обработчик получения геолокации ---
# ИЗМЕНЕНО: Убрано состояние F.location и TopUpStates, т.к. геолокация больше не запрашивается.
#          Обработчик теперь вызывается другим способом (например, по кнопке "Узнать цену")
# @router.message(F.location, TopUpStates.waiting_for_location) 
# ^^^ Закомментировано

# TODO: Переделать триггер для этого обработчика. Пока оставляем его без явного триггера.
# async def handle_location(message: Message, state: FSMContext, i18n: I18n, user, orm: ORM):
async def show_regional_price(message: Message, state: FSMContext, i18n: I18n, user: User, orm: ORM):
    # await state.clear() # Состояние больше не используется здесь
    # ИЗМЕНЕНО: Получаем страну из профиля пользователя
    user_country_code = user.country 
    logger.info(f"Используем страну из профиля пользователя {message.from_user.id if message.from_user else 'Unknown'}: {user_country_code}")
    
    # --- Убран блок try/except для Geopy --- 

    # Получаем цены из БД, используя страну пользователя
    region_config = None
    country_code_for_price = None # Переменная для хранения кода, по которому нашлась цена
    
    if user_country_code:
        user_country_code = user_country_code.upper() # Приводим к верхнему регистру
        region_config = await orm.regional_pricing_repo.get_pricing_by_country(user_country_code)
        if region_config:
             country_code_for_price = user_country_code
        else:
             logger.warning(f"Конфигурация цен для страны пользователя {user_country_code} не найдена.")
    
    if not region_config: # Если страна не указана в профиле или для нее нет конфига
        logger.info(f"Используется дефолтная конфигурация цен.")
        region_config = await orm.regional_pricing_repo.get_default_pricing()
        country_code_for_price = "DEFAULT"

    if not region_config: # Крайний случай, если даже дефолт не найден
        logger.error("Не найдена конфигурация цен, включая дефолтную!")
        await message.answer(i18n.gettext("Не удалось получить информацию о ценах. Обратитесь к администратору.", locale=user.lang), reply_markup=types.ReplyKeyboardRemove())
        return

    logger.info(f"Используется конфигурация цен для региона: {country_code_for_price} - {region_config}")

    # --- Расчет цены --- 
    # Убрана заглушка usd_to_local
    
    # Используем Decimal для точности
    base_price_usd = Decimal("1.0") # Базовая цена 1 токена в USD
    currency = region_config["currency"]
    symbol = region_config["symbol"]
    coefficient = Decimal(str(region_config["coefficient"])) # Преобразуем в Decimal, безопасно через str
    exchange_rate = Decimal(str(region_config["exchange_rate"])) # Преобразуем в Decimal, безопасно через str

    # Расчет и округление до целого
    final_price = int(round(base_price_usd * coefficient * exchange_rate))

    # Формируем новое сообщение с подтверждением и ценой
    # ИЗМЕНЕНО: Уточнено, что регион взят из профиля
    price_message = i18n.gettext(
        "✅ Регион определён по вашему профилю: {region}\n\nСтоимость пополнения для вашего региона:\n<b>1 токен = {price} {symbol}</b>",
        locale=user.lang
    ).format(region=country_code_for_price, price=final_price, symbol=symbol)

    # TODO: Добавить кнопки для выбора количества токенов и перехода к оплате
    # Отправляем сообщение и удаляем клавиатуру запроса локации (если она была)
    await message.answer(price_message, reply_markup=types.ReplyKeyboardRemove()) 