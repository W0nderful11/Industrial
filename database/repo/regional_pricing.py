from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.future import select
from decimal import Decimal
from typing import Optional, Dict, Any

from database.models import RegionalPricing
from database.repo.repo import Repo

class RegionalPricingRepo(Repo):
    def __init__(self, sessionmaker: async_sessionmaker):
        super().__init__(sessionmaker)

    async def get_pricing_by_country(self, country_code: str) -> Optional[Dict[str, Any]]:
        """Получает конфигурацию цен для указанного кода страны."""
        query = select(RegionalPricing).where(RegionalPricing.country_code == country_code.upper())
        async with self.sessionmaker() as session:
            result = await session.execute(query)
            pricing = result.scalar_one_or_none()
            if pricing:
                return {
                    "currency": pricing.currency,
                    "symbol": pricing.symbol,
                    "coefficient": pricing.coefficient,
                    "exchange_rate": pricing.exchange_rate
                }
            return None

    async def get_default_pricing(self) -> Dict[str, Any]:
        """Получает конфигурацию цен по умолчанию (например, для USD)."""
        # Предполагаем, что "DEFAULT" или "US" является ключом по умолчанию
        # Попробуем сначала US, потом можно добавить явный DEFAULT, если нужно
        default_pricing = await self.get_pricing_by_country("US") 
        if default_pricing:
            return default_pricing
        else:
            # Возвращаем абсолютный минимум, если даже US не найден
             return {
                "currency": "USD",
                "symbol": "$",
                "coefficient": Decimal("1.00"),
                "exchange_rate": Decimal("1.0000")
            }

    # Можно добавить методы add/update/delete, если нужно будет управлять ценами через бота 