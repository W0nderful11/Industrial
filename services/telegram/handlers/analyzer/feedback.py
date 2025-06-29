"""
Система обратной связи для анализатора файлов
"""
import html
import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InaccessibleMessage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.i18n import I18n

from config import Environ
from database.models import User
from services.telegram.misc.callbacks import LikeDislikeCallback, ReportCallback, AdminCallback
from services.telegram.misc.notifications.analyzer import notification_about_analysis_result
from services.telegram.template.analyzer import SolutionAboutError
from .states import ReportState

logger = logging.getLogger(__name__)

router = Router()


class MockFromUser:
    """Mock класс для пользователя в уведомлениях"""
    def __init__(self, id_val: int, username_val: Optional[str], full_name_val: Optional[str]):
        self.id = id_val
        self.username = username_val
        self.full_name = full_name_val


class MockChat:
    """Mock класс для чата в уведомлениях"""
    def __init__(self, id_val: int):
        self.id = id_val


class MockMessage:
    """Mock класс для сообщения в уведомлениях"""
    def __init__(self, msg_id: int, chat_id_val: int, from_uid: int, 
                 from_uname: Optional[str], from_fname: Optional[str], bot_instance: Bot):
        self.message_id = msg_id
        self.chat = MockChat(chat_id_val)
        self.from_user = MockFromUser(from_uid, from_uname, from_fname)
        self.bot = bot_instance
        self.is_mock = True

    async def forward(self, target_chat_id: int):
        """Пересылает оригинальное сообщение"""
        try:
            await self.bot.forward_message(
                chat_id=target_chat_id, 
                from_chat_id=self.chat.id, 
                message_id=self.message_id
            )
        except Exception as e_fwd:
            logger.error(f"Could not forward original message {self.message_id} "
                        f"from {self.chat.id} to {target_chat_id}: {e_fwd}")


@router.callback_query(LikeDislikeCallback.filter())
async def handle_like_dislike(query: CallbackQuery, callback_data: LikeDislikeCallback, 
                            state: FSMContext, i18n: I18n, user: User, env: Environ):
    """Обработчик лайков и дизлайков"""
    action = callback_data.action

    # Убираем только кнопки лайка/дизлайка, оставляем остальные (например, "Полный ответ")
    original_markup = None
    if query.message and not isinstance(query.message, InaccessibleMessage):
        original_markup = query.message.reply_markup
    
    new_kb = InlineKeyboardBuilder()
    
    if original_markup:
        for row in original_markup.inline_keyboard:
            new_row_buttons = []
            for button in row:
                if not (button.callback_data and button.callback_data.startswith("like_dislike")):
                    new_button = InlineKeyboardButton(
                        text=button.text, 
                        url=button.url, 
                        callback_data=button.callback_data,
                        web_app=button.web_app, 
                        login_url=button.login_url,
                        switch_inline_query=button.switch_inline_query,
                        switch_inline_query_current_chat=button.switch_inline_query_current_chat,
                        callback_game=button.callback_game, 
                        pay=button.pay
                    )
                    new_row_buttons.append(new_button)
            if new_row_buttons:
                new_kb.row(*new_row_buttons)

    if action == "like":
        await _handle_like_action(query, new_kb, i18n, user)
    elif action == "dislike":
        await _handle_dislike_action(query, new_kb, state, i18n, user)


async def _handle_like_action(query: CallbackQuery, new_kb: InlineKeyboardBuilder, 
                            i18n: I18n, user: User):
    """Обрабатывает лайк"""
    if not query.message or isinstance(query.message, InaccessibleMessage):
        await query.answer("Сообщение недоступно")
        return
        
    # Получаем оригинальный текст или подпись
    original_text = ""
    if query.message.text:
        original_text = query.message.text
    elif query.message.caption:
        original_text = query.message.caption
        
    feedback_text = original_text + f"\n\n<i>{i18n.gettext('Thanks for your feedback!', locale=user.lang)}</i>"
    
    try:
        # Редактируем текст или подпись в зависимости от типа сообщения
        if query.message.photo:
            await query.message.edit_caption(
                caption=feedback_text,
                reply_markup=new_kb.as_markup() if new_kb.buttons else None
            )
        else:
            await query.message.edit_text(
                feedback_text,
                reply_markup=new_kb.as_markup() if new_kb.buttons else None
            )
    except Exception as e:
        logger.warning(f"Could not edit message after like: {e}")
        
    await query.answer()


async def _handle_dislike_action(query: CallbackQuery, new_kb: InlineKeyboardBuilder, 
                                state: FSMContext, i18n: I18n, user: User):
    """Обрабатывает дизлайк"""
    if not query.message or isinstance(query.message, InaccessibleMessage):
        await query.answer("Сообщение недоступно")
        return
        
    try:
        # Убираем кнопки лайка/дизлайка
        await query.message.edit_reply_markup(
            reply_markup=new_kb.as_markup() if new_kb.buttons else None
        )
        
        # Сохраняем информацию для пересылки
        data = await state.get_data()
        chat_id = query.message.chat.id
        message_id = query.message.message_id
        key_suffix = f"_{chat_id}_{message_id}"
        file_id = data.get(f"file_id{key_suffix}")
        original_msg_id = data.get(f"original_msg_id{key_suffix}")
        analysis_text = data.get(f"analysis_text{key_suffix}")

        await state.update_data(
            report_file_id=file_id,
            report_original_msg_id=original_msg_id,
            report_original_chat_id=query.from_user.id,
            report_analysis_text=analysis_text
        )
        
        await query.message.answer(
            i18n.gettext("Please describe your issue — it will be sent to the admin.", locale=user.lang)
        )
        await state.set_state(ReportState.waiting_for_report)
        
    except Exception as e:
        logger.warning(f"Could not handle dislike action: {e}")
        
    await query.answer()


@router.callback_query(ReportCallback.filter(F.action == "report_issue"))
async def handle_report_button(query: CallbackQuery, state: FSMContext, i18n: I18n, user: User):
    """Обработчик кнопки жалобы (устаревший, оставлен для совместимости)"""
    await query.answer()


@router.message(ReportState.waiting_for_report)
async def handle_report_description(message: Message, state: FSMContext, bot: Bot, 
                                  i18n: I18n, user: User, env: Environ):
    """Обработчик описания проблемы от пользователя"""
    if not message.from_user:
        await message.answer("Ошибка: не удалось определить отправителя")
        return
        
    data = await state.get_data()
    original_msg_id = data.get("report_original_msg_id")
    original_chat_id = data.get("report_original_chat_id")
    analysis_text = data.get("report_analysis_text")
    
    # Формируем единый текст для отчета
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

    header = f"{user_details} ({message.from_user.id}) сообщил(а) о проблеме:"
    user_report_text = message.text or "Нет текста"
    
    # Собираем все части
    report_parts = [header, user_report_text]
    if analysis_text:
        report_parts.append(analysis_text)
    
    full_report_text = "\n\n".join(report_parts)

    # Создаем кнопку для ответа пользователю
    reply_kb = InlineKeyboardBuilder()
    reply_kb.add(
        InlineKeyboardButton(
            text=i18n.gettext("Ответить пользователю", locale='ru'),
            callback_data=AdminCallback(action="reply_to_user", user_id=user.user_id).pack()
        )
    )

    try:
        # Отправляем объединенный отчет с кнопкой
        await bot.send_message(
            chat_id=env.channel_id,
            text=full_report_text,
            reply_markup=reply_kb.as_markup(),
            parse_mode="HTML"
        )

        # Пересылаем исходное сообщение с файлом/фото
        if original_msg_id and original_chat_id:
            try:
                await bot.forward_message(
                    chat_id=env.channel_id,
                    from_chat_id=original_chat_id,
                    message_id=original_msg_id
                )
            except Exception as e:
                logger.error(f"Не удалось переслать исходный файл для жалобы: {e}")
                await bot.send_message(
                    chat_id=env.channel_id,
                    text=i18n.gettext("Не удалось переслать исходный файл для жалобы.", locale='ru')
                )

        await message.answer(
            i18n.gettext("Thank you! Your message has been sent to the admin.", locale=user.lang)
        )
        
    except Exception as e:
        logger.error(f"Error sending report to admin: {e}")
        await message.answer(
            i18n.gettext("Произошла ошибка при отправке жалобы.", locale=user.lang)
        )
    
    # Очищаем данные жалобы
    await _clear_report_data(state)


async def _clear_report_data(state: FSMContext):
    """Очищает данные жалобы из состояния"""
    current_data = await state.get_data()
    keys_to_remove = ["report_file_id", "report_original_msg_id", "report_original_chat_id", "report_analysis_text"]
    for key in keys_to_remove:
        if key in current_data:
            del current_data[key]
            
    await state.set_data(current_data)
    await state.set_state(None)


async def send_admin_notification_for_full_answer(callback_query: CallbackQuery, stored_data: dict, 
                                                i18n: I18n, user: User):
    """Отправляет уведомление админу при запросе полного ответа"""
    if not callback_query.bot:
        return
        
    original_message_id = stored_data.get("original_message_id")
    original_chat_id = stored_data.get("original_chat_id")
    original_from_user_id = stored_data.get("original_from_user_id")
    original_from_user_username = stored_data.get("original_from_user_username")
    original_from_user_full_name = stored_data.get("original_from_user_full_name")
    
    # Получаем полные данные решения
    error_code = stored_data.get("error_code")
    panic_string = stored_data.get("panic_string")
    full_descriptions = stored_data.get("descriptions", [])
    full_links = stored_data.get("links", [])
    date_of_failure = stored_data.get("date_of_failure", "")
    phone_model_name = stored_data.get("phone_model_name")
    phone_model_version = stored_data.get("phone_model_version")
    phone_ios_version = stored_data.get("phone_ios_version")
    
    # Импортируем необходимые шаблоны
    from services.telegram.template.analyzer import template_about_analysis_result_header, template_about_analysis_result
    from services.telegram.schemas.analyzer import ModelPhone
    
    # Создаем заголовок с информацией об устройстве
    phone_for_header = ModelPhone(
        model=phone_model_name,
        version=phone_model_version,
        ios_version=phone_ios_version
    )
    
    solution_for_header = SolutionAboutError(
        descriptions=[], 
        links=[], 
        date_of_failure=date_of_failure,
        error_code=error_code
    )
    
    device_info_header = template_about_analysis_result_header(
        phone=phone_for_header,
        solution_about_error=solution_for_header,
        i18n=i18n,
        lang=user.lang
    )
    
    # Создаем полное содержимое решения
    solution_for_body = SolutionAboutError(
        descriptions=full_descriptions,
        links=full_links,
        date_of_failure=date_of_failure, 
        is_full=True,
        error_code=error_code
    )
    
    solution_body_text = template_about_analysis_result(
        solution_for_body, 
        i18n=i18n, 
        lang=user.lang
    )
    
    # Формируем полное содержимое для админов
    contents_for_admin_body = [device_info_header, solution_body_text]
    
    # Создаем объект решения для админских уведомлений (только для заголовка)
    solution_for_admin_notification_obj = SolutionAboutError(
        descriptions=[], 
        links=[], 
        date_of_failure=date_of_failure,
        is_full=True, 
        error_code=error_code,
        panic_string=panic_string,
        extracted_error_text_for_admin=None
    )

    if (original_message_id and original_chat_id and 
        original_from_user_id is not None):
        
        mock_original_message = MockMessage(
            msg_id=original_message_id,
            chat_id_val=original_chat_id,
            from_uid=original_from_user_id,
            from_uname=original_from_user_username,
            from_fname=original_from_user_full_name,
            bot_instance=callback_query.bot
        )
        
        try:
            await notification_about_analysis_result(
                message=mock_original_message, 
                solution=solution_for_admin_notification_obj, 
                contents=contents_for_admin_body,
                action_description=i18n.gettext("Пользователь нажал полный ответ", locale='ru'),
                include_extracted_text_for_admin=False,
                token_info=None
            )
        except Exception as e:
            logger.error(f"Could not send admin notification for full answer: {e}")
    else:
        logger.warning(f"Not enough data to send full admin notification for user {user.user_id}, error {error_code}") 