from aiogram import Router, F, Bot
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import cast
from aiogram.utils.i18n import I18n
from decimal import Decimal, InvalidOperation
import math
import html

from database.database import ORM
from database.models import User
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import LangCallback, ResistorCalculatorCallback, ResistorCalculatorTypeCallback, ResistorCallback
from services.telegram.misc.keyboards import Keyboards
from services.analyzer.nand import NandList # Для find_command

# Импорт логгера и CHANNEL_URL из __init__.py текущего пакета
from . import logger, CHANNEL_URL

router = Router()
# Применяем фильтры ко всем хэндлерам в этом роутере, как было в оригинальном home.py
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


# Состояния для прямого ввода значений из меню калькулятора
class MenuResistorState(StatesGroup):
    waiting_for_smd_code = State()
    waiting_for_smd_value = State()
    waiting_for_resistance_value = State()
    waiting_for_multiplier_selection = State()
    waiting_for_tolerance_selection = State()


@router.message(F.text == "Главная")
@router.message(Command("start"))
async def home(message: Message, user: User, i18n: I18n):
    reply_markup = Keyboards.home(i18n, user)

    greeting_message = i18n.gettext(
        "Приветствую @{}🙂🤝🏼"
        "\nЯ помогу тебе с анализом сбоев"
        "\nОтправь мне файл и я его проанализирую 🔬",
        locale=user.lang
    ).format(user.username)

    await message.answer(
        greeting_message,
        reply_markup=reply_markup
    )


@router.message(Command("balance"))
async def show_user_balance(message: Message, orm: ORM, i18n: I18n, user: User):
    if not message.from_user:
        return
    
    if not orm or not orm.user_repo:
        await message.answer(
            "❌ Сервис временно недоступен. Попробуйте позже.",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    token_balance = await orm.user_repo.get_token_balance(message.from_user.id)
    await message.answer(
        i18n.gettext("💰 Ваш текущий баланс: {} токенов.", locale=user.lang).format(token_balance),
        reply_markup=Keyboards.back_to_home(i18n, user),
        reply_to_message_id=message.message_id,
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(F.text == "Пополнить баланс 💳")
@router.message(F.text == "Top Up Balance 💳")
async def request_topup_balance(message: Message, orm: ORM, i18n: I18n, user: User):
    price_info = "1 токен = 1$\n"
    user_country_code_raw = user.country
    user_country_code_upper = user_country_code_raw.upper() if user_country_code_raw else None
    base_usd_price = Decimal("1.0")

    if user_country_code_upper and hasattr(orm, 'regional_pricing_repo') and orm.regional_pricing_repo:
        regional_data = await orm.regional_pricing_repo.get_pricing_by_country(user_country_code_upper)
        if regional_data:
            try:
                coeff = Decimal(str(regional_data['coefficient']))
                rate = Decimal(str(regional_data['exchange_rate']))
                symbol = regional_data['symbol']
                raw_price = base_usd_price * coeff * rate
                price = math.ceil(raw_price / 10) * 10
                price_info = f"1 токен = {price} {symbol}\n"
            except (KeyError, TypeError, ValueError, InvalidOperation) as e:
                logger.error(
                    f"Ошибка при расчете региональной цены для {user_country_code_upper}: {e}. Используется цена по умолчанию.")
                price_info = "1 токен = 1$\n"

    admin_contact = "@masterkazakhstan"
    topup_request_message = i18n.gettext(
        "Для пополнения баланса свяжитесь с администратором:\n{admin_contact}",
        locale=user.lang
    ).format(admin_contact=admin_contact)

    await message.answer(
        topup_request_message,
        reply_markup=Keyboards.back_to_home(i18n, user),
        reply_to_message_id=message.message_id,
        parse_mode=ParseMode.MARKDOWN
    )

    channel_tokens_target_id = None
    if hasattr(message.bot, 'environment') and message.bot:
        bot_env = getattr(message.bot, 'environment', None)
        if bot_env:
            # logger.info(f"Bot has environment object: {bool(bot_env)}") # Removed for brevity
            if hasattr(bot_env, 'channel_tokens_id'):
                # logger.info(f"Environment has channel_tokens_id attribute: {bot_env.channel_tokens_id}") # Removed
                try:
                    channel_tokens_target_id = int(bot_env.channel_tokens_id)
                    logger.info(f"Успешно получен channel_tokens_id: {channel_tokens_target_id}")
                except (ValueError, TypeError) as e_parse_id:
                    logger.error(
                        f"Не удалось преобразовать channel_tokens_id '{bot_env.channel_tokens_id}' в int: {e_parse_id}")
            else:
                logger.error("Атрибут channel_tokens_id отсутствует в environment")
        else:
            logger.error("Объект environment в боте пустой или None")
    else:
        logger.error("Объект bot не имеет атрибута environment")

    if not message.from_user:
        return
    
    full_name = html.escape(message.from_user.full_name or '')
    username = message.from_user.username

    user_details_parts = []
    if full_name:
        user_details_parts.append(full_name)
    if username:
        user_details_parts.append(f"@{username}")

    user_details = " ".join(user_details_parts)
    if not user_details:
        user_details = "Пользователь"

    admin_notification_text = i18n.gettext(
        "Пользователь {user_details} ({user_id}) запросил пополнение баланса.",
        locale="ru"
    ).format(user_details=user_details, user_id=user.user_id)

    admin_instructions = (
        f"\n*Инструкции для админа:*\n"
        f"чтоб списать: `-{(user.user_id)} 10`\n"
        f"чтоб пополнить: `+{(user.user_id)} 10`"
    )
    admin_notification_text += admin_instructions

    if channel_tokens_target_id and message.bot:
        try:
            await message.bot.send_message(
                channel_tokens_target_id,
                admin_notification_text,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Отправлено уведомление о пополнении баланса в канал {channel_tokens_target_id}")
            return
        except Exception as channel_err:
            logger.error(
                f"Не удалось отправить уведомление о пополнении в канал {channel_tokens_target_id}: {channel_err}")
    else:
        logger.error("CHANNEL_TOKENS_ID не настроен или некорректен в конфигурации. Использую резервный механизм.")

    if not message.bot:
        logger.error("Bot object is None, cannot send admin notifications")
        return

    if orm and orm.user_repo:
        try:
            admins = await orm.user_repo.get_admins()
            if admins:
                logger.info(f"Найдено {len(admins)} админов для резервной отправки: {[a.user_id for a in admins]}")
                for admin in admins:
                    try:
                        await message.bot.send_message(
                            admin.user_id,
                            admin_notification_text,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        logger.info(f"Отправлено прямое уведомление о пополнении баланса админу {admin.user_id}")
                    except Exception as admin_err:
                        logger.error(f"Не удалось отправить уведомление о пополнении админу {admin.user_id}: {admin_err}")
            else:
                logger.warning("Не найдены администраторы для резервной отправки уведомления о пополнении баланса")
        except Exception as backup_err:
            logger.error(f"Не удалось выполнить резервную отправку уведомлений о пополнении: {backup_err}")
    else:
        logger.error("ORM не доступен для отправки резервных уведомлений")


@router.message(F.text == "Инструкция " + "📕")
@router.message(F.text == "Instructions " + "📕")
async def instruction(message: Message, user: User, i18n: I18n):
    text = i18n.gettext(
        "📥 *Инструкция по отправке логов для анализа*:\n"
        "✅ *Лучше всего отправлять*:\n"
        "• .ips файл (например, panic-full-[data].ips)\n"
        "• .txt файл (например, экспортированный из 3uTools)\n"
        "Это даст *максимально точный результат и быстрый анализ!*\n"
        "⸻\n"
        "📸 *Также допустимы*:\n"
        "• Скриншоты или *качественные фото* panic-файлов\n"
        "• Обязательно: хорошо виден *верх файла* (самое начало текста)\n"
        "• Без бликов и размытий\n\n"
        "Файлы можно отправлять прямо сюда, как с телефона, так и с компьютера.\n"
        "⸻\n"
        "🔍 *Как найти panic-файл на iPhone*:\n"
        " 1. Откройте *Настройки*\n"
        " 2. Перейдите в *Конфиденциальность и безопасность*\n"
        " 3. Выберите *Аналитика и улучшения*\n"
        " 4. Перейдите в *Данные аналитики*\n"
        " 5. Найдите файл, начинающийся с panic-full-...\n"
        "Для лучшего результата можно отправить *несколько последних файлов*.\n"
        "⸻\n"
        "💰 *Использование токенов и бонусы*:\n"
        "• *1 токен списывается только если найдено решение*\n"
        "• 📊 *Бонус*: после первого анализа устройства вы получите ещё 9 бесплатных проверок логов для него, сроком на 30 дней\n"
        "• 🗓️ *Ежемесячный бонус*: 1-го числа в 00:05 вы получаете *+1 бесплатный токен*",
        locale=user.lang)

    await message.answer(
        text,
        reply_markup=Keyboards.back_to_home(i18n, user),
        reply_to_message_id=message.message_id,
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(F.text == "Мой баланс 💰")
@router.message(F.text == "My Balance 💰")
async def show_balance(message: Message, user: User, orm: ORM, i18n: I18n):
    if not message.from_user:
        return
    
    if not orm or not orm.user_repo:
        await message.answer(
            "❌ Сервис временно недоступен. Попробуйте позже.",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    token_balance = await orm.user_repo.get_token_balance(message.from_user.id)
    await message.answer(
        i18n.gettext("💰 Ваш текущий баланс: {} токенов.", locale=user.lang).format(token_balance),
        reply_markup=Keyboards.back_to_home(i18n, user),
        reply_to_message_id=message.message_id,
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(F.text == "Реферальная ссылка" + " 🔗")
@router.message(F.text == "Referral link" + " 🔗")
async def show_referral_link(message: Message, user: User, i18n: I18n, bot: Bot):
    bot_user = await bot.get_me()
    referral_link = f"https://t.me/{bot_user.username}?start={user.user_id}"
    text = i18n.gettext(
        "Пригласите друга и получите 2 токена после того, как он зарегистрируется по вашей ссылке.\n"
        "Ваша реферальная ссылка: {referral_link}",
        locale=user.lang
    ).format(referral_link=referral_link)
    await message.answer(
        text,
        reply_markup=Keyboards.back_to_home(i18n, user),
        disable_web_page_preview=True
    )


@router.message(F.text == "Сменить язык " + "🏳️")
@router.message(F.text == "Change language " + "🏳️")
async def change_language(message: Message, user: User, i18n: I18n, state: FSMContext):
    await state.clear()
    await message.answer(i18n.gettext("Выберите язык:", locale=user.lang),
                         reply_markup=Keyboards.lang())


@router.callback_query(LangCallback.filter())
async def change_language_callback(callback: CallbackQuery,
                                   callback_data: LangCallback,
                                   i18n: I18n,
                                   orm: ORM,
                                   state: FSMContext):
    if not callback.from_user:
        return
    
    if not orm or not orm.user_repo:
        await callback.answer("❌ Сервис временно недоступен. Попробуйте позже.", show_alert=True)
        return
    
    logger.info(f"Language change request: user_id={callback.from_user.id}, requested_lang={callback_data.lang}")
    
    await orm.user_repo.upsert_user(callback.from_user.id, lang=callback_data.lang)
    updated_user = await orm.user_repo.find_user_by_user_id(callback.from_user.id)
    user_lang_to_use = updated_user.lang if updated_user else callback_data.lang
    
    logger.info(f"Language change result: user_id={callback.from_user.id}, saved_lang={updated_user.lang if updated_user else 'None'}, using_lang={user_lang_to_use}")

    # Отправляем новое сообщение с обновленной клавиатурой
    if callback.from_user:
        try:
            bot = callback.bot
            if bot:
                message_text = i18n.gettext("Язык изменен", locale=user_lang_to_use)
                logger.info(f"Sending language changed message in {user_lang_to_use}: '{message_text}'")
                await bot.send_message(
                    callback.from_user.id,
                    message_text,
                    reply_markup=Keyboards.home(i18n, updated_user or callback.from_user)
                )
        except Exception as send_err:
            logger.error(f"Ошибка при отправке сообщения: {send_err}")
    await state.clear()


@router.message(F.text == "Назад " + "◀️")
@router.message(F.text == "Back " + "◀️")
async def back_to_home(message: Message, user: User, i18n: I18n):
    await message.answer(
        i18n.gettext(
            "Приветствую @{}🙂🤝🏼"
            "\nЯ помогу тебе с анализом сбоев"
            "\nОтправь мне файл и я его проанализирую 🔬",
            locale=user.lang).format(user.username),
        reply_markup=Keyboards.home(i18n, user))


@router.message(F.text == "Наш канал " + "👥")
@router.message(F.text == "Our channel " + "👥")
async def open_channel(message: Message, i18n: I18n, user: User):
    channel_text = i18n.gettext("Перейдите по ссылке: {channel_url}", locale=user.lang).format(channel_url=CHANNEL_URL)
    await message.answer(
        channel_text,
        reply_markup=Keyboards.back_to_home(i18n, user),
        reply_to_message_id=message.message_id,
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(F.text == ("Disk directory") + " 📚")
@router.message(F.text == ("Справочник дисков") + " 📚")
async def send_disk_guide(message: Message, i18n: I18n, user: User):
    keyboard = get_inline_button(i18n, user.lang)
    text_to_send = i18n.gettext("Нажмите кнопку ниже, чтобы начать поиск дисков:", locale=user.lang)
    await message.answer(
        text_to_send,
        reply_markup=keyboard,
    )


def get_inline_button(i18n: I18n, lang: str):
    button_text = i18n.gettext("Искать диск 🔍", locale=lang)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    switch_inline_query_current_chat="disk ",
                )
            ]
        ]
    )
    return keyboard


@router.message(Command("disk"))
async def find_command(message: Message, user: User, orm: ORM, i18n: I18n):
    if not message.text:
        return
    command_parts = message.text.split(" ", 1)
    if len(command_parts) < 2 or not command_parts[1].strip():
        logger.warning(f"Disk command received without model name: '{message.text}' from user {user.user_id}")
        await message.answer(
            i18n.gettext("Пожалуйста, укажите модель диска после команды /disk.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    model_name_query = command_parts[1].strip()
    user_lang = user.lang
    logger.info(
        f"Command '/disk' received. Model query: '{model_name_query}', User lang: {user_lang}, User ID: {user.user_id}")

    nand = NandList()
    if not nand.sheet:
        logger.error("NandList sheet is not loaded. Cannot process /disk command.")
        await message.answer(
            i18n.gettext("Ошибка: справочник дисков временно недоступен.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    answer = nand.find_info(model_name_query, user_lang)

    if answer:
        logger.info(f"Found info for model '{model_name_query}' for lang '{user_lang}':\n{answer}")
        # Важно: оригинальный код не добавлял Keyboards.back_to_home сюда, т.к. это прямой ответ информацией.
        # Если это финальное сообщение - можно добавить. Пока оставляю как было.
        await message.answer(
            str(answer),
            reply_markup=Keyboards.back_to_home(i18n, user), # Добавлено по общей логике
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN # Добавлено по общей логике
            ) 
    else:
        logger.warning(f"No info found for model '{model_name_query}' for lang '{user_lang}'.")
        all_models = nand.get_models()
        similar_models = [m['name'] for m in all_models if model_name_query.lower() in m['name'].lower()]
        if similar_models:
            suggestions = "\n".join([f"- {sm}" for sm in similar_models[:5]])
            response_text = i18n.gettext(
                "К сожалению данные по '{model_name}' не найдены. Возможно вы искали:\n{suggestions}",
                locale=user.lang).format(model_name=model_name_query, suggestions=suggestions)
        else:
            response_text = i18n.gettext("К сожалению данные по '{model_name}' не найдены.", locale=user.lang).format(
                model_name=model_name_query)
        await message.answer(
            response_text,
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )


@router.message(F.text == "Калькулятор резисторов 🧮")
@router.message(F.text == "Resistor Calculator 🧮")
async def resistor_calculator_menu(message: Message, user: User, i18n: I18n):
    """Обработчик кнопки главного меню калькулятора резисторов."""
    text = i18n.gettext(
        "🧮 *Калькулятор резисторов*\n\n"
        "Выберите тип калькулятора:",
        locale=user.lang
    )
    
    await message.answer(
        text,
        reply_markup=Keyboards.resistor_calculator_menu(i18n, user),
        parse_mode=ParseMode.MARKDOWN
    )


@router.callback_query(ResistorCalculatorTypeCallback.filter())
async def handle_resistor_calculator_type(
    callback: CallbackQuery,
    callback_data: ResistorCalculatorTypeCallback,
    user: User,
    i18n: I18n,
    state: FSMContext
):
    """Обработчик выбора типа калькулятора резисторов."""
    if not callback.message:
        await callback.answer("Ошибка: сообщение недоступно")
        return
    
    calc_type = callback_data.calculator_type
    
    if calc_type == "color":
        # Запускаем калькулятор цветовой маркировки (color → value)
        from services.telegram.handlers.tools.resistor_calculator import start_color_to_value_calculator
        await start_color_to_value_calculator(callback, state, user, i18n)
        
    elif calc_type == "reverse_color":
        # Запускаем обратный калькулятор цветовой маркировки (value → color)  
        await state.set_state(MenuResistorState.waiting_for_resistance_value)
        try:
            if callback.message and hasattr(callback.message, 'edit_text') and hasattr(callback.message, 'message_id'):
                msg = cast(Message, callback.message)
                await msg.edit_text(
                    i18n.gettext(
                        "Введите числовое значение сопротивления (например: 4.7, 150, 22).\nМожно использовать 'R' как десятичный знак (4R7 = 4.7).",
                        locale=user.lang
                    ),
                    parse_mode=None  # Убираем HTML форматирование
                )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
        
    elif calc_type == "smd_code":
        # Запускаем SMD калькулятор код → значение
        await state.set_state(MenuResistorState.waiting_for_smd_code)
        try:
            if callback.message and hasattr(callback.message, 'edit_text') and hasattr(callback.message, 'message_id'):
                msg = cast(Message, callback.message)
                await msg.edit_text(
                    i18n.gettext(
                        "📱 <b>Калькулятор SMD-резисторов</b>\n\n"
                        "Я могу рассчитать номинал по коду или найти код по номиналу.\n\n"
                        "Введите SMD код резистора:\n\n"
                        "📝 <b>Примеры по коду (режим 'Рассчитать по коду'):</b>\n"
                        "• <code>103</code> (3 цифры)\n"
                        "• <code>4702</code> (4 цифры)\n"
                        "• <code>4R7</code> (с 'R')\n"
                        "• <code>01A</code> (EIA-96)",
                        locale=user.lang
                    ),
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            
    elif calc_type == "smd_value":
        # Запускаем SMD калькулятор значение → код
        await state.set_state(MenuResistorState.waiting_for_smd_value)
        try:
            if callback.message and hasattr(callback.message, 'edit_text') and hasattr(callback.message, 'message_id'):
                msg = cast(Message, callback.message)
                await msg.edit_text(
                    i18n.gettext(
                        "⚙️ <b>Калькулятор SMD-резисторов</b>\n\n"
                        "Введите номинал для получения SMD кода:\n\n"
                        "📝 <b>Примеры по номиналу (режим 'Рассчитать по номиналу'):</b>\n"
                        "• <code>10k</code>\n"
                        "• <code>4.7M</code>\n"
                        "• <code>150</code> (будет понято как 150 Ом)",
                        locale=user.lang
                    ),
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
    
    await callback.answer()


# --- Обработчики прямого ввода из меню калькулятора ---

@router.message(MenuResistorState.waiting_for_smd_code)
async def process_menu_smd_code(message: Message, state: FSMContext, user: User, i18n: I18n):
    """Обработчик ввода SMD кода из меню."""
    if not message.text:
        return
    
    code = message.text.strip()
    
    # Используем существующую функцию для обработки SMD кода
    from services.telegram.handlers.tools.resistor_calculator import process_smd_code_calculation
    await process_smd_code_calculation(message, code, user, i18n)
    await state.clear()


@router.message(MenuResistorState.waiting_for_smd_value)
async def process_menu_smd_value(message: Message, state: FSMContext, user: User, i18n: I18n):
    """Обработчик ввода номинала для SMD кода из меню."""
    if not message.text:
        return
    
    value_str = message.text.strip()
    
    # Используем существующую функцию для обработки номинала
    from services.telegram.handlers.tools.resistor_calculator import process_smd_value
    await process_smd_value(message, state, user, i18n, provided_value=value_str)
    await state.clear()


@router.message(MenuResistorState.waiting_for_resistance_value)
async def process_menu_resistance_value(message: Message, state: FSMContext, user: User, i18n: I18n):
    """Обработчик ввода номинала для цветовой маркировки из меню."""
    if not message.text:
        return
    
    # Парсим только числовое значение (как в оригинальной команде /resistor)
    normalized_input = message.text.strip().replace(',', '.')
    
    try:
        # Check for 'R' notation and convert it
        if 'r' in normalized_input.lower():
            value_str = normalized_input.lower().replace('r', '.')
            value = float(value_str)
        else:
            value = float(normalized_input)

        if value <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            i18n.gettext("Неверный формат. Введите число, например: 4.7 или 150.", locale=user.lang)
        )
        return
    
    # Сохраняем числовое значение и переходим к выбору единиц измерения
    await state.update_data(numeric_value=value)
    await state.set_state(MenuResistorState.waiting_for_multiplier_selection)
    
    # Используем ту же логику выбора единиц измерения, что и в /resistor
    from services.telegram.misc.callbacks import ResistorCallback
    
    builder = InlineKeyboardBuilder()
    multipliers = [
        (i18n.gettext("Ом", locale=user.lang), 1), 
        (i18n.gettext("кОм", locale=user.lang), 1e3), 
        (i18n.gettext("МОм", locale=user.lang), 1e6), 
        (i18n.gettext("ГОм", locale=user.lang), 1e9)
    ]
    for name, value_mult in multipliers:
        builder.button(
            text=name,
            # Using color field to pass multiplier value
            callback_data=ResistorCallback(action="menu_select_multiplier", color=str(value_mult)).pack()
        )
    builder.adjust(4)
    
    await message.answer(
        i18n.gettext("Выберите единицу измерения:", locale=user.lang), 
        reply_markup=builder.as_markup()
    )


@router.callback_query(ResistorCallback.filter(F.action == "menu_select_multiplier"), MenuResistorState.waiting_for_multiplier_selection)
async def process_menu_multiplier_selection(query: CallbackQuery, callback_data: ResistorCallback, state: FSMContext, user: User, i18n: I18n):
    """Обработчик выбора единицы измерения из меню калькулятора."""
    if not callback_data.color:
        return
    
    multiplier = float(callback_data.color)
    data = await state.get_data()
    numeric_value = data.get("numeric_value")

    if numeric_value is None:
        await query.answer(i18n.gettext("Ошибка: числовое значение не найдено.", locale=user.lang), show_alert=True)
        return

    # Вычисляем финальное значение (как в оригинальной команде /resistor)
    final_value = numeric_value * multiplier
    await state.update_data(value=final_value)
    await state.set_state(MenuResistorState.waiting_for_tolerance_selection)

    # Переходим к выбору точности (как в оригинальной команде)
    builder = InlineKeyboardBuilder()
    tolerances = [10, 5, 2, 1, 0.5, 0.25, 0.1, 0.05]
    for t in tolerances:
        builder.button(
            text=f"±{t}%",
            callback_data=ResistorCallback(action="menu_select_tolerance", color=str(t)).pack()
        )
    builder.adjust(2)

    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(
                i18n.gettext("Выберите точность:", locale=user.lang), 
                reply_markup=builder.as_markup()
            )
        except Exception:
            # Skip if message can't be edited
            pass
    await query.answer()


@router.callback_query(ResistorCallback.filter(F.action == "menu_select_tolerance"), MenuResistorState.waiting_for_tolerance_selection)
async def process_menu_tolerance_selection(query: CallbackQuery, callback_data: ResistorCallback, state: FSMContext, user: User, i18n: I18n):
    """Обработчик выбора точности из меню калькулятора."""
    data = await state.get_data()
    
    # Get the final resistance value that was calculated in process_menu_multiplier_selection
    final_value = data.get("value")
    tolerance_str = callback_data.color
    
    if final_value is None or tolerance_str is None:
        if isinstance(query.message, Message):
            await query.message.edit_text(i18n.gettext("Произошла ошибка, попробуйте снова.", locale=user.lang))
        await state.clear()
        return

    try:
        tolerance_percent = float(tolerance_str)
    except (ValueError, TypeError):
        if isinstance(query.message, Message):
            await query.message.edit_text(i18n.gettext("Произошла ошибка, неверное значение точности.", locale=user.lang))
        await state.clear()
        return

    # Используем ту же логику расчета цветов, что и в оригинальной команде
    from services.telegram.handlers.tools.resistor_calculator import value_to_colors, format_resistance, COLOR_EMOJIS
    from services.telegram.misc.callbacks import ResistorInfoCallback
    
    colors = value_to_colors(final_value, tolerance_percent)

    if not colors:
        if isinstance(query.message, Message):
            await query.message.edit_text(i18n.gettext("Не удалось подобрать цвета для указанного номинала.", locale=user.lang))
        await state.clear()
        return

    color_names = [i18n.gettext(color.capitalize(), locale=user.lang) for color in colors]
    color_lines = [f"{COLOR_EMOJIS.get(color, '❓')} {name}" for color, name in zip(colors, color_names)]

    response = i18n.gettext(
        "🎨 <b>Цветовая маркировка для {value} (±{tolerance}%):</b>\n\n{colors_list}",
        locale=user.lang
    ).format(
        value=format_resistance(final_value, i18n, user.lang),
        tolerance=tolerance_percent,
        colors_list="\n".join(color_lines)
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.gettext("Как определить мощность на глаз?", locale=user.lang),
        callback_data=ResistorInfoCallback(action="show_power_image").pack()
    )
    
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(response, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        except Exception:
            # Если не удалось отредактировать, отправим новое сообщение
            await query.message.answer(response, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    
    await state.clear()
    await query.answer() 