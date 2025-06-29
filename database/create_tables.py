"""
Создание таблицы analysis_history для хранения истории анализов пользователей
"""

import sys
import os
import asyncio
from pathlib import Path

# Добавляем корневую директорию в путь
current_dir = Path(__file__).parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

from database.database import ORM
from database.models import Base

async def create_tables():
    """Создать все таблицы"""
    orm = ORM()
    try:
        # Инициализируем репозитории для создания движка
        await orm.create_repos()
        
        if not orm.engine:
            print("Ошибка: не удалось создать движок базы данных")
            return
        
        # Создаем все таблицы
        print("Создание всех таблиц...")
        async with orm.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Все таблицы успешно созданы!")
        
    except Exception as e:
        print(f"Ошибка при создании таблиц: {e}")
        raise
    finally:
        if orm.engine:
            await orm.engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_tables())
