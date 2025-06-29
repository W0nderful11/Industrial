from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.i18n import I18n
from decimal import Decimal

from database.database import ORM
from database.models import User # Нужен для type hinting и RoleFilter
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.keyboards import Keyboards

# Импорт логгера из __init__.py текущего пакета
from . import logger

router = Router()
# Фильтр RoleFilter(roles=["admin"]) будет применен к каждому хэндлеру индивидуально, 
# так как не все хэндлеры в home являются исключительно админскими.
# Однако, все хэндлеры в этом файле - админские.
router.message.filter(RoleFilter(roles=["admin"]))
# router.callback_query.filter(RoleFilter(roles=["admin"])) # Если будут callback-хэндлеры для админов тут


@router.message(F.text.regexp(r"^\+?\d{5,}\s+\d+$")) # RoleFilter(roles=["admin"]) уже на роутере
async def universal_admin_topup(message: Message, orm: ORM, i18n: I18n):
    admin_user = await orm.user_repo.find_user_by_user_id(message.from_user.id)
    if not admin_user: # admin_user здесь это тот, кто отправляет команду, он должен быть админом
        logger.error(f"Admin user {message.from_user.id} not found in universal_admin_topup.")
        await message.answer(
            i18n.gettext("Произошла ошибка: не удалось получить данные администратора для отображения меню.", locale=message.from_user.language_code)
        )
        return

    try:
        text = message.text.lstrip('+').strip()
        user_id_str, amount_str = text.split()
        user_id = int(user_id_str)
        tokens_to_add = int(amount_str)

        if tokens_to_add <= 0:
            await message.answer(
                i18n.gettext("Количество токенов должно быть положительным.", locale=admin_user.lang),
                reply_markup=Keyboards.back_to_home(i18n, admin_user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        target_user = await orm.user_repo.find_user_by_user_id(user_id) # Пользователь, которому пополняют
        if not target_user:
            await message.answer(
                f"❌ Пользователь с ID {user_id} не найден.",
                reply_markup=Keyboards.back_to_home(i18n, admin_user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        success = await orm.user_repo.add_tokens(user_id=user_id, tokens_to_add=tokens_to_add,
                                                 admin_id=message.from_user.id)

        if not success:
            await message.answer(
                "❌ Не удалось добавить токены (возможно, пользователь не найден).",
                reply_markup=Keyboards.back_to_home(i18n, admin_user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        new_token_balance = await orm.user_repo.get_token_balance(user_id)

        await message.answer(
            i18n.gettext("✅ Пользователю {user_id} добавлено {tokens} токенов. Новый баланс: {new_balance} токенов.",
                         locale=admin_user.lang).format(
                user_id=user_id,
                tokens=tokens_to_add,
                new_balance=new_token_balance
            ),
            reply_markup=Keyboards.back_to_home(i18n, admin_user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )

    except ValueError:
        await message.answer(
            i18n.gettext(
            "❌ Ошибка формата данных. Используйте: + [user_id] [кол-во_токенов]. Убедитесь, что ID и количество токенов - целые числа.",
            locale=admin_user.lang),
            reply_markup=Keyboards.back_to_home(i18n, admin_user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Ошибка универсального пополнения токенов: {e}", exc_info=True)
        await message.answer(
            "⚠️ Произошла системная ошибка при добавлении токенов.",
            reply_markup=Keyboards.back_to_home(i18n, admin_user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )


@router.message(Command("admin_balance")) # RoleFilter(roles=["admin"]) уже на роутере
async def show_admin_menu(message: Message, i18n: I18n, user: User): # Добавил i18n, user для клавиатуры
    await message.answer(
        i18n.gettext("🔧 Меню управления балансом:", locale=user.lang),
        reply_markup=Keyboards.admin_balance_menu(i18n, user) # Передаем i18n и user
    )


@router.message(F.text.regexp(r"^\d+\s+\d+$")) # RoleFilter(roles=["admin"]) уже на роутере
async def admin_manual_topup(message: Message, orm: ORM, i18n: I18n):
    admin_user = await orm.user_repo.find_user_by_user_id(message.from_user.id)
    if not admin_user:
        logger.error(f"Admin user {message.from_user.id} not found in admin_manual_topup.")
        await message.answer(
            i18n.gettext("Произошла ошибка: не удалось получить данные администратора для отображения меню.", locale=message.from_user.language_code)
        )
        return
    try:
        user_id_str, amount_str = message.text.strip().split()
        user_id = int(user_id_str)
        amount = Decimal(amount_str)

        target_user = await orm.user_repo.find_user_by_user_id(user_id)
        if not target_user:
            await message.answer(
                f"❌ Пользователь с ID {user_id} не найден.",
                reply_markup=Keyboards.back_to_home(i18n, admin_user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        country_code = await orm.user_repo.get_country_code(user_id)
        _, currency_symbol = await orm.currency_repo.get_price_in_user_currency(Decimal("0"), country_code)

        success = await orm.user_repo.update_balance(user_id, amount)
        if not success:
            await message.answer(
                "❌ Не удалось обновить баланс.",
                reply_markup=Keyboards.back_to_home(i18n, admin_user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return
        await message.answer(
            f"✅ Баланс пользователя {user_id} пополнен на {amount}{currency_symbol}",
            reply_markup=Keyboards.back_to_home(i18n, admin_user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Ошибка пополнения: {e}", exc_info=True)
        await message.answer(
            "⚠️ Произошла ошибка при пополнении. Проверь данные.",
            reply_markup=Keyboards.back_to_home(i18n, admin_user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )


@router.message(F.text.startswith("+")) # RoleFilter(roles=["admin"]) уже на роутере
async def quick_topup_handler(message: Message, user: User, orm: ORM, i18n: I18n):
    # user здесь это admin_user, так как RoleFilter("admin") применен
    try:
        parts = message.text.split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit(): # Проверка что amount тоже digit
            await message.answer(
                "❌ Неверный формат: Используйте + [user_id] [amount]",
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        user_id_to_topup = int(parts[1])
        tokens_to_add = int(parts[2])

        if not await orm.user_repo.user_exists(user_id_to_topup):
            await message.answer(
                f"👤 Пользователь {user_id_to_topup} не найден",
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        success = await orm.user_repo.add_tokens(user_id=user_id_to_topup, tokens_to_add=tokens_to_add,
                                                 admin_id=message.from_user.id)
        if not success:
            await message.answer(
                "❌ Ошибка при добавлении токенов",
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        new_token_balance = await orm.user_repo.get_token_balance(user_id_to_topup)
        await message.answer(
            f"✅ Пользователю {user_id_to_topup} добавлено {tokens_to_add} токенов. Новый баланс: {new_token_balance} токенов.",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )

    except ValueError as e: # Если int() не удался
        await message.answer(
            f"❌ Ошибка формата данных: {str(e)}. Используйте + [user_id] [amount]",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Critical error in quick_topup_handler: {str(e)}", exc_info=True)
        await message.answer(
            "⚠️ Произошла системная ошибка",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )


@router.message(F.text.startswith("-")) # RoleFilter(roles=["admin"]) уже на роутере
async def quick_deduct_handler(message: Message, user: User, orm: ORM, i18n: I18n):
    # user здесь это admin_user
    try:
        text = message.text.lstrip('-').strip() # Убираем минус и лишние пробелы
        parts = text.split()

        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await message.answer(
                "❌ Неверный формат: Используйте -[user_id] [amount]",
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        user_id_to_deduct = int(parts[0])
        tokens_to_deduct = int(parts[1])

        if not await orm.user_repo.user_exists(user_id_to_deduct):
            await message.answer(
                f"👤 Пользователь {user_id_to_deduct} не найден",
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        current_token_balance = await orm.user_repo.get_token_balance(user_id_to_deduct)
        if current_token_balance < tokens_to_deduct:
            await message.answer(
                f"❌ Недостаточно токенов для списания. Текущий баланс: {current_token_balance}",
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        success = await orm.user_repo.deduct_tokens(user_id=user_id_to_deduct, tokens_to_deduct=tokens_to_deduct,
                                                    admin_id=message.from_user.id)
        if not success:
            await message.answer(
                "❌ Ошибка при списании токенов",
                reply_markup=Keyboards.back_to_home(i18n, user),
                reply_to_message_id=message.message_id,
                parse_mode=ParseMode.MARKDOWN
            )
            return

        new_token_balance = await orm.user_repo.get_token_balance(user_id_to_deduct)
        await message.answer(
            f"✅ У пользователя {user_id_to_deduct} списано {tokens_to_deduct} токенов. Новый баланс: {new_token_balance} токенов.",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )

    except ValueError as e: # Если int() не удался
        await message.answer(
            f"❌ Ошибка формата данных: {str(e)}. Используйте -[user_id] [amount]",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Critical error in quick_deduct_handler: {str(e)}", exc_info=True)
        await message.answer(
            "⚠️ Произошла системная ошибка",
            reply_markup=Keyboards.back_to_home(i18n, user),
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.MARKDOWN
        )


@router.message(F.text == "Admin panel ⚙️")
@router.message(F.text == "Админ панель ⚙️") # RoleFilter(roles=["admin"]) уже на роутере
async def open_admin_panel(message: Message, user: User, i18n: I18n):
    # user здесь это admin_user, так как RoleFilter("admin") применен
    admin_keyboard = Keyboards.admin_panel(i18n, user)
    # Ответ всегда на русском для админ панели, как в оригинале
    await message.answer(i18n.gettext("Добро пожаловать в админ панель!", locale='ru'), reply_markup=admin_keyboard) 