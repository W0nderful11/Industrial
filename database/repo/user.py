import os
from aiogram import Bot
from aiogram.types import Message
from sqlalchemy import select, update, delete, exists, func, and_, or_
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from typing import List, Optional, Dict, Any, Tuple
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from phonenumbers import parse, is_valid_number
from phonenumbers import NumberParseException
from dotenv import load_dotenv
from sqlalchemy import String

from database.models import User, Subscription, Transaction
from database.repo.repo import Repo
from database.repo.exceptions import InsufficientFundsError, UserNotFoundError

logger = logging.getLogger(__name__)
load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))


class UserRepo(Repo):
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def get_balance(self, user_id: int) -> Decimal:
        async with self.sessionmaker() as session:
            result = await session.scalar(select(User.balance).where(User.user_id == user_id))
            return result or Decimal('0.00')

    async def get_token_balance(self, user_id: int) -> int:
        """Возвращает баланс токенов пользователя."""
        async with self.sessionmaker() as session:
            result = await session.scalar(select(User.token_balance).where(User.user_id == user_id))
            return result or 0

    async def add_tokens(self, user_id: int, tokens_to_add: int, admin_id: Optional[int] = None, notify_user: bool = True, notification_text: Optional[str] = None) -> bool:
        """Добавляет указанное количество токенов пользователю и записывает транзакцию."""
        if tokens_to_add <= 0:
            logger.warning(f"Attempted to add non-positive tokens ({tokens_to_add}) for user {user_id}")
            return False
        async with self.sessionmaker() as session:
            async with session.begin():
                # Обновляем баланс пользователя
                result = await session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .values(token_balance=User.token_balance + tokens_to_add)
                    .returning(User.token_balance)
                )
                new_balance = result.scalar_one_or_none()

                if new_balance is None:
                    logger.error(f"User {user_id} not found when trying to add tokens.")
                    await session.rollback()  # Откат, если пользователя нет
                    return False
                else:
                    logger.info(f"Added {tokens_to_add} tokens to user {user_id}. New token balance: {new_balance}")
                    # Создаем запись о транзакции
                    transaction = Transaction(
                        user_id=user_id,
                        type='token_topup' if admin_id else 'token_bonus',  # Тип зависит от наличия admin_id
                        amount=tokens_to_add,
                        admin_id=admin_id  # Может быть None для автоматических начислений
                    )
                    session.add(transaction)
                    logger.info(
                        f"Transaction recorded for user {user_id}: type='{transaction.type}', amount={tokens_to_add}, admin={admin_id}")
                    # Коммит в конце with session.begin()
                    # await session.commit() # Убрано, т.к. автокоммит в конце begin()

                    # Отправка уведомления пользователю, если это указано
                    if notify_user:
                        try:
                            user_lang = await session.scalar(select(User.lang).where(User.user_id == user_id)) or "ru"
                            # Используем кастомный текст, если он передан, иначе — стандартный
                            if notification_text:
                                message_text = notification_text
                            else:
                                # TODO: Загрузить тексты из i18n или определить их здесь
                                if user_lang == "ru":
                                    message_text = f"Ваш счет пополнен на {tokens_to_add} токенов. Всего {new_balance} токенов."
                                else:  # Можно добавить другие языки или использовать английский по умолчанию
                                    message_text = f"Your account has been credited with {tokens_to_add} tokens. Total {new_balance} tokens."
                            await bot.send_message(chat_id=user_id, text=message_text)
                            logger.info(f"Sent token addition notification to user {user_id}")
                        except Exception as e:
                            logger.error(f"Failed to send token addition notification to user {user_id}: {e}")

                    return True

    async def deduct_token(self, user_id: int) -> bool:
        """Списывает 1 токен с баланса пользователя. Возвращает True если успешно, False если недостаточно токенов или ошибка."""
        async with self.sessionmaker() as session:
            async with session.begin():
                current_balance = await session.scalar(
                    select(User.token_balance).where(User.user_id == user_id)
                )

                # Perform deduction
                result = await session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .where(User.token_balance >= 1)  # Double check condition
                    .values(token_balance=User.token_balance - 1)
                    .returning(User.token_balance)
                )
                new_balance = result.scalar_one_or_none()
                return new_balance

    async def find_all(self) -> list[User]:
        async with self.sessionmaker() as session:
            query = select(User)
            result = await session.scalars(query)
            return result.all() or []

    async def find_user_by_user_id(self, user_id: int) -> Optional[User]:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(user_id=user_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def find_user_by_username(self, username) -> User:
        async with self.sessionmaker() as session:
            query = select(User).filter_by(username=username)
            return await session.scalar(query) or User()

    async def find_user_by_username_or_id(self, identifier: str) -> Optional[User]:
        """Ищет пользователя по ID (если строка - число) или по username (с @ или без)."""
        async with self.sessionmaker() as session:
            user = None
            if identifier.isdigit():
                user = await session.scalar(select(User).filter_by(user_id=int(identifier)))
            elif identifier.startswith('@'):
                user = await session.scalar(select(User).filter_by(username=identifier[1:]))
            else:
                user = await session.scalar(select(User).filter_by(username=identifier))

            if user:
                logger.info(f"User found by identifier '{identifier}': ID={user.user_id}, Username={user.username}")
            else:
                logger.info(f"User not found by identifier '{identifier}'.")
            return user

    async def create_user(self, user_id: int, **kwargs):
        """
        Создает нового пользователя. Используется для первоначального создания "гостя".
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                # Проверяем, существует ли пользователь, чтобы избежать дублирования
                existing_user = await session.scalar(select(User).filter_by(user_id=user_id))
                if existing_user:
                    return existing_user

                user = User(user_id=user_id, **kwargs)
                session.add(user)
            return user

    async def get_users_by_language(self, lang: str) -> List[User]:
        async with self.sessionmaker() as session:
            result = await session.scalars(
                select(User).where(User.lang == lang)
            )
            return result.all()

    @staticmethod
    def _validate_phone_number(number: str) -> bool:
        try:
            return is_valid_number(parse(number, None))
        except NumberParseException:
            return False

    async def upsert_user(self, user_id: int = None, **user_data):
        async with self.sessionmaker() as session:
            async with session.begin():  # Используем session.begin() для атомарности
                if user_id is not None:
                    user = await session.scalar(select(User).filter_by(user_id=user_id))
                    if user:
                        # Обновляем существующего пользователя
                        for key, value in user_data.items():
                            if hasattr(user, key):
                                setattr(user, key, value)
                        user.updated_at = datetime.utcnow()  # Обновляем время изменения
                    else:
                        # Создаем нового пользователя, если не найден
                        # Убедимся, что user_id включен в данные для нового пользователя
                        all_user_data = {"user_id": user_id, **user_data}
                        user = User(**all_user_data)
                        session.add(user)
                else:
                    # Этот случай (user_id is None) при инициализации админов не должен происходить,
                    # но если он для других целей, то user_id должен быть в user_data.
                    if "user_id" not in user_data or user_data["user_id"] is None:
                        # Это состояние не должно приводить к ошибке NOT NULL, 
                        # возможно, стоит выбросить исключение или логгировать серьезную ошибку,
                        # так как user_id является обязательным.
                        # Для сценария инициализации админов user_id всегда должен быть.
                        logging.error(
                            "Попытка создать пользователя без user_id через upsert_user, когда user_id не был передан явно.")
                        # Можно либо вернуть ошибку, либо создать с user_data как есть, если user_id там есть
                        if "user_id" in user_data:
                            user = User(**user_data)
                            session.add(user)
                        else:
                            # Предотвращаем ошибку NOT NULL
                            raise ValueError("user_id должен быть предоставлен для создания нового пользователя")
                    else:
                        user = User(**user_data)
                        session.add(user)

                # await session.commit() # Commit будет выполнен контекстным менеджером session.begin()
            return user  # Возвращаем пользователя после коммита

    async def delete_user(self, user_id: int) -> bool:
        async with self.sessionmaker() as session:
            # Correctly fetch the user by the 'user_id' (Telegram ID) column
            result = await session.execute(select(User).where(User.user_id == user_id))
            user_to_delete = result.scalar_one_or_none()

            if user_to_delete:
                # Now, delete the object through the session
                # This will trigger the cascade delete for related analysis_history
                await session.delete(user_to_delete)
                await session.commit()
                logging.info(f"User with user_id {user_id} and their analysis history have been deleted.")
                return True
            else:
                logging.warning(f"Attempted to delete non-existent user with user_id {user_id}")
                return False

    async def get_admins(self) -> List[User]:
        async with self.sessionmaker() as session:
            result = await session.scalars(
                select(User).where(User.role == 'admin')
            )
            return result.all()

    async def get_user(self, user_id: int):
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(
                    User.user_id,
                    User.balance,
                    User.role
                ).where(User.user_id == user_id)
            )

        return result.first()

    async def get_or_create_user(
            self,
            user_id: int,
            fullname: Optional[str] = None,
            username: Optional[str] = None,
            lang: str = "ru",
            role: str = "user",
            affiliate: Optional[str] = None,
            city: Optional[str] = None,
            country: Optional[str] = None,
            phone_number: Optional[str] = None,
            token_balance: int = 0,
            # balance: Decimal = Decimal("0.00") # Оставим возможность передавать, но установим дефолт ниже
    ) -> Tuple[User, bool]:
        async with self.sessionmaker() as session:
            created = False
            # Преобразуем user_id к int, если это строка (на всякий случай)
            user_id_int = int(user_id)

            user = await session.scalar(
                select(User).where(User.user_id == user_id_int)
            )

            if not user:
                created = True
                user_data = {
                    "user_id": user_id_int,
                    "fullname": fullname,
                    "username": username,
                    "lang": lang,
                    "role": role,  # Начальная роль
                    "affiliate": affiliate,
                    "city": city,
                    "country": country,
                    "phone_number": phone_number,
                    "token_balance": token_balance,
                    "balance": Decimal("0.00")  # Устанавливаем денежный баланс по умолчанию
                }
                user = User(**user_data)
                session.add(user)
                await session.flush()  # Чтобы user.id был доступен и для обновления роли ниже
            else:
                # Обновляем данные существующего пользователя, если они переданы
                if fullname is not None and user.fullname != fullname:
                    user.fullname = fullname
                if username is not None and user.username != username:
                    user.username = username
                if lang is not None and user.lang != lang:
                    user.lang = lang
                if affiliate is not None and user.affiliate != affiliate:
                    user.affiliate = affiliate
                if city is not None and user.city != city:
                    user.city = city
                if country is not None and user.country != country:
                    user.country = country
                if phone_number is not None and user.phone_number != phone_number:
                    user.phone_number = phone_number
                user.updated_at = datetime.utcnow()

            # Проверка и обновление роли, если пользователь в списке ADMINS из .env
            admin_ids_str = os.getenv("ADMINS", "").split(',')
            env_admin_ids = {int(admin_id.strip()) for admin_id in admin_ids_str if admin_id.strip().isdigit()}

            if user.user_id in env_admin_ids and user.role != 'admin':
                logger.info(f"User {user.user_id} is in ENV ADMINS. Updating role to 'admin'.")
                user.role = 'admin'

            # Если пользователь не в env_admin_ids, но текущая роль admin - не меняем, 
            # это могло быть установлено вручную или другим механизмом.
            # Если только создается и не админ из env, роль уже установлена (user по умолчанию или из kwargs)

            await session.commit()
            return user, created

    async def user_exists(self, user_id: int) -> bool:
        async with self.sessionmaker() as session:
            stmt = select(exists().where(User.user_id == user_id))
            return await session.scalar(stmt)

    async def get_balance_changes(
            self,
            user_id: int,
            start_date: datetime,
            end_date: datetime
    ) -> dict:
        """Возвращает изменения баланса за период"""
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(
                    Transaction.type,
                    sum(Transaction.amount).label("total")
                )
                .where(Transaction.user_id == user_id)
                .where(Transaction.timestamp.between(start_date, end_date))
                .group_by(Transaction.type)
            )
            return {row[0]: float(row[1]) for row in result.all()}

    async def admin_update_balance(self, admin_id: int, user_id: int, amount: Decimal) -> bool:
        """
        Упрощенное пополнение баланса администратором
        Возвращает True если успешно, False если ошибка
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                # Проверяем что администратор существует и имеет права
                admin = await session.get(User, admin_id)
                if not admin or admin.role != 'admin':
                    return False

                # Обновляем баланс одним запросом
                result = await session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .values(balance=User.balance + amount)
                    .returning(User.balance)
                )

                if not result.scalar_one_or_none():
                    raise UserNotFoundError()

                return True

    async def quick_topup(self, user_id: int, amount: Decimal) -> bool:
        """
        Максимально упрощенное пополнение баланса
        Без проверок прав, только базовые проверки
        """
        async with self.sessionmaker() as session:
            try:
                await session.execute(
                    update(User)
                    .where(User.user_id == user_id)
                    .values(balance=User.balance + amount)
                )
                await session.commit()
                return True
            except:
                await session.rollback()
                return False

    async def update_alance(
            self,
            user_id: int,
            amount: Decimal,
            admin_id: Optional[int] = None,
            transaction_type: str = "manual"
    ) -> None:
        """
        Обновление баланса с проверкой прав и созданием транзакции
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                # Проверка прав администратора
                if admin_id:
                    # Ищем админа по user_id (Telegram ID)
                    admin_result = await session.execute(select(User).where(User.user_id == admin_id))
                    admin = admin_result.scalar_one_or_none()
                    if not admin or admin.role != 'admin':
                        raise PermissionError("Admin rights required")

                # Блокировка строки пользователя
                user = await session.execute(
                    select(User)
                    .where(User.user_id == user_id)
                    .with_for_update()
                )
                user = user.scalar_one_or_none()

                if not user:
                    raise UserNotFoundError()

                # Проверка типа данных
                if not isinstance(amount, Decimal):
                    raise TypeError("Amount must be Decimal")

                # Обновление баланса
                new_balance = user.balance + amount
                if new_balance < Decimal('0'):
                    raise InsufficientFundsError("Negative balance not allowed")

                user.balance = new_balance

                # Логирование транзакции
                transaction = Transaction(
                    user_id=user_id,
                    type=transaction_type,
                    amount=amount,
                    admin_id=admin_id
                )
                session.add(transaction)

    async def deduct_funds(
            self,
            user_id: int,
            amount: Decimal,
            description: str
    ) -> None:
        """
        Списание средств с баланса
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                user = await session.get(User, user_id, with_for_update=True)

                if user.balance < amount:
                    raise InsufficientFundsError(
                        f"Insufficient funds. Balance: {user.balance}, Required: {amount}"
                    )

                user.balance -= amount

                transaction = Transaction(
                    user_id=user_id,
                    type="payment",
                    amount=-amount,
                    description=description
                )
                session.add(transaction)

    async def add_funds(
            self,
            user_id: int,
            amount: Decimal,
            description: str,
            admin_id: Optional[int] = None
    ) -> None:
        """
        Пополнение баланса
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                user = await session.get(User, user_id, with_for_update=True)
                user.balance += amount

                transaction = Transaction(
                    user_id=user_id,
                    type="topup",
                    amount=amount,
                    admin_id=admin_id,
                    description=description
                )
                session.add(transaction)

    async def get_country_code(self, user_id: int) -> str:
        async with self.sessionmaker() as session:
            user = await session.scalar(select(User.country).where(User.user_id == user_id))
            if not user:
                logger.warning(f"Не удалось получить страну для пользователя {user_id}. Возвращаем US.")
                return "US"
            country = user.strip().upper()
            logger.info(f"Определена страна для пользователя {user_id}: '{country}'")  # Логируем полученную страну
            # Добавляем больше вариантов для России и Казахстана
            if country in ["КАЗАХСТАН", "KAZAKHSTAN", "KZ", "КЗ"]:
                logger.info(f"Страна определена как KZ.")
                return "KZ"
            if country in ["РОССИЯ", "RUSSIA", "RU", "РФ", "RUSSIAN FEDERATION"]:
                logger.info(f"Страна определена как RU.")
                return "RU"

            # Если не KZ или RU, возвращаем US как дефолт
            logger.warning(f"Страна '{country}' не распознана как KZ или RU. Возвращаем US.")
            return "US"

    async def deduct_tokens(self, user_id: int, tokens_to_deduct: int, admin_id: int = None) -> bool:
        """Списывает токены с баланса пользователя."""
        if tokens_to_deduct <= 0:
            logger.warning(f"Попытка списания не положительного числа токенов: {tokens_to_deduct}")
            return False

        async with self.sessionmaker() as session:
            async with session.begin():
                # Блокируем строку пользователя
                user_result = await session.execute(
                    select(User).where(User.user_id == user_id).with_for_update()
                )
                user = user_result.scalar_one_or_none()

                if not user:
                    logger.warning(f"Попытка списать токены у несуществующего пользователя {user_id}")
                    return False

                if user.token_balance < tokens_to_deduct:
                    logger.warning(
                        f"Недостаточно токенов ({user.token_balance}) для списания {tokens_to_deduct} у пользователя {user_id}")
                    return False

                user.token_balance -= tokens_to_deduct
                session.add(user)
                await session.flush()  # Применяем изменения

                # Записываем транзакцию списания
                transaction_data = {
                    'user_id': user.id,
                    'amount': Decimal(tokens_to_deduct),
                    'type': 'token_deduction',  # Используем поле 'type' вместо 'transaction_type'
                    'admin_id': admin_id,  # ID админа, который выполнил списание
                    'timestamp': datetime.utcnow()  # Добавляем timestamp
                }
                new_transaction = Transaction(**transaction_data)
                session.add(new_transaction)
                await session.flush()
                logger.info(
                    f"Списано {tokens_to_deduct} токенов у пользователя {user_id}. Новый баланс: {user.token_balance}. Админ: {admin_id}")

                # Отправка уведомления пользователю
                try:
                    # user_lang уже должен быть доступен из объекта user, если поле lang есть в модели User
                    # Если нет, то нужен запрос: user_lang = await session.scalar(select(User.lang).where(User.user_id == user_id)) or "ru"
                    user_lang = user.lang if hasattr(user, 'lang') and user.lang else "ru"
                    # TODO: Загрузить тексты из i18n или определить их здесь
                    if user_lang == "ru":
                        message_text = f"С вашего счета сняли {tokens_to_deduct} токенов. Всего {user.token_balance} токенов."
                    else:
                        message_text = f"{tokens_to_deduct} tokens have been deducted from your account. Total {user.token_balance} tokens."
                    await bot.send_message(chat_id=user_id, text=message_text)
                    logger.info(f"Sent token deduction notification to user {user_id} for {tokens_to_deduct} tokens.")
                except Exception as e:
                    logger.error(f"Failed to send token deduction notification to user {user_id}: {e}")

                return True

    async def update_balance(self, user_id: int, amount: Decimal) -> bool:
        """Обновляет баланс пользователя."""
        async with self.sessionmaker() as session:
            async with session.begin():
                stmt = update(
                    User
                ).where(
                    User.user_id == user_id
                )

                user = await session.get(User, user_id, with_for_update=True)

                user.balance += amount
                await session.commit()
                return True

    async def get_total_user_count(self) -> Optional[int]:
        async with self.sessionmaker() as session:
            result = await session.execute(select(func.count(User.id)))
            return result.scalar_one_or_none()

    async def get_paged_users(self, page: int = 0, limit: int = 10) -> Tuple[List[User], int]:
        """
        Возвращает список пользователей с пагинацией.
        """
        async with self.sessionmaker() as session:
            count_query = select(func.count(User.id))
            total_items = await session.scalar(count_query)
            total_pages = (total_items + limit - 1) // limit if total_items else 0

            query = select(User).order_by(User.id).offset(page * limit).limit(limit)
            result = await session.scalars(query)
            users = result.all()
            
            return users, total_pages

    async def search_users(self, query: str, page: int = 0, limit: int = 10) -> Tuple[List[User], int]:
        """
        Ищет пользователей по ID, имени пользователя или полному имени.
        Поддерживает пагинацию.
        Возвращает список пользователей и общее количество страниц.
        """
        async with self.sessionmaker() as session:
            # Строим запрос на поиск
            search_query = select(User).where(
                or_(
                    User.user_id.cast(String).ilike(f"%{query}%"),
                    User.username.ilike(f"%{query}%"),
                    User.fullname.ilike(f"%{query}%")
                )
            ).order_by(User.id)

            # Получаем общее количество совпадающих пользователей для пагинации
            count_query = select(func.count()).select_from(search_query.alias())
            total_items = await session.scalar(count_query)
            total_pages = (total_items + limit - 1) // limit if total_items else 0

            # Применяем пагинацию
            paginated_query = search_query.offset(page * limit).limit(limit)
            result = await session.scalars(paginated_query)
            users = result.all()
            
            return users, total_pages

    async def get_all_user_ids(self) -> Optional[List[int]]:
        async with self.sessionmaker() as session:
            result = await session.scalars(select(User.user_id))
            return result.all()

    async def get_active_subscription(self, user_id: int, crash_reporter_key: str) -> Optional[Subscription]:
        """
        Проверяет наличие активной подписки для пользователя по crash_reporter_key.
        Подписка считается активной, если текущая дата меньше date_end и analysis_count > 0.
        """
        async with self.sessionmaker() as session:
            now = datetime.now()
            result = await session.execute(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.crash_reporter_key == crash_reporter_key,
                    Subscription.date_end > now,
                    Subscription.analysis_count > 0
                )
            )
            return result.scalar_one_or_none()

    async def find_subscription_fuzzy(
            self, user_id: int, crash_key_prefix: str
    ) -> Optional[Subscription]:
        """
        Ищет активную подписку по префиксу crash_reporter_key.
        """
        async with self.sessionmaker() as session:
            now = datetime.now()
            # 1. Получаем все активные подписки пользователя
            active_subs_result = await session.execute(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.date_end > now,
                    Subscription.analysis_count > 0
                )
            )
            active_subs = active_subs_result.scalars().all()

            # 2. Ищем совпадение по префиксу в Python
            for sub in active_subs:
                if sub.crash_reporter_key and sub.crash_reporter_key.startswith(crash_key_prefix):
                    logger.info(f"Fuzzy match found for user {user_id}: prefix {crash_key_prefix} matched sub key {sub.crash_reporter_key}")
                    return sub
            
            return None

    async def create_or_update_subscription(
        self,
        user_id: int,
        crash_reporter_key: str,
        product: str,
        duration_days: int = 30,
        analysis_limit: int = 10
    ) -> Subscription:
        """
        Создает новую или обновляет существующую подписку, сбрасывая ее срок действия и количество анализов.
        """
        async with self.sessionmaker() as session:
            async with session.begin():
                # Попробуем найти существующую подписку по уникальному ключу
                existing_sub = await session.scalar(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.crash_reporter_key == crash_reporter_key
                    )
                )

                now = datetime.now()
                end_date = now + timedelta(days=duration_days)

                if existing_sub:
                    # Если подписка найдена, обновляем ее
                    existing_sub.date_start = now
                    existing_sub.date_end = end_date
                    existing_sub.analysis_count = analysis_limit
                    existing_sub.product = product
                    existing_sub.is_warn = False
                    logger.info(
                        f"Updated subscription for user {user_id}, key {crash_reporter_key}. "
                        f"New end date: {end_date}, analyses: {analysis_limit}"
                    )
                    return existing_sub
                else:
                    # Если подписка не найдена, создаем новую
                    new_sub = Subscription(
                        user_id=user_id,
                        crash_reporter_key=crash_reporter_key,
                        product=product,
                        analysis_count=analysis_limit,
                        date_start=now,
                        date_end=end_date,
                        is_warn=False
                    )
                    session.add(new_sub)
                    logger.info(
                        f"New subscription created for user {user_id}, key {crash_reporter_key}. "
                        f"End date: {end_date}, analyses: {analysis_limit}"
                    )
                    return new_sub

    async def decrement_subscription_analysis_count(self, user_id: int, crash_reporter_key: str) -> Optional[Subscription]:
        """Уменьшает счетчик доступных анализов для подписки на 1."""
        async with self.sessionmaker() as session:
            async with session.begin():
                # Сначала найдем подписку, чтобы убедиться, что она активна и есть что уменьшать
                stmt_select = (
                    select(Subscription)
                    .where(Subscription.user_id == user_id)
                    .where(Subscription.crash_reporter_key == crash_reporter_key)
                    .where(Subscription.date_end > datetime.utcnow())
                    .where(Subscription.analysis_count > 0)
                )
                subscription = await session.scalar(stmt_select)

                if subscription:
                    # Если нашли активную подписку с доступными анализами, уменьшаем счетчик
                    # Используем прямой update для атомарности и эффективности
                    stmt_update = (
                        update(Subscription)
                        .where(Subscription.id == subscription.id) # Обновляем по ID
                        .where(Subscription.analysis_count > 0) # Доп. проверка на всякий случай
                        .values(analysis_count=Subscription.analysis_count - 1)
                        .returning(Subscription.analysis_count) # Возвращаем новый счетчик
                    )
                    result = await session.execute(stmt_update)
                    new_count = result.scalar_one_or_none()
                    
                    if new_count is not None: # Если обновление прошло успешно
                        logger.info(f"Decremented analysis_count for user {user_id}, key {crash_reporter_key}. New count: {new_count}")
                        # Обновим объект subscription перед возвратом
                        subscription.analysis_count = new_count
                        return subscription
                    else:
                        # Этого не должно произойти, если select выше нашел подписку с analysis_count > 0
                        logger.error(f"Failed to decrement analysis_count for user {user_id}, key {crash_reporter_key}, though it seemed active.")
                        return None 
                else:
                    logger.warning(f"Could not decrement analysis_count for user {user_id}, key {crash_reporter_key}. Subscription not found, not active, or count is zero.")
                    return None

    async def get_users_created_after(self, date_from: datetime, role: str = None, token_balance: int = None) -> List[User]:
        """
        Возвращает список пользователей, созданных после указанной даты,
        с возможностью фильтрации по роли и балансу токенов.
        """
        async with self.sessionmaker() as session:
            query = select(User).where(User.created_at >= date_from)

            if role is not None:
                query = query.where(User.role == role)

            if token_balance is not None:
                query = query.where(User.token_balance == token_balance)

            result = await session.scalars(query)
            return result.all()

    async def get_all_users(self):
        async with self.sessionmaker() as session:
            result = await session.scalars(select(User))
            return result.all()
