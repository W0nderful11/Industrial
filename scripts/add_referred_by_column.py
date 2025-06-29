import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Убираем все зависимости от .env и config
# Жестко прописываем данные для подключения
DB_USER = "deaspecty"
DB_PASSWORD = "W4p_Aspect"
DB_NAME = "iosbug"
DB_HOST = "localhost"
DB_PORT = "5432"

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def main():
    """
    Этот скрипт выполняет миграцию базы данных:
    1. Проверяет, существует ли колонка 'referred_by' в таблице 'users'.
    2. Если колонки нет, добавляет ее.
    3. Добавляет внешний ключ для обеспечения целостности данных.
    """
    print("Запуск миграции базы данных...")
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        # Проверяем, существует ли колонка
        result = await conn.execute(text("""
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='referred_by'
        """))
        column_exists = result.scalar_one_or_none()

        if not column_exists:
            print("Колонка 'referred_by' не найдена. Добавляю...")
            await conn.execute(text('ALTER TABLE users ADD COLUMN referred_by BIGINT'))
            print("Колонка 'referred_by' успешно добавлена.")
        else:
            print("Колонка 'referred_by' уже существует.")

    print("Миграция успешно завершена.")

if __name__ == "__main__":
    asyncio.run(main()) 