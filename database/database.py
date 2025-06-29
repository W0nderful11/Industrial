"""Database ORM module for managing PostgreSQL connections and repositories."""
import logging
import sys
from typing import Optional

from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from config import Environ
from database.models import Base, User
from database.repo.subscription import SubscriptionRepo
from database.repo.transactions import TransactionRepo
from database.repo.user import UserRepo
from database.repo.currency_repo import CurrencyRepo
from database.repo.regional_pricing_repo import RegionalPricingRepo
from database.repo.analysis_history import AnalysisHistoryRepo

# Настраиваем логирование
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


# pylint: disable=too-many-instance-attributes
class ORM:
    """Database ORM class for managing connections and repositories."""

    def __init__(self):
        """Initialize ORM with environment settings and setup engine."""
        self.settings = Environ()
        self.user_repo: Optional[UserRepo] = None
        self.subscription_repo: Optional[SubscriptionRepo] = None
        self.transactions: Optional[TransactionRepo] = None
        self.currency_repo: Optional[CurrencyRepo] = None
        self.regional_pricing_repo: Optional[RegionalPricingRepo] = None
        self.analysis_history_repo: Optional[AnalysisHistoryRepo] = None
        self.async_sessionmaker: Optional[async_sessionmaker] = None
        self.engine = None
        self.session_maker = None

        self._setup_engine()

    def _setup_engine(self):
        """Setup async database engine and sessionmaker."""
        # Унифицируем создание движка, чтобы везде был асинхронный
        # Это решает проблему с NullPool, который приводил к утечке соединений
        db_url = self.settings.asyncpg_url()
        self.engine = create_async_engine(db_url, echo=False)
        self.async_sessionmaker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            autoflush=False
        )

    async def get_async_engine(self, echo=False):
        """Get async engine with optional echo parameter."""
        # Создаем новый движок если нужен другой echo
        if echo:
            return create_async_engine(self.settings.asyncpg_url(), echo=echo)
        return self.engine

    def get_engine(self, echo=False):
        """Get synchronous engine for create_tables operations."""
        # Синхронный движок для create_tables
        return create_engine(
            f"postgresql://{self.settings.user}:{self.settings.password}@"
            f"{self.settings.host}:{self.settings.port}/{self.settings.dbname}",
            echo=echo
        )

    def create_tables(self, with_drop=False, echo: bool = False):
        """Create database tables with optional drop and user backup."""
        env = Environ()
        engine = create_engine(
            f"postgresql://{env.user}:{env.password}@"
            f"{env.host}:{env.port}/{env.dbname}",
            echo=echo
        )
        if with_drop:
            logger.info("Starting table recreation with user backup.")

            # 1. Резервное копирование пользователей
            users_backup = []
            inspector = inspect(engine)
            if inspector.has_table(User.__tablename__):
                try:
                    with sessionmaker(bind=engine)() as session:
                        users = session.query(User).all()
                        for user in users:
                            user_data = {
                                c.name: getattr(user, c.name)
                                for c in user.__table__.columns
                            }
                            users_backup.append(user_data)
                        logger.info("Backed up %d users.", len(users_backup))
                except SQLAlchemyError as e:
                    logger.error("Error backing up users: %s", e)

            # 2. Удаление и создание таблиц
            try:
                Base.metadata.drop_all(engine)
                logger.info("All tables dropped.")
                Base.metadata.create_all(engine)
                logger.info("All tables created.")
            except SQLAlchemyError as e:
                logger.error("Error dropping/creating tables: %s", e)
                return

            # 3. Восстановление пользователей
            if users_backup:
                try:
                    with sessionmaker(bind=engine)() as session:
                        # Простое восстановление пользователей
                        for user_data in users_backup:
                            user = User(**user_data)
                            session.add(user)
                        session.commit()
                    logger.info("Restored %d users.", len(users_backup))
                except SQLAlchemyError as e:
                    logger.error("Error restoring users: %s", e)
        else:
            # Обычное создание таблиц без удаления
            Base.metadata.create_all(engine)
            logger.info("Tables checked/created without dropping.")

    def create_metadata(self):
        """Create database metadata using synchronous engine."""
        # Используем синхронный движок для создания метаданных
        sync_engine = self.get_engine()
        Base.metadata.create_all(sync_engine)
        logger.info("Tables metadata created.")

    async def init_currencies(self):
        """Initialize currencies in database."""
        if not self.async_sessionmaker:
            logger.error(
                "Session maker not initialized for currency initialization."
            )
            return

        # Простая инициализация без специальных методов
        logger.info("Currency initialization skipped - using default values")

    async def get_async_sessionmaker(self) -> async_sessionmaker:
        """Get async sessionmaker, creating if necessary."""
        if not self.async_sessionmaker:
            async_engine = await self.get_async_engine()
            self.async_sessionmaker = async_sessionmaker(
                async_engine, expire_on_commit=False
            )
        return self.async_sessionmaker

    async def create_repos(self):
        """Create all repository instances with async sessionmaker."""
        # Движок и фабрика сессий уже созданы в _setup_engine
        if not self.async_sessionmaker:
            self._setup_engine()

        if self.async_sessionmaker:
            # Создаем репозитории
            self.user_repo = UserRepo(self.async_sessionmaker)
            self.subscription_repo = SubscriptionRepo(self.async_sessionmaker)
            self.transactions = TransactionRepo(self.async_sessionmaker)
            self.currency_repo = CurrencyRepo(self.async_sessionmaker)
            self.regional_pricing_repo = RegionalPricingRepo(
                self.async_sessionmaker
            )
            self.analysis_history_repo = AnalysisHistoryRepo(
                self.async_sessionmaker
            )
        else:
            logger.error(
                "Failed to create repositories: async_sessionmaker is None"
            )
