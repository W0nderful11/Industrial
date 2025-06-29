import logging
from decimal import Decimal
import os
from aiogram import Bot
from aiogram.utils.i18n import I18n
from database.database import ORM
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Base price per analysis from environment variable
BASE_PRICE_PER_ANALYSIS = Decimal(os.getenv("PRICE_PER_ANALYSIS", "1.00"))
MONTHLY_BONUS_ANALYSIS_COUNT = 1

# --- Constant for Monthly Token Bonus ---
MONTHLY_BONUS_TOKENS = 1

async def give_monthly_bonus(bot: Bot, orm: ORM, i18n: I18n):
    """Gives a monthly token bonus to all registered users."""
    logger.info("Запуск ежемесячного начисления бонусных токенов...")
    # TODO: Define what constitutes an "active" user for the bonus (e.g., role='user')
    users = await orm.user_repo.find_all_active_users() # Assuming this method gets users with role 'user' or similar
    
    if not users:
        logger.info("Нет активных пользователей для начисления бонусных токенов.")
        return

    successful_bonuses = 0
    failed_bonuses = 0

    for user in users:
        try:
            # Add bonus tokens using the new method
            added_successfully = await orm.user_repo.add_tokens(user.user_id, MONTHLY_BONUS_TOKENS)
            
            if added_successfully:
                token_balance_after_bonus = await orm.user_repo.get_token_balance(user.user_id)
            
                # Send notification using tokens
                # TODO: i18n: Ensure locale works correctly
                notification_text = i18n.gettext(
                    "🎁 Вам начислен ежемесячный бонус: {count} токен. Ваш баланс: {balance} токенов.",
                locale=user.lang
                ).format(count=MONTHLY_BONUS_TOKENS, balance=token_balance_after_bonus)
            
                await bot.send_message(user.user_id, notification_text)
                successful_bonuses += 1
                logger.debug(f"Ежемесячный бонус ({MONTHLY_BONUS_TOKENS} токен) успешно начислен и уведомление отправлено пользователю {user.user_id}")
            else:
                 # Log failure if add_tokens returned False (e.g., user not found)
                 failed_bonuses += 1
                 logger.error(f"Не удалось начислить ежемесячный бонус пользователю {user.user_id} (метод add_tokens вернул False).")

        except Exception as e:
            failed_bonuses += 1
            logger.error(f"Исключение при начислении ежемесячного бонуса или отправке уведомления пользователю {user.user_id}: {e}")

    logger.info(f"Ежемесячное начисление бонусных токенов завершено. Успешно: {successful_bonuses}, Ошибки: {failed_bonuses}")

def schedule_monthly_bonus(scheduler: AsyncIOScheduler, bot: Bot, orm: ORM, i18n: I18n):
    """Schedules the monthly bonus job."""
    scheduler.add_job(
        give_monthly_bonus,
        trigger='cron', 
        day=1, 
        hour=9, # Run at 9 AM on the 1st of every month
        minute=0,
        kwargs={'bot': bot, 'orm': orm, 'i18n': i18n},
        id='monthly_bonus_job',
        name='Monthly User Bonus',
        replace_existing=True
    )
    logger.info("Ежемесячная задача начисления бонусов запланирована.") 