from typing import Dict, Any, Awaitable, Callable
import logging

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, Message, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Environ
from database.database import ORM


class DataMiddleware(BaseMiddleware):
    def __init__(self, orm: ORM, scheduler: AsyncIOScheduler, i18n ):
        self.orm = orm
        self.scheduler = scheduler
        self.i18n = i18n

    async def __call__(
            self,
            handler: Callable[
                [TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        data["env"] = Environ()
        data["orm"] = self.orm
        data["scheduler"] = self.scheduler
        data["i18n"] = self.i18n

        # Проверяем, есть ли у события пользователь (для Message, CallbackQuery и т.д.)
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, "from_user"):
            from_user = getattr(event, "from_user", None)
            if from_user:
                user_id = from_user.id
            
        if user_id and self.orm.user_repo:
            try:
                user = await self.orm.user_repo.find_user_by_user_id(user_id)
                if user:
                    data["user"] = user
            except Exception as e:
                logging.error(f"Ошибка при получении пользователя {user_id}: {e}")
    
        return await handler(event, data)


