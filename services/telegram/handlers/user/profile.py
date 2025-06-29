import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.i18n import I18n
from database.database import ORM
from database.models import User  # Убедитесь, что User импортирован

logger = logging.getLogger(__name__)
router = Router()


async def get_admin_contacts(orm: ORM) -> str:
    # admins = await orm.user_repo.get_admins()
    # admin_contact_info = ""
    # if admins:
    #     admin_contact_info = "\n".join([f"@{admin.username}" for admin in admins if admin.username])
    # if not admin_contact_info: # Fallback
    #     admin_contact_info = "@masterkazakhstan"
    # return admin_contact_info
    return "@masterkazakhstan"  # Всегда возвращаем этого администратора для данного контекста


# Обработчик для текстовой кнопки "Пополнить баланс 💳"
# Текст кнопки может зависеть от локализации, поэтому используем F.text и проверяем содержимое.
# Это пример, точный текст кнопки нужно будет проверить или использовать более гибкий фильтр.
@router.message(F.text.contains("Пополнить баланс") & F.text.contains("💳"))
async def handle_top_up_balance_text_request(message: Message, orm: ORM, i18n: I18n, user: User):
    admin_contacts = await get_admin_contacts(orm)
    await message.answer(
        i18n.gettext(
            "Для пополнения баланса свяжитесь с администратором:\n{admin_contacts}",
            locale=user.lang
        ).format(admin_contacts=admin_contacts)
    )


# Обработчик для inline-кнопки с callback_data="topup_balance_user"
@router.callback_query(F.data == "topup_balance_user")
async def handle_top_up_balance_callback_request(callback: CallbackQuery, orm: ORM, i18n: I18n, user: User):
    admin_contacts = await get_admin_contacts(orm)
    await callback.message.answer(
        i18n.gettext(
            "Для пополнения баланса свяжитесь с администратором:\n{admin_contacts}",
            locale=user.lang
        ).format(admin_contacts=admin_contacts)
    )
    await callback.answer()

# Не забудьте подключить этот роутер в основном файле, например, в main.py или app.py:
# from services.telegram.handlers.user import profile
# dp.include_router(profile.router)
