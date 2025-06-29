#!/usr/bin/env python3
"""
Скрипт для добавления полей repeat_attempts, last_repeat_attempt и blocked_until 
в таблицу analysis_history для отслеживания повторных попыток анализа.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.database import ORM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def add_repeat_attempts_columns():
    """Добавить поля для отслеживания повторных попыток анализа."""
    
    orm = ORM()
    await orm.create_repos()
    
    try:
        if not orm.async_sessionmaker:
            logger.error("Failed to initialize async_sessionmaker")
            return
            
        async with orm.async_sessionmaker() as session:
            # Проверяем существование полей
            check_columns_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'analysis_history' 
                AND column_name IN ('repeat_attempts', 'last_repeat_attempt', 'blocked_until');
            """)
            
            result = await session.execute(check_columns_query)
            existing_columns = {row[0] for row in result.fetchall()}
            
            # Добавляем поля, которых нет
            if 'repeat_attempts' not in existing_columns:
                logger.info("Добавляем поле repeat_attempts...")
                await session.execute(text("""
                    ALTER TABLE analysis_history 
                    ADD COLUMN repeat_attempts INTEGER NOT NULL DEFAULT 0;
                """))
            else:
                logger.info("Поле repeat_attempts уже существует")
                
            if 'last_repeat_attempt' not in existing_columns:
                logger.info("Добавляем поле last_repeat_attempt...")
                await session.execute(text("""
                    ALTER TABLE analysis_history 
                    ADD COLUMN last_repeat_attempt TIMESTAMP;
                """))
            else:
                logger.info("Поле last_repeat_attempt уже существует")
                
            if 'blocked_until' not in existing_columns:
                logger.info("Добавляем поле blocked_until...")
                await session.execute(text("""
                    ALTER TABLE analysis_history 
                    ADD COLUMN blocked_until TIMESTAMP;
                """))
            else:
                logger.info("Поле blocked_until уже существует")
            
            # Создаем индексы для оптимизации запросов
            logger.info("Создаем индексы...")
            try:
                await session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_analysis_history_repeat_attempts 
                    ON analysis_history (repeat_attempts);
                """))
                
                await session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_analysis_history_blocked_until 
                    ON analysis_history (blocked_until);
                """))
            except Exception as e:
                logger.warning(f"Ошибка при создании индексов: {e}")
            
            await session.commit()
            logger.info("✅ Поля для отслеживания повторных попыток успешно добавлены!")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении полей: {e}")
        raise
        
    finally:
        if orm.engine:
            await orm.engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_repeat_attempts_columns()) 