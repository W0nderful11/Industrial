from aiogram import Router, F
from aiogram.types import InlineQuery, InputTextMessageContent, InlineQueryResultArticle
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.telegram.filters.role import RoleFilter

router = Router()
# Фильтруем, чтобы inline-обработчик срабатывал только для админов
router.inline_query.filter(RoleFilter(roles=["admin"]))

@router.inline_query()
async def admin_user_search_inline(inline_query: InlineQuery, orm: ORM, i18n: I18n, user):
    """
    Обрабатывает inline-запросы от администраторов для поиска пользователей.
    """
    query = inline_query.query or ''
    results = []
    
    # Если запрос пустой, ничего не показываем
    if not query:
        await inline_query.answer(results, cache_time=0)
        return

    # Ищем пользователей в БД
    users, _ = await orm.user_repo.search_users(query, page=0, limit=10)

    if users:
        for found_user in users:
            # Формируем текст с детальной информацией о пользователе
            user_details_text = (
                f"👤 <b>Пользователь:</b> {found_user.fullname or 'N/A'} (<code>{found_user.user_id}</code>)\n"
                f"<b>Ник:</b> @{found_user.username or 'N/A'}\n"
                f"<b>Баланс:</b> {found_user.token_balance} 🪙\n"
                f"<b>Роль:</b> {found_user.role}\n"
                f"<b>Язык:</b> {found_user.lang}\n"
                f"<b>Дата регистрации:</b> {found_user.created_at.strftime('%Y-%m-%d') if found_user.created_at else 'N/A'}"
            )
            
            # Создаем результат для выпадающего списка
            result = InlineQueryResultArticle(
                id=str(found_user.user_id),
                title=f"{found_user.fullname or 'N/A'} (@{found_user.username or 'N/A'})",
                description=f"ID: {found_user.user_id} | Токены: {found_user.token_balance}",
                input_message_content=InputTextMessageContent(
                    message_text=user_details_text,
                    parse_mode="HTML"
                )
            )
            results.append(result)

    await inline_query.answer(results, cache_time=10) 