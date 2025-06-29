from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from database.models import CurrencyRate
from database.repo.repo import Repo

class CurrencyRepo(Repo):
    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def get_rate(self, country_code: str) -> CurrencyRate:
        async with self.sessionmaker() as session:
            query = select(CurrencyRate).filter_by(country_code=country_code)
            return await session.scalar(query)

    async def set_rate(self, country_code: str, currency: str, symbol: str, target_price: Decimal) -> CurrencyRate:
        async with self.sessionmaker() as session:
            async with session.begin():
                rate = await session.scalar(select(CurrencyRate).filter_by(country_code=country_code))
                if rate:
                    rate.currency = currency
                    rate.symbol = symbol
                    rate.target_price_per_usd = target_price
                else:
                    rate = CurrencyRate(
                        country_code=country_code,
                        currency=currency,
                        symbol=symbol,
                        target_price_per_usd=target_price
                    )
                    session.add(rate)
                await session.commit()
                return rate

    async def get_all_rates(self) -> list[CurrencyRate]:
        async with self.sessionmaker() as session:
            query = select(CurrencyRate)
            result = await session.scalars(query)
            return result.all()

    async def convert_price(self, amount: Decimal, from_country: str, to_country: str) -> Decimal:
        async with self.sessionmaker() as session:
            from_rate = await session.scalar(select(CurrencyRate).filter_by(country_code=from_country))
            to_rate = await session.scalar(select(CurrencyRate).filter_by(country_code=to_country))
            
            if not from_rate or not to_rate:
                return amount
            
            return amount

    async def get_price_in_user_currency(self, base_price_usd: Decimal, country_code: str) -> tuple[Decimal, str]:
        """Рассчитывает цену в валюте пользователя, умножая базовую цену в USD на целевую цену за 1 USD.
        
        Args:
            base_price_usd: Базовая цена анализа в USD (например, из PRICE_PER_ANALYSIS).
            country_code: Код страны пользователя (US, KZ, RU).

        Returns:
            Кортеж (итоговая_цена_в_локальной_валюте, символ_валюты).
        """
        async with self.sessionmaker() as session:
            rate = await session.scalar(select(CurrencyRate).filter_by(country_code=country_code))
            
            if not rate or country_code == "US":
                return base_price_usd, "$"
            
            price = base_price_usd * rate.target_price_per_usd
            return price.quantize(Decimal('0.01')), rate.symbol 