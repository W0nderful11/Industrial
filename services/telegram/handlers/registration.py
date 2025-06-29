from aiogram import F, Router, Dispatcher, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, Chat, User as TgUser, InaccessibleMessage
from aiogram.utils.i18n import I18n, SimpleI18nMiddleware
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import datetime

from config import NEW_USER_BONUS_TOKENS, REFERRAL_BONUS_TOKENS
from database.database import ORM
from database.models import User
from services.telegram.misc.callbacks import LangCallback
from services.telegram.misc.keyboards import Keyboards
from services.telegram.handlers.home import home_router
from services.telegram.handlers.home.user_commands import home
from services.telegram.handlers.analyzer import analyzer, communication
from services.telegram.handlers import topup
from services.telegram.handlers.tools import resistor_calculator
from services.telegram.handlers.user import analysis_history
from services.telegram.handlers.admin import (
    registration as admin_registration, 
    replace_panic, 
    main as admin_main, 
    admin_topup, 
    debug_control,
    inline_search as admin_inline_search
)
from services.telegram.middlewares.data import DataMiddleware

router = Router()

@router.message(Command("start"))
async def start_handler(message: Message, command: CommandObject, state: FSMContext, orm: ORM, i18n: I18n):
    """
    Этот обработчик встречает нового пользователя или возвращает старого в главное меню.
    Он также обрабатывает реферальные ссылки.
    """
    if not message.from_user:
        logging.warning("Received a message with no from_user info in start_handler.")
        return

    if not orm or not orm.user_repo:
        await message.answer("❌ Сервис временно недоступен. Попробуйте позже.")
        return

    await state.clear()
    user = await orm.user_repo.find_user_by_user_id(message.from_user.id)
    
    # Если пользователь уже существует и у него установлен язык, отправляем его в главное меню.
    if user and user.lang:
        # Здесь можно было бы обработать ситуацию, когда старый пользователь переходит по реф. ссылке,
        # но по ТЗ бонус только для новых.
        await home(message, user, i18n)
        return

    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)
        # Проверяем, что реферер существует и это не сам пользователь
        if referrer_id == message.from_user.id:
            referrer_id = None 
        else:
            if orm and orm.user_repo:
                referrer_user = await orm.user_repo.find_user_by_user_id(referrer_id)
                if not referrer_user:
                    referrer_id = None 

    # Создаем пользователя, если его нет
    if not user and orm and orm.user_repo:
        await orm.user_repo.create_user(
            user_id=message.from_user.id,
            username=message.from_user.username or "",
            fullname=message.from_user.full_name,
            role="guest",
            referred_by=referrer_id
        )
    # Если пользователь уже есть (но без языка), но пришел по реф. ссылке, обновляем его
    elif referrer_id and orm and orm.user_repo:
        await orm.user_repo.upsert_user(user_id=message.from_user.id, referred_by=referrer_id)


    await message.answer(
        text="Выберите язык / Choose your language",
        reply_markup=Keyboards.lang()
    )


@router.callback_query(LangCallback.filter())
async def process_language_selection(callback: CallbackQuery, callback_data: LangCallback, orm: ORM, i18n: I18n, state: FSMContext, bot: Bot):
    """
    Этот обработчик завершает регистрацию после выбора языка.
    Начисляет бонусы, включая реферальные.
    """
    if not callback.from_user:
        logging.warning("Received a callback_query with no from_user info in process_language_selection.")
        await callback.answer("Error: user not identified.", show_alert=True)
        return

    if not orm or not orm.user_repo:
        await callback.answer("❌ Сервис временно недоступен. Попробуйте позже.", show_alert=True)
        return
        
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    full_name = callback.from_user.full_name
    lang = callback_data.lang

    i18n.ctx_locale.set(lang)

    user = await orm.user_repo.find_user_by_user_id(user_id)
    is_eligible_for_bonus = user and user.role == 'guest'

    await orm.user_repo.upsert_user(
        user_id=user_id,
        username=username,
        fullname=full_name,
        lang=lang,
        role='user'
    )

    if is_eligible_for_bonus and user and orm and orm.user_repo:
        # Бонус за регистрацию
        if NEW_USER_BONUS_TOKENS > 0:
            await orm.user_repo.add_tokens(
                user_id=user_id,
                tokens_to_add=NEW_USER_BONUS_TOKENS,
                notify_user=False
            )
            welcome_message = i18n.gettext(
                "🎁 Welcome bonus: {count} tokens have been credited to your account.",
                locale=lang
            ).format(count=NEW_USER_BONUS_TOKENS)
            await bot.send_message(chat_id=user_id, text=welcome_message)

        # Реферальный бонус
        if user.referred_by and REFERRAL_BONUS_TOKENS > 0:
            referrer_id = user.referred_by
            referrer = await orm.user_repo.find_user_by_user_id(referrer_id)
            if referrer:
                # Начисляем токены рефереру
                referrer_lang = referrer.lang or "ru"
                await orm.user_repo.add_tokens(
                    user_id=referrer_id,
                    tokens_to_add=REFERRAL_BONUS_TOKENS,
                    notify_user=True,
                    notification_text=i18n.gettext(
                        "🎉 A new user has registered using your referral link! You have been credited with {count} tokens.",
                        locale=referrer_lang
                    ).format(count=REFERRAL_BONUS_TOKENS)
                )
    
    # Безопасное удаление сообщения
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            if hasattr(callback.message, 'delete'):
                await callback.message.delete() 
        except Exception as e:
            # Сообщение может быть уже удалено или недоступно - это нормально
            logging.warning(f"Could not delete message after language selection: {e}")
        
    if orm and orm.user_repo:
        updated_user = await orm.user_repo.find_user_by_user_id(user_id)

        if updated_user:
            # Since we might have deleted the original message, we cannot use it.
            # We also cannot call `home` as it requires a message object.
            # We will manually send the greeting message and home keyboard.
            # This is a more robust way than trying to call `home`.
            
            reply_markup = Keyboards.home(i18n, updated_user)
            greeting_message = i18n.gettext(
                "Приветствую @{}🙂🤝🏼"
                "\nЯ помогу тебе с анализом сбоев"
                "\nОтправь мне файл и я его проанализирую 🔬",
                locale=updated_user.lang
            ).format(updated_user.username)

            await bot.send_message(
                chat_id=user_id,
                text=greeting_message,
                reply_markup=reply_markup
            )

    logging.info(f"User {user_id} ({full_name}) has been successfully registered with lang='{lang}'.")


class TgRegister:
    def __init__(self, dp: Dispatcher, orm: ORM, i18n):
        self.dp = dp
        self.orm = orm
        self.i18n = i18n

    def register(self):
        self._register_handlers()
        self._register_middlewares()

    def _register_handlers(self):
        # home
        self.dp.include_routers(home_router, router)
        # analyzer
        self.dp.include_routers(analyzer.router, communication.router)
        # topup
        self.dp.include_routers(topup.router)
        # tools
        self.dp.include_routers(resistor_calculator.router)
        # user handlers
        self.dp.include_routers(analysis_history.router)
        # admin
        self.dp.include_routers(
            admin_registration.router, 
            replace_panic.router, 
            admin_main.router, 
            admin_topup.admin_topup_router,
            debug_control.router,
            admin_inline_search.router
        )

    def _register_middlewares(self):
        scheduler = AsyncIOScheduler(timezone="Asia/Almaty")
        scheduler.start()
        i18n_middleware = SimpleI18nMiddleware(self.i18n, "i18n", "i18n_middleware")
        middleware = DataMiddleware(self.orm, scheduler, i18n_middleware.i18n)

        self.dp.update.middleware(middleware)
        self.dp.update.middleware(i18n_middleware)
        self.dp.callback_query.middleware(middleware)
        self.dp.callback_query.middleware(i18n_middleware)
        self.dp.message.middleware(middleware)
        self.dp.message.middleware(i18n_middleware)
        self.dp.inline_query.middleware(middleware)
        self.dp.inline_query.middleware(i18n_middleware)

        self.setup_middleware()

    def setup_middleware(self):
        # Implementation of setup_middleware method
        pass