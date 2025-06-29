from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.utils.i18n import I18n
from decimal import Decimal

from database.database import ORM
from database.models import User # Для User в параметрах и получения admin_user
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.keyboards import Keyboards
from services.telegram.handlers.states import DeleteUserStates, BalanceStates # AdminStates не используется напрямую тут

# Импорт логгера из __init__.py текущего пакета
from . import logger

router = Router()
router.message.filter(RoleFilter(roles=["admin"])) 

# Глобальная переменная, как в оригинале. Рассмотреть рефакторинг в будущем.
PRICE_PER_ANALYSIS = 1.0 # Значение по умолчанию, если оно не было установлено


@router.message(DeleteUserStates.waiting_for_user_id)
async def delete_user_by_id_state(message: Message, state: FSMContext, orm: ORM, i18n: I18n, user: User):
    # user здесь - это админ, выполняющий действие, т.к. router.message.filter(RoleFilter(roles=["admin"]))
    try:
        user_id_to_delete = int(message.text)
        user_to_delete = await orm.user_repo.find_user_by_user_id(user_id_to_delete)

        if user_to_delete:
            await orm.user_repo.delete_user(user_id=user_to_delete.user_id)
            await message.answer(
                i18n.gettext("Пользователь удален!", locale=user.lang),
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.answer(
                i18n.gettext("Пользователь с таким ID не найден.", locale=user.lang),
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )

    except ValueError:
        await message.answer(
            i18n.gettext("Неверный формат user_id. Пожалуйста, введите число.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except AttributeError as ae: # Пример из оригинального кода
        logger.error(f"Ошибка при вызове метода удаления пользователя: {ae}")
        await message.answer(
            i18n.gettext("Ошибка конфигурации сервера при удалении пользователя.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error deleting user by id state: {e}", exc_info=True)
        await message.answer(
            i18n.gettext("Ошибка при удалении пользователя.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        await state.clear()


@router.message(BalanceStates.waiting_for_pricing)
async def update_pricing_state(message: Message, orm: ORM, i18n: I18n, state: FSMContext, user: User):
    # user здесь - админ
    global PRICE_PER_ANALYSIS
    try:
        PRICE_PER_ANALYSIS = float(message.text)
        # TODO: Сохранять PRICE_PER_ANALYSIS в БД или конфиг, а не в global
        await message.answer(
            f"Новая стоимость установлена: {PRICE_PER_ANALYSIS}₸",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except ValueError:
        await message.answer(
            i18n.gettext("Ошибка! Введите число", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        await state.clear()


@router.message(StateFilter("admin_check_balance_wait"))
async def check_balance_state(message: Message, state: FSMContext, orm: ORM, i18n: I18n, user: User):
    # user здесь - админ
    try:
        user_id_to_check = int(message.text)
        # balance = await orm.user_repo.get_balance(user_id_to_check) # get_balance может не быть, используем get_token_balance
        token_balance = await orm.user_repo.get_token_balance(user_id_to_check)
        # _, currency_symbol = await orm.currency_repo.get_price_in_user_currency(Decimal("0"), target_user.country) # Если нужен символ
        
        # Проверим, существует ли пользователь, чтобы дать более осмысленное сообщение
        target_user = await orm.user_repo.find_user_by_user_id(user_id_to_check)
        if not target_user:
            await message.answer(
                i18n.gettext("Пользователь с ID {} не найден.", locale=user.lang).format(user_id_to_check),
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.answer(
                # f"Баланс пользователя {user_id_to_check}: {token_balance}₸" # Если предполагается тенге
                i18n.gettext("Баланс пользователя {user_id}: {balance} токенов.", locale=user.lang).format(user_id=user_id_to_check, balance=token_balance),
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
    except ValueError:
        await message.answer(
            i18n.gettext("Неверный формат user_id. Пожалуйста, введите число.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in check_balance_state: {e}", exc_info=True)
        await message.answer(
            i18n.gettext("Произошла ошибка при проверке баланса.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        await state.clear()


@router.message(StateFilter("admin_history_wait"))
async def show_history_state(message: Message, state: FSMContext, orm: ORM, i18n: I18n, user: User):
    # user здесь - админ
    try:
        user_id_for_history = int(message.text)
        # Здесь должна быть логика истории, которой нет в оригинале
        await message.answer(
            f"История пользователя {user_id_for_history}: ...", # Заглушка, как в оригинале
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except ValueError:
        await message.answer(
            i18n.gettext("Неверный формат user_id. Пожалуйста, введите число.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in show_history_state: {e}", exc_info=True)
        await message.answer(
            i18n.gettext("Произошла ошибка при получении истории.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        await state.clear()


@router.message(StateFilter("admin_reset_wait"))
async def reset_balance_state(message: Message, state: FSMContext, orm: ORM, i18n: I18n, user: User):
    # user здесь - админ
    try:
        user_id_to_reset = int(message.text)
        
        target_user = await orm.user_repo.find_user_by_user_id(user_id_to_reset)
        if not target_user:
            await message.answer(
                i18n.gettext("Пользователь с ID {} не найден.", locale=user.lang).format(user_id_to_reset),
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await orm.user_repo.update_balance(user_id_to_reset, Decimal(0)) # Обнуление баланса
            await orm.user_repo.update_tokens(user_id_to_reset, 0) # Обнуление токенов, если это отдельное поле
            await message.answer(
                i18n.gettext("Баланс пользователя {} обнулён.", locale=user.lang).format(user_id_to_reset),
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
    except ValueError:
        await message.answer(
            i18n.gettext("Неверный формат user_id. Пожалуйста, введите число.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in reset_balance_state: {e}", exc_info=True)
        await message.answer(
            i18n.gettext("Произошла ошибка при обнулении баланса.", locale=user.lang),
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        await state.clear()


@router.message(StateFilter("custom_topup_waiting_amount"))
async def process_custom_topup_state(message: Message, state: FSMContext, orm: ORM, i18n: I18n, user: User):
    admin_user = user 

    try:
        amount_to_add = Decimal(message.text)
        if amount_to_add <= 0:
            await message.answer(
                i18n.gettext("Сумма должна быть положительной.", locale=admin_user.lang),
                reply_markup=Keyboards.back_to_home(i18n, admin_user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return # Не очищаем состояние, чтобы дать еще попытку
        
        data = await state.get_data()
        user_id_to_topup = data.get("user_id")

        if not user_id_to_topup:
            logger.error("user_id not found in state for process_custom_topup_state")
            await message.answer(
                i18n.gettext("Произошла ошибка: не найден ID пользователя для пополнения.", locale=admin_user.lang),
                reply_markup=Keyboards.back_to_home(i18n, admin_user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            await state.clear()
            return
        
        # Проверяем, существует ли пользователь, которому пополняем
        target_user = await orm.user_repo.find_user_by_user_id(user_id_to_topup)
        if not target_user:
            await message.answer(
                i18n.gettext("Пользователь с ID {} не найден.", locale=admin_user.lang).format(user_id_to_topup),
                reply_markup=Keyboards.back_to_home(i18n, admin_user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            await state.clear()
            return

        # Пополняем баланс/токены. В оригинале был update_balance.
        # Если у вас есть токены, то orm.user_repo.add_tokens
        # Если это денежный баланс, то update_balance
        # Судя по названию `custom_topup_waiting_amount` и Decimal, это может быть денежный баланс.
        await orm.user_repo.update_balance(user_id_to_topup, amount_to_add)
        # Или, если это токены:
        # await orm.user_repo.add_tokens(user_id=user_id_to_topup, tokens_to_add=int(amount_to_add), admin_id=admin_user.user_id)
        
        # Получаем символ валюты или просто указываем "ед."
        # country_code = await orm.user_repo.get_country_code(user_id_to_topup)
        # _, currency_symbol = await orm.currency_repo.get_price_in_user_currency(Decimal("0"), country_code)
        currency_symbol = "ед." # Заглушка, так как непонятно, токены это или валюта
        
        await message.answer(
            i18n.gettext("✅ Баланс пользователя {user_id} пополнен на {amount}{symbol}.", locale=admin_user.lang).format(user_id=user_id_to_topup, amount=amount_to_add, symbol=currency_symbol),
            reply_markup=Keyboards.back_to_home(i18n, admin_user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
        await state.clear()

    except InvalidOperation: # Ошибка преобразования Decimal
        await message.answer(
            i18n.gettext("Неверный формат суммы. Пожалуйста, введите число (например, 100 или 100.50).", locale=admin_user.lang),
            reply_markup=Keyboards.back_to_home(i18n, admin_user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
        # Не очищаем состояние, даем еще попытку
    except Exception as e:
        logger.error(f"Error in process_custom_topup_state: {e}", exc_info=True)
        await message.answer(
            i18n.gettext("Произошла системная ошибка при пополнении.", locale=admin_user.lang),
            reply_markup=Keyboards.back_to_home(i18n, admin_user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
        await state.clear() 