from database.database import ORM
from aiogram import Bot
from aiogram.utils.i18n import I18n
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound
import logging

logger = logging.getLogger(__name__)

async def check_subscribe_client(orm: ORM, bot: Bot, i18n: I18n):
    (expired_subscriptions, almost_expired_subscriptions) = await orm.subscription_repo.get_expired()

    for subscription in expired_subscriptions:
        user_id = subscription.user_id
        await orm.subscription_repo.delete_subscription(user_id)
        user = await orm.user_repo.find_user_by_user_id(user_id)

        if user and user.lang:
            text = i18n.gettext('Ваша подписка истекла \nОбратитесь к админу чтобы вам продлили подписку', locale=user.lang)
            try:
                await bot.send_message(user_id, text)
            except (TelegramForbiddenError, TelegramNotFound) as e:
                logger.warning(f"Не удалось отправить уведомление об истечении подписки пользователю {user_id}: {e}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления об истечении подписки пользователю {user_id}: {e}", exc_info=True)

    for subscription in almost_expired_subscriptions:
        user_id = subscription.user_id
        await orm.subscription_repo.warn_user(user_id)
        user = await orm.user_repo.find_user_by_user_id(user_id)

        if user and user.lang:
            text = i18n.gettext('Ваша подписка истекает через сутки \nОбратитесь к админу чтобы вам продлили подписку', locale=user.lang)
            try:
                await bot.send_message(user_id, text)
            except (TelegramForbiddenError, TelegramNotFound) as e:
                logger.warning(f"Не удалось отправить предупреждение о подписке пользователю {user_id}: {e}")
            except Exception as e:
                logger.error(f"Ошибка при отправке предупреждения о подписке пользователю {user_id}: {e}", exc_info=True)

async def grant_monthly_token_bonus(orm: ORM, bot: Bot, i18n: I18n):
    logger.info("Запуск ежемесячного начисления бонусных токенов...")
    tokens_to_add = 1
    users = await orm.user_repo.find_all()
    success_count = 0
    fail_count = 0

    for user in users:
        try:
            success = await orm.user_repo.add_tokens(user_id=user.user_id, tokens_to_add=tokens_to_add)
            if success:
                success_count += 1
                logger.info(f"Начислен {tokens_to_add} бонусный токен пользователю {user.user_id}.")
                try:
                    user_lang = user.lang if user.lang else 'ru'
                    bonus_message = i18n.gettext("🎁 Вам начислен ежемесячный бонус: {count} токен!", locale=user_lang).format(count=tokens_to_add)
                    await bot.send_message(user.user_id, bonus_message)
                except (TelegramForbiddenError, TelegramNotFound) as e:
                    logger.warning(f"Не удалось отправить уведомление о ежемесячном бонусе пользователю {user.user_id}: {e}")
                except Exception as e_msg:
                    logger.error(f"Ошибка при отправке уведомления о ежемесячном бонусе пользователю {user.user_id}: {e_msg}", exc_info=True)
            else:
                fail_count += 1
        except Exception as e_add:
            fail_count += 1
            logger.error(f"Ошибка при начислении ежемесячного бонуса пользователю {user.user_id}: {e_add}", exc_info=True)

    logger.info(f"Ежемесячное начисление бонусных токенов завершено. Успешно: {success_count}, Неудачно: {fail_count}.")