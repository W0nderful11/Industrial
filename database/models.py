from datetime import datetime
from typing import Annotated, Optional
from decimal import Decimal
from sqlalchemy import Column, text, BigInteger, ForeignKey, DateTime, func, Boolean, String, Numeric, Index, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

intpk = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]
created_at_pk = Annotated[
    datetime, mapped_column(server_default=text("TIMEZONE('utc', now())"))]
updated_at_pk = Annotated[
    datetime, mapped_column(server_default=text("TIMEZONE('utc', now())"),
                            onupdate=text("TIMEZONE('utc', now())"))]


class Base(DeclarativeBase):
    __table_args__ = {'extend_existing': True}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index('ix_users_balance', 'balance'),
        Index('ix_users_role', 'role'),
        Index('ix_users_lang', 'lang'),
        Index('ix_user_id', 'user_id', postgresql_using='hash'),
        Index('ix_users_token_balance', 'token_balance')
    )
    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(nullable=True)
    fullname: Mapped[str] = mapped_column(nullable=True)
    affiliate: Mapped[str] = mapped_column(nullable=True)
    city: Mapped[str] = mapped_column(nullable=True)
    country: Mapped[str] = mapped_column(nullable=True)
    """
    guest: null in fullname, affiliate, city, phone_number
    no_access: have all datas. wait access from admin
    user: have all user privileges
    admin: have all privileges
    """
    role: Mapped[str] = mapped_column(String(20), default="guest")
    lang: Mapped[str] = mapped_column(default="ru")
    phone_number: Mapped[str] = mapped_column(nullable=True)
    referred_by: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), nullable=True)
    created_at: Mapped[created_at_pk]
    updated_at: Mapped[updated_at_pk]
    balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    token_balance: Mapped[int] = mapped_column(default=0, nullable=False)

    def get_null_columns(self):
        result = []
        if not self.fullname:
            result.append("fullname")
        if not self.affiliate:
            result.append("affiliate")
        if not self.city:
            result.append("city")
        if not self.country:
            result.append("country")
        if not self.phone_number:
            result.append("phone_number")
        result.append("lang")
        return result


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index('ix_subscriptions_user_id', 'user_id'),
        Index('ix_subscriptions_date_end', 'date_end'),
        Index('ix_subscriptions_product', 'product'),
        Index('uq_user_crash_reporter', 'user_id', 'crash_reporter_key', unique=True)
    )

    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product: Mapped[Optional[str]] = mapped_column(String(100))
    analysis_count: Mapped[int] = mapped_column(default=0, nullable=False)
    date_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    crash_reporter_key: Mapped[str] = mapped_column(String(255), nullable=False)
    date_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_warn: Mapped[bool] = mapped_column(Boolean, default=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index('ix_transactions_user_id', 'user_id'),
        Index('ix_transactions_timestamp', 'timestamp'),
    )
    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'topup', 'payment', 'refund'
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)  # Используем Python datetime
    admin_id: Mapped[Optional[int]] = mapped_column(BigInteger)


class CurrencyRate(Base):
    __tablename__ = "currency_rates"

    id: Mapped[intpk]
    country_code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    symbol: Mapped[str] = mapped_column(String(5), nullable=False)
    target_price_per_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[created_at_pk]
    updated_at: Mapped[updated_at_pk]


class RegionalPricing(Base):
    __tablename__ = "regional_pricing"
    __table_args__ = (
        Index('ix_regional_pricing_country_code', 'country_code', unique=True),
    )

    id: Mapped[intpk]
    country_code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)  # e.g., KZ, RU, US
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # e.g., KZT, RUB, USD
    symbol: Mapped[str] = mapped_column(String(5), nullable=False)  # e.g., ₸, ₽, $
    coefficient: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=1.00)  # Price coefficient
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False,
                                                   default=1.0000)  # Exchange rate to base currency (e.g., USD)


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"
    __table_args__ = (
        Index('ix_analysis_history_user_id', 'user_id'),
        Index('ix_analysis_history_created_at', 'created_at'),
        Index('ix_analysis_history_device_model', 'device_model'),
        Index('ix_analysis_history_file_type', 'file_type'),
        Index('ix_analysis_history_success', 'is_solution_found'),
    )

    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    
    # Информация об устройстве
    device_model: Mapped[Optional[str]] = mapped_column(String(100))  # iPhone 13, iPad Air
    ios_version: Mapped[Optional[str]] = mapped_column(String(50))   # iOS 15.4
    
    # Информация о файле
    original_filename: Mapped[Optional[str]] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # .ips, .txt, photo, .json
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)  # размер в байтах
    file_path: Mapped[Optional[str]] = mapped_column(String(500))  # путь к сохраненному файлу
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # SHA256 хеш файла для дедупликации
    
    # Результаты анализа
    error_code: Mapped[Optional[str]] = mapped_column(String(100))  # kernel_panic_0x8badf00d
    error_description: Mapped[Optional[str]] = mapped_column(Text)   # boot_loop, не определена
    solution_text: Mapped[Optional[str]] = mapped_column(Text)       # текст решения
    is_solution_found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Метаданные
    tokens_used: Mapped[int] = mapped_column(default=0, nullable=False)  # количество потраченных токенов
    created_at: Mapped[created_at_pk]
    
    # Повторные круги анализа
    repeat_attempts: Mapped[int] = mapped_column(default=0, nullable=False)  # количество кругов повторного анализа
    last_repeat_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # время последнего круга
    blocked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # заблокировано до
    
    # Связь с пользователем
    user: Mapped["User"] = relationship("User", back_populates="analysis_history")


# Добавляем связь к модели User
User.analysis_history = relationship("AnalysisHistory", back_populates="user", cascade="all, delete-orphan")