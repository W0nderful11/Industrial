#!/usr/bin/env python3
"""
Скрипт для добавления поля file_hash в таблицу analysis_history
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from database.database import ORM
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_database():
    """Добавляет поле file_hash в таблицу analysis_history"""
    
    # Создаем ORM и получаем движок
    orm = ORM()
    engine = await orm.get_async_engine()
    
    try:
        async with engine.begin() as conn:  # type: ignore
            # Проверяем, существует ли поле file_hash
            check_column_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'analysis_history' 
                AND column_name = 'file_hash'
            """)
            
            result = await conn.execute(check_column_query)
            column_exists = result.fetchone() is not None
            
            if column_exists:
                logger.info("Поле file_hash уже существует в таблице analysis_history")
                return
            
            # Добавляем поле file_hash
            add_column_query = text("""
                ALTER TABLE analysis_history 
                ADD COLUMN file_hash VARCHAR(64)
            """)
            
            await conn.execute(add_column_query)
            logger.info("Поле file_hash добавлено в таблицу analysis_history")
            
            # Создаем индекс
            create_index_query = text("""
                CREATE INDEX IF NOT EXISTS ix_analysis_history_file_hash 
                ON analysis_history (file_hash)
            """)
            
            await conn.execute(create_index_query)
            logger.info("Индекс ix_analysis_history_file_hash создан")
            
    except Exception as e:
        logger.error(f"Ошибка при выполнении миграции: {e}")
        raise
    finally:
        if engine:
            await engine.dispose()  # type: ignore

if __name__ == "__main__":
    asyncio.run(migrate_database()) 