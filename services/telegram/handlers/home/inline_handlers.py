from aiogram import Router, F
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.utils.i18n import I18n

from database.database import ORM
from services.analyzer.nand import NandList

# Импорт логгера из __init__.py текущего пакета
from . import logger

router = Router()
# Inline хэндлеры обычно не фильтруются по ролям на уровне роутера
# router.inline_query.filter(RoleFilter(roles=["admin", "user"])) # Если нужно, можно добавить

@router.inline_query(F.query.startswith('disk '))
async def find_disk_inline(inq: InlineQuery, i18n: I18n, orm: ORM):
    query = inq.query[5:].strip() # Убираем "disk " из начала запроса
    # Язык пользователя для i18n можно получить из inq.from_user.language_code
    # В оригинальном коде был выбор между 'ru' и 'en' с фолбэком на 'ru'
    user_lang = 'ru' # Упрощенный вариант, лучше использовать i18n.locale или inq.from_user.language_code
    if hasattr(inq.from_user, 'language_code') and inq.from_user.language_code in i18n.available_locales:
        user_lang = inq.from_user.language_code
    
    logger.info(f"Inline query 'disk' received. Query: '{query}', User lang: {user_lang}, User ID: {inq.from_user.id}")
    results = []

    if query: # Только если запрос не пустой
        nand = NandList()  # Использует путь по умолчанию ./data/nand_list.xlsx
        if not nand.sheet:  # Проверка, что Excel загружен
            logger.error("NandList sheet is not loaded. Cannot process inline disk query.")
            # В этом случае пользователю ничего не будет показано, кроме, возможно, заглушки от Telegram
            # Можно отправить пустой результат с cache_time, чтобы Telegram не ждал долго
            await inq.answer(results=results, cache_time=10) # cache_time из оригинала
            return

        all_models = nand.get_models()
        # logger.debug(f"All models from NandList for inline query: {all_models[:10]}") # Убрано для краткости

        # Фильтрация моделей: ищем query в model['name'] без учета регистра
        filtered_models = [model for model in all_models if query.lower() in model['name'].lower()]
        logger.info(f"Found {len(filtered_models)} models matching query '{query}'.")

        # Ограничение на количество результатов, как в оригинале (было < 50, потом [:50])
        for model_data in filtered_models[:50]: 
            results.append(
                InlineQueryResultArticle(
                    id=str(model_data['row']),  # ID должен быть строкой
                    title=model_data['name'],  # Показываем имя модели в результатах
                    input_message_content=InputTextMessageContent(
                        message_text=f"/disk {model_data['name']}"  # Отправляем команду /disk ИмяМодели
                    ),
                    # description=i18n.gettext("Нажмите для получения информации", locale=user_lang) # Можно добавить описание
                )
            )
        logger.debug(f"Prepared {len(results)} results for inline query '{query}'.")
    else:
        logger.info("Empty query for inline disk search.")
        # Можно отправить инструкцию, если запрос пустой
        # results.append(InlineQueryResultArticle(...))

    try:
        await inq.answer(results=results, cache_time=10) # cache_time из оригинала
    except Exception as e:
        logger.error(f"Error answering inline query: {e}", exc_info=True) 