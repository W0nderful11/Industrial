from datetime import datetime, timedelta
from aiogram.types import Message
from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import Optional
import logging

from database.models import Subscription
from database.repo.repo import Repo

logger = logging.getLogger(__name__)

class SubscriptionRepo(Repo):
    async def get_subscription(self, user_id: int, crash_reporter_key: str) -> Optional[Subscription]:
        """Получает запись подписки по user_id и crash_reporter_key."""
        async with self.sessionmaker() as session:
            result = await session.scalar(
                select(Subscription)
                .where(
                    and_(
                        Subscription.user_id == user_id,
                        Subscription.crash_reporter_key == crash_reporter_key
                    )
                )
            )
            return result

    async def create_or_reset_subscription(
            self,
            user_id: int,
            crash_reporter_key: str,
            start_date: datetime,
            end_date: datetime
    ) -> bool:
        """
        Управляет записью о подписке для пользователя и crash_reporter_key.
        - Если у пользователя уже есть подписка на этот crash_reporter_key, она сбрасывается.
        - Если crash_reporter_key новый глобально, создается новая подписка для пользователя.
        - Если crash_reporter_key существует глобально (отправлен другим пользователем),
          новая запись о подписке для текущего пользователя не создается,
          но функция возвращает True, чтобы разрешить обработку и списание токена вызывающим кодом.
        Возвращает True, если операция концептуально успешна (обработка может продолжаться),
        False при непредвиденных ошибках.
        """
        async with self.sessionmaker() as session:
            # Сначала проверяем, есть ли у пользователя уже подписка на этот ключ
            existing_sub_for_user = await session.scalar(
                select(Subscription).where(
                    and_(
                        Subscription.user_id == user_id,
                        Subscription.crash_reporter_key == crash_reporter_key
                    )
                )
            )

            # ЯВНО ЗАВЕРШАЕМ ТРАНЗАКЦИЮ, НАЧАТУЮ ДЛЯ ЧТЕНИЯ ВЫШЕ
            # Это необходимо, чтобы следующий блок session.begin() мог корректно начать новую транзакцию.
            await session.commit()

            if existing_sub_for_user:
                # Начинаем явную транзакцию для операции обновления
                async with session.begin():
                    existing_sub_for_user.analysis_count = 1
                    existing_sub_for_user.date_start = start_date
                    existing_sub_for_user.date_end = end_date
                    existing_sub_for_user.is_warn = False
                    session.add(existing_sub_for_user) # Убедимся, что объект отслеживается сессией для flush
                # Транзакция автоматически коммитится здесь при выходе из блока, если не было ошибок
                return True
            else:
                # У пользователя нет подписки на этот crash_reporter_key.
                # Проверяем, существует ли ключ глобально (этот метод использует свою собственную сессию).
                key_is_globally_known = await self.check_crash_key_exists(crash_reporter_key)

                if key_is_globally_known:
                    # Ключ существует в системе (вероятно, от другого пользователя).
                    # Для текущего пользователя запись в subscriptions не создаем и не изменяем.
                    # Возвращаем True, чтобы разрешить дальнейшую обработку и списание токена.
                    return True
                else:
                    # Ключ глобально новый. Пытаемся создать новую подписку для этого пользователя.
                    try:
                        # Начинаем явную транзакцию для операции вставки
                        async with session.begin(): # Это место, где возникала ошибка (ранее строка 78)
                            new_sub = Subscription(
                                user_id=user_id,
                                crash_reporter_key=crash_reporter_key,
                                analysis_count=1,
                                date_start=start_date,
                                date_end=end_date,
                                is_warn=False
                            )
                            session.add(new_sub)
                        # Транзакция автоматически коммитится здесь, если не было ошибок
                        return True
                    except IntegrityError:
                        # session.begin() автоматически откатит транзакцию в случае ошибки
                        # Это обычно означает гонку транзакций: другой процесс только что вставил этот crash_reporter_key.
                        # Проверяем, действительно ли ключ теперь существует.
                        if await self.check_crash_key_exists(crash_reporter_key):
                            # Ключ действительно был вставлен конкурентно. Это приемлемый исход.
                            return True
                        else:
                            # IntegrityError по другой причине, или ключ все еще не существует (неожиданно).
                            # Здесь можно добавить логирование этой ситуации.
                            return False
                    except Exception:
                        # session.begin() автоматически откатит транзакцию.
                        # Любая другая ошибка при вставке. Можно логировать.
                        return False
        # Эта часть не должна быть достигнута, если логика выше исчерпывающая.
        # Возвращаем False для безопасности.
        return False

    async def increment_analysis_count(self, user_id: int, crash_reporter_key: str) -> bool:
        """Увеличивает счетчик бесплатных анализов для активной подписки."""
        async with self.sessionmaker() as session:
            async with session.begin(): # Контекстный менеджер обработает commit/rollback
                result = await session.execute(
                    update(Subscription)
                    .where(
                        and_(
                            Subscription.user_id == user_id,
                            Subscription.crash_reporter_key == crash_reporter_key,
                            Subscription.date_end > func.now(),  # Убедимся, что подписка активна
                            Subscription.analysis_count < 10  # Убедимся, что лимит не достигнут
                        )
                    )
                    .values(analysis_count=Subscription.analysis_count + 1)
                    .returning(Subscription.id)
                )
                updated_id = result.scalar_one_or_none()
                if updated_id:
                    # await session.commit() # УДАЛЕНО - обрабатывается session.begin()
                    return True
                else:
                    # Не удалось обновить (подписка не найдена, истекла или лимит исчерпан)
                    # await session.rollback() # УДАЛЕНО - обрабатывается session.begin()
                    return False

    async def get_expired(self):
        async with self.sessionmaker() as session:
            expired = await session.scalars(select(Subscription).where(Subscription.date_end <= datetime.now()))
            almost_expired = await session.scalars(
                select(Subscription).where(
                    (datetime.now() + timedelta(days=1) >= Subscription.date_end) & (Subscription.is_warn.is_(False))
                )
            )
            return expired.all(), almost_expired.all()

    async def delete_subscription(self, user_id: int):
        async with self.sessionmaker() as session:
            async with session.begin(): # Добавлен session.begin() для управления транзакцией
                await session.execute(delete(Subscription).where(Subscription.user_id == user_id))
            # await session.commit() # УДАЛЕНО - обрабатывается session.begin()

    async def warn_user(self, user_id: int):
        async with self.sessionmaker() as session:
            async with session.begin(): # Добавлен session.begin() для управления транзакцией
                await session.execute(update(Subscription).where(Subscription.user_id == user_id).values(is_warn=True))
            # await session.commit() # УДАЛЕНО - обрабатывается session.begin()

    async def check_crash_key_exists(self, crash_reporter_key: str) -> bool:
        """Проверяет, существует ли Subscription с данным crash_reporter_key глобально."""
        async with self.sessionmaker() as session:
            result = await session.scalar(
                select(Subscription.id).where(Subscription.crash_reporter_key == crash_reporter_key).limit(1)
            )
        return result is not None

    async def save_crash_key(self, crash_reporter_key: str, user_id: int):
        """Сохраняет crash_reporter_key. ВНИМАНИЕ: этот метод может быть избыточен с новой логикой create_or_reset_subscription"""
        async with self.sessionmaker() as session:
            async with session.begin(): 
                session.add(Subscription(
                    user_id=user_id,
                    crash_reporter_key=crash_reporter_key,
                    analysis_count=1, # Предполагаем, что сохранение ключа = первый анализ
                    date_start=datetime.now(),
                    # date_end нужно устанавливать осмысленно, если это активная подписка
                    date_end=datetime.now() + timedelta(days=30) # Пример: подписка на 30 дней
                ))
