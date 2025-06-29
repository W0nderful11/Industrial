#!/usr/bin/env python3
"""
Миграция: добавление поля file_path в таблицу analysis_history
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import ORM
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

async def add_file_path_column():
    """Добавить поле file_path в таблицу analysis_history"""
    orm = ORM()
    
    try:
        # Используем синхронный движок для DDL операций
        engine = orm.get_engine()
        
        with engine.connect() as conn:
            # Проверяем существует ли уже столбец
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'analysis_history' 
                AND column_name = 'file_path'
            """))
            
            if result.fetchone():
                print("✅ Столбец file_path уже существует")
                return
            
            # Добавляем столбец
            conn.execute(text("""
                ALTER TABLE analysis_history 
                ADD COLUMN file_path VARCHAR(500)
            """))
            
            conn.commit()
            print("✅ Столбец file_path успешно добавлен в таблицу analysis_history")
            
    except Exception as e:
        logger.error(f"Ошибка при добавлении столбца: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(add_file_path_column()) 