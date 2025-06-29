"""
Анализатор файлов - объединенный модуль
"""
from aiogram import Router

from services.telegram.filters.role import RoleFilter
from . import handlers, callbacks, feedback

# Создаем главный роутер для анализатора
router = Router()

# Применяем фильтры на весь модуль
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))

# Включаем все подроутеры
router.include_router(handlers.router)
router.include_router(callbacks.router)
router.include_router(feedback.router)

# Экспортируем для использования в других модулях
__all__ = ["router"]
