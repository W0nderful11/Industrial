from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.dialects.postgresql import insert
from decimal import Decimal
import logging

from database.models import CurrencyRate, RegionalPricing # Импортируем обе модели
from database.repo.repo import Repo

logger = logging.getLogger(__name__)

class CurrencyRepo(Repo):
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def update_rates(self, rates: dict):
        """Обновляет курсы валют в таблицах CurrencyRate и RegionalPricing."""
        async with self.sessionmaker() as session:
            async with session.begin():
                updated_currencies = set()
                for currency_code, rate in rates.items():
                    try:
                        # Пытаемся обновить курс в RegionalPricing по коду валюты
                        # Это обновит exchange_rate для всех стран, использующих эту валюту
                        stmt_regional = (
                            update(RegionalPricing)
                            .where(RegionalPricing.currency == currency_code)
                            .values(exchange_rate=Decimal(str(rate)))
                        )
                        result_regional = await session.execute(stmt_regional)
                        if result_regional.rowcount > 0:
                            logger.info(f"Updated exchange_rate for {currency_code} in RegionalPricing ({result_regional.rowcount} rows)")

                        # Обновляем или вставляем курс в CurrencyRate (если он там нужен)
                        # Используем INSERT ... ON CONFLICT DO UPDATE (UPSERT)
                        # Ключ конфликта - currency (код валюты), т.к. он уникальный (или должен быть)
                        # Нужно будет создать UNIQUE constraint на колонку `currency` в модели CurrencyRate!
                        # stmt_currency = (
                        #     insert(CurrencyRate)
                        #     .values(currency=currency_code, target_price_per_usd=Decimal(str(rate)))
                        #     .on_conflict_do_update(
                        #         index_elements=['currency'], # Укажите имя вашего уникального индекса/констрейнта
                        #         set_=dict(target_price_per_usd=Decimal(str(rate)))
                        #     )
                        # )
                        # await session.execute(stmt_currency)
                        # logger.debug(f"Upserted rate for {currency_code} in CurrencyRate")
                        # updated_currencies.add(currency_code)

                    except Exception as e:
                        logger.error(f"Error updating rate for {currency_code}: {e}", exc_info=True)
                        # Не прерываем цикл, пытаемся обновить другие
            
            logger.info(f"Finished updating rates. Processed {len(rates)} currencies.")

    async def get_price_in_user_currency(self, amount_usd: Decimal, country_code: str) -> tuple[Decimal, str]:
        """Возвращает цену в валюте пользователя и символ валюты."""
        async with self.sessionmaker() as session:
            # Сначала получаем региональные настройки
            regional_info = await session.scalar(
                select(RegionalPricing)
                .where(RegionalPricing.country_code == country_code.upper())
            )
            
            if not regional_info:
                # Если для страны нет, берем дефолт (например, US)
                 regional_info = await session.scalar(
                    select(RegionalPricing)
                    .where(RegionalPricing.country_code == "US") # TODO: Сделать дефолт настраиваемым
                 )
                 if not regional_info:
                      logger.error(f"Default regional pricing (US) not found!")
                      return Decimal("0"), "USD" # Возвращаем 0 и USD в крайнем случае

            # Теперь используем данные из regional_info
            exchange_rate = regional_info.exchange_rate # Берем актуальный курс из regional_pricing
            coefficient = regional_info.coefficient
            currency_symbol = regional_info.symbol
            
            final_price = amount_usd * coefficient * exchange_rate
            return final_price, currency_symbol 