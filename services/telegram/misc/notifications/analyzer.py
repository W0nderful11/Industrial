import logging
import typing
import html

from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.utils.i18n import I18n
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import Environ
from database.database import ORM
from database.models import User
from services.telegram.misc.utils import send_message_long
from services.telegram.schemas.analyzer import SolutionAboutError


async def notification_about_analysis_result(
        message: typing.Any,  # Message or MockMessage
        solution: SolutionAboutError,
        contents: typing.List[str],
        action_description: typing.Optional[str] = None,
        include_extracted_text_for_admin: bool = True,
        token_info: typing.Optional[str] = None
) -> None:
    """Обработка и отправка результата анализа"""

    env_config = Environ()
    channel_id = env_config.channel_id
    if not channel_id:
        logging.warning("ADMIN_CHANNEL_ID not set, skipping notification.")
        return

    try:
        full_name = html.escape(message.from_user.full_name or '')
        username = message.from_user.username

        user_details_parts = []
        if full_name:
            user_details_parts.append(full_name)
        if username:
            user_details_parts.append(f"@{username}")

        user_details = " ".join(user_details_parts)
        if not user_details:
            user_details = "Пользователь"

        header_elements = [
            f"<b>Для</b>: {user_details} ({message.from_user.id})",
            f"❌ <b>error_code</b>: {solution.error_code if solution.error_code else 'Не найдено'}"
        ]

        if action_description:
            header_elements.append(f"<i>{action_description}</i>")
        
        # header_elements.append("---") # Optional separator, can be added if desired

        kb = InlineKeyboardBuilder()
        user_id_for_reply = message.from_user.id
        if not isinstance(user_id_for_reply, int):
            try:
                user_id_for_reply = int(user_id_for_reply)
            except ValueError:
                logging.error(f"Could not convert user_id '{user_id_for_reply}' to int for reply button.")
                user_id_for_reply = None
        
        if user_id_for_reply:
            kb.button(text="Ответить пользователю", callback_data=f"reply_to_user:{user_id_for_reply}")

        # `contents` (from caller) should now be [device_info_header, solution_body]
        # Prepend our standard admin header to these contents.
        final_text_parts = header_elements + contents
        
        # Добавляем информацию о токенах в конец сообщения если она есть
        if token_info:
            final_text_parts.append(f"\n{token_info}")

        # if include_extracted_text_for_admin and solution.extracted_error_text_for_admin:
        #     # Avoid duplicating if it somehow got included by the caller (though it shouldn't)
        #     is_already_present = any(solution.extracted_error_text_for_admin in part for part in final_text_parts)
        #     if not is_already_present:
        #         final_text_parts.append(f"\n<b>Извлеченный текст ошибки (для админа):</b>\n{solution.extracted_error_text_for_admin}")
        
        text_to_send = "\n".join(final_text_parts)

        await send_message_long(
            bot=message.bot,
            chat_id=channel_id,
            text=text_to_send,
            reply_markup=kb.as_markup() if kb.buttons else None, # Отправляем клавиатуру только если есть кнопки
            parse_mode=ParseMode.HTML
        )

        # Forwarding the original message (log/photo)
        if hasattr(message, 'is_mock'): # This is our MockMessage
            await message.forward(channel_id) # MockMessage.forward expects target_chat_id
        elif hasattr(message, 'forward'): # This is a standard aiogram.Message
             # Standard way to forward an aiogram.Message object
            await message.bot.forward_message(chat_id=channel_id, from_chat_id=message.chat.id, message_id=message.message_id)
        else:
            logging.warning(f"Message object of type {type(message)} does not support expected forwarding methods.")


    except Exception as e:
        logging.error(f"Ошибка отправки уведомления в канал: {e}", exc_info=True)


async def notify_no_funds(message: Message, orm: ORM, i18n: I18n, user: User):
    # Упрощаем: всегда показываем masterkazakhstan
    admin_contacts = "@masterkazakhstan"

    await message.answer(
        i18n.gettext(
            "Ваш баланс равен 0.\n\n"
            "💬 Пожалуйста, обратитесь к администратору для пополнения баланса:\n\n"
            "{contacts}", locale=user.lang  # Используем язык пользователя для сообщения
        ).format(contacts=admin_contacts)
    )
