import logging
import httpx
from decimal import Decimal
from database.database import ORM  # Предполагаем, что ORM инициализируется где-то и передается

logger = logging.getLogger(__name__)
API_URL = "https://open.er-api.com/v6/latest/USD"  # Базовая валюта USD


async def fetch_latest_rates() -> dict:
    """Получает последние курсы валют с API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(API_URL)
            response.raise_for_status()  # Вызовет исключение для HTTP ошибок 4xx/5xx
            data = response.json()
            if data.get("result") == "success":
                logger.info(f"Successfully fetched rates. Last update: {data.get('time_last_update_utc')}")
                return data.get("rates", {})
            else:
                logger.error(f"API request was not successful: {data}")
                return {}
    except httpx.RequestError as e:
        logger.error(f"Error fetching exchange rates: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error fetching or parsing rates: {e}", exc_info=True)
        return {}


async def update_database_rates(orm: ORM):
    """Получает свежие курсы и обновляет их в базе данных."""
    logger.info("Starting daily rates update...")
    rates = await fetch_latest_rates()
    if rates:
        # Убедимся, что orm.currency_repo существует
        if hasattr(orm, 'currency_repo') and orm.currency_repo:
            await orm.currency_repo.update_rates(rates)
        else:
            logger.error("ORM object does not have 'currency_repo' initialized.")
    else:
        logger.warning("No rates fetched, database not updated.")


