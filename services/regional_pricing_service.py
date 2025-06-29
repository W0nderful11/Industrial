import pandas as pd
import logging
from decimal import Decimal
from database.database import ORM  # Предполагаем ORM
import zipfile

logger = logging.getLogger(__name__)
DEFAULT_EXCEL_PATH = "data/regional_prices.xlsx"


def read_pricing_from_excel(file_path: str = DEFAULT_EXCEL_PATH) -> list:
    """Читает данные о региональных ценах из Excel файла."""
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
        # Проверяем наличие необходимых колонок
        required_columns = ['country_code', 'currency', 'symbol', 'coefficient']
        if not all(col in df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in df.columns]
            logger.error(f"Excel file {file_path} is missing required columns: {missing}")
            return []

        # Преобразуем в список словарей, обрабатывая возможные NaN
        # Заполняем NaN значениями по умолчанию или пропускаем строки
        df = df.dropna(subset=required_columns)  # Пропускаем строки, где не хватает ключевых данных
        # Преобразуем coefficient в Decimal
        df['coefficient'] = df['coefficient'].apply(lambda x: Decimal(str(x)) if pd.notna(x) else Decimal('1.0'))
        pricing_data = df[required_columns].to_dict('records')
        logger.info(f"Successfully read {len(pricing_data)} records from {file_path}")
        return pricing_data
    except FileNotFoundError:
        logger.error(f"Regional pricing Excel file not found at {file_path}")
        return []
    except zipfile.BadZipFile:
        logger.error(f"Failed to read {file_path}. The file is corrupted or not a valid Excel (.xlsx) file.")
        return []
    except Exception as e:
        logger.error(f"Error reading or processing Excel file {file_path}: {e}", exc_info=True)
        return []


async def load_regional_pricing_to_db(orm: ORM, file_path: str = DEFAULT_EXCEL_PATH):
    """Загружает региональные цены из Excel в базу данных."""
    logger.info(f"Starting regional pricing load from {file_path}...")
    pricing_data = read_pricing_from_excel(file_path)

    if pricing_data:
        if hasattr(orm, 'regional_pricing_repo') and orm.regional_pricing_repo:
            # Опционально: очистить старые данные перед загрузкой новых
            # await orm.regional_pricing_repo.clear_pricing()
            await orm.regional_pricing_repo.update_pricing_from_list(pricing_data)
            logger.info(f"Finished loading {len(pricing_data)} regional pricing records to DB.")
        else:
            logger.error("ORM object does not have 'regional_pricing_repo' initialized.")
    else:
        logger.warning("No regional pricing data read from Excel, database not updated.")
