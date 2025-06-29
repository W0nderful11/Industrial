import argparse
import asyncio
import logging
import os

import coloredlogs
from aiogram import Bot, Dispatcher
from aiogram.utils.i18n import I18n
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import Environ, DEBUG_MODE
from database.database import ORM
from services.analyzer import KNOWN_ERROR_CODES
from services.telegram.jobs.tasks import check_subscribe_client, grant_monthly_token_bonus
from services.telegram.misc.create_dirs import create_dirs
from services.telegram.handlers.registration import TgRegister
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from services.exchange_rates import update_database_rates
from services.regional_pricing_service import load_regional_pricing_to_db


# Создаем кастомный класс Bot для хранения окружения
class MyBot(Bot):
    environment: Environ


async def start(environment: Environ):
    orm = ORM()

    bot = MyBot(
        token=environment.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Добавляем переменные окружения в атрибуты бота
    bot.environment = environment
    orm.create_tables(with_drop=False, echo=False)
    os.makedirs("data/tmp", exist_ok=True)
    await orm.create_repos()

    for admin_id in environment.admins:
        try:
            await orm.user_repo.upsert_user(
                user_id=admin_id,
                role='admin',
                # lang='ru' # Пример
            )
            logging.info(f"Пользователю {admin_id} установлена роль 'admin'.")
        except ValueError:
            logging.warning(f"Некорректный ID администратора: '{admin_id}'. Пропускаем.")
        except Exception as e_admin:
            logging.error(f"Ошибка при установке роли admin для ID {admin_id}: {e_admin}")

    await load_regional_pricing_to_db(orm)
    await update_database_rates(orm)

    create_dirs()

    i18n = I18n(path="./locales/", default_locale="ru", domain="messages")

    tg_register = TgRegister(dp, orm, i18n)
    tg_register.register()

    scheduler = AsyncIOScheduler(
        timezone='Asia/Almaty'
    )
    scheduler.add_job(
        update_database_rates,
        trigger=CronTrigger(hour=3, minute=0),
        args=(orm,)
    )
    # scheduler.add_job(
    #     check_subscribe_client,
    #     IntervalTrigger(minutes=1),
    #     args=(orm, bot, i18n),
    # )
    scheduler.add_job(
        grant_monthly_token_bonus,
        CronTrigger(day=1, hour=0, minute=5),
        args=(orm, bot, i18n)
    )
    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--recreate-db", action="store_true", help="Recreate database tables")
    args = parser.parse_args()

    env = Environ()
    logging.basicConfig(level=env.logging_level)
    coloredlogs.install()

    if args.recreate_db:
        # Временный синхронный вызов для пересоздания БД
        orm_sync = ORM()
        orm_sync.create_tables(with_drop=True)

    asyncio.run(start(env))
