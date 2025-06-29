import asyncio
import logging
import os
import sys
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from dotenv import load_dotenv

# Абсолютный путь к корневой директории проекта
# Это делает скрипт запускаемым из любого места
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Загружаем переменные окружения из .env в корне проекта
dotenv_path = os.path.join(project_root, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    # Если .env не найден, пытаемся загрузить из env-dist
    dist_path = os.path.join(project_root, 'env-dist')
    if os.path.exists(dist_path):
        load_dotenv(dist_path)

# Импортируем наш конфигурационный класс
from config import Environ
from ios.database.models import User, Base

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Инициализируем окружение и получаем URL
try:
    settings = Environ()
    DB_URL = settings.asyncpg_url()
except Exception as e:
    logging.error(f"Не удалось загрузить конфигурацию. Убедитесь, что .env файл существует и настроен правильно. Ошибка: {e}")
    sys.exit(1)

if not DB_URL:
    logging.error("Не удалось сформировать DB_URL из конфигурации.")
    sys.exit(1)

engine = create_async_engine(DB_URL, echo=False)
session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def delete_guest_users():
    """
    Удаляет пользователей с ролью 'guest'.
    """
    async with session_maker() as session:
        async with session.begin():
            # Сначала посчитаем, сколько гостей будет удалено
            guest_count_stmt = select(func.count(User.id)).where(User.role == 'guest')
            guest_count_result = await session.execute(guest_count_stmt)
            guest_count = guest_count_result.scalar_one()

            if guest_count == 0:
                logging.info("Пользователи с ролью 'guest' не найдены. Очистка не требуется.")
                return

            logging.info(f"Найдено {guest_count} пользователей с ролью 'guest'. Начинаем удаление...")

            # Создаем и выполняем запрос на удаление
            stmt = delete(User).where(User.role == 'guest')
            result = await session.execute(stmt)
            deleted_count = result.rowcount

            logging.info(f"Успешно удалено {deleted_count} пользователей с ролью 'guest'.")

    await engine.dispose()


if __name__ == "__main__":
    logging.info("Запускаем скрипт очистки пользователей-гостей...")
    try:
        asyncio.run(delete_guest_users())
        logging.info("Скрипт успешно завершил работу.")
    except Exception as e:
        logging.error(f"Произошла ошибка во время выполнения скрипта: {e}", exc_info=True) 