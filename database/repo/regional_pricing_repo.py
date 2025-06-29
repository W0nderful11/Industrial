from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.dialects.postgresql import insert
from decimal import Decimal
import logging

from database.models import RegionalPricing
from database.repo.repo import Repo

logger = logging.getLogger(__name__)

class RegionalPricingRepo(Repo):
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def clear_pricing(self):
        """Очищает всю таблицу региональных цен."""
        async with self.sessionmaker() as session:
            async with session.begin():
                await session.execute(delete(RegionalPricing))
                logger.info("Cleared all regional pricing data.")

    async def update_pricing_from_list(self, pricing_data: list):
        """Обновляет/вставляет данные о ценах из списка словарей."""
        async with self.sessionmaker() as session:
            async with session.begin():
                for record in pricing_data:
                    # Используем INSERT ... ON CONFLICT DO UPDATE (UPSERT)
                    # Ключ конфликта - country_code, т.к. он уникальный
                    stmt = (
                        insert(RegionalPricing)
                        .values(**record) # Передаем весь словарь
                        .on_conflict_do_update(
                            index_elements=['country_code'], 
                            set_=record # Обновляем все поля из словаря при конфликте
                        )
                    )
                    await session.execute(stmt)
                logger.info(f"Upserted {len(pricing_data)} regional pricing records.")

    async def get_pricing_by_country(self, country_code: str) -> dict | None:
        """Возвращает словарь с данными о ценах для указанной страны."""
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(RegionalPricing).where(RegionalPricing.country_code == country_code.upper())
            )
            row = result.scalar_one_or_none()
            if row:
                # Преобразуем объект SQLAlchemy в словарь для удобства
                return {
                    "country_code": row.country_code,
                    "currency": row.currency,
                    "symbol": row.symbol,
                    "coefficient": row.coefficient,
                    "exchange_rate": row.exchange_rate
                }
            return None
            
    async def get_default_pricing(self) -> dict | None:
         """Возвращает дефолтные настройки цен (например, для US)."""
         # TODO: Сделать код дефолтной страны настраиваемым
         return await self.get_pricing_by_country("US") 