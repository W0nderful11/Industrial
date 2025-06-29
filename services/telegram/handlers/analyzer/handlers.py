"""
Основные обработчики анализатора файлов
"""
import asyncio
from datetime import datetime
import logging
import re
from typing import Optional
import os

from aiogram import Router, F, Bot
from aiogram.filters import or_f
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.i18n import I18n

from config import Environ, SUBSCRIPTION_ANALYSIS_LIMIT
from database.database import ORM
from database.models import User
from services.analyzer.solutions import find_error_solutions
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import FullButtonCallback, LikeDislikeCallback
from services.telegram.misc.keyboards import Keyboards
from services.telegram.misc.notifications.analyzer import notify_no_funds, notification_about_analysis_result
from services.telegram.misc.utils import delete_message, remove_file
from services.telegram.template.analyzer import template_about_analysis_result, template_about_analysis_result_header, \
    template_not_found_solution, SolutionAboutError
from services.telegram.schemas.analyzer import ModelPhone
from .utils import sanitize_callback_data

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))
openai_semaphore = asyncio.Semaphore(1)


@router.message(
    or_f(
        F.document.file_name.endswith((".ips", ".txt", ".json", ".png", ".jpg", ".jpeg")),
        F.photo
    )
)
async def document_analyze(
        message: Message,
        user: User,
        orm: ORM,
        i18n: I18n,
        state: FSMContext,
        env: Environ
):
    """Основной обработчик анализа файлов"""
    logger.info(f"Starting analysis for user_id={user.user_id}, username={message.from_user.username if message.from_user else 'Unknown'}, user_lang={user.lang}")
    
    if not message.bot:
        await message.answer(i18n.gettext("Ошибка: бот недоступен", locale=user.lang))
        return
    
    # Проверяем ограничения по хешу файла ПЕРЕД началом анализа
    if orm and orm.async_sessionmaker:
        try:
            # Скачиваем файл для вычисления хеша
            file_obj = None
            if message.document:
                file_obj = await message.bot.download(message.document)
            elif message.photo:
                file_obj = await message.bot.download(message.photo[-1])
            
            if file_obj:
                from services.telegram.misc.utils import calculate_file_hash_from_file_like
                file_hash = await calculate_file_hash_from_file_like(file_obj)
                
                # Проверяем ограничения по хешу
                async with orm.async_sessionmaker() as session:
                    from database.repo.analysis_history import AnalysisHistoryRepo
                    history_repo = AnalysisHistoryRepo(session)
                    can_analyze, error_message, existing_analysis_id = await history_repo.can_analyze_file_by_hash(
                        user.user_id, file_hash
                    )
                
                if not can_analyze:
                    await message.answer(
                        i18n.gettext("⏰ *Повторные круги ограничены*\n\n{message}", locale=user.lang).format(message=error_message),
                        parse_mode="Markdown"
                    )
                    return
        except Exception as e:
            logger.warning(f"Error checking file hash limitations: {e}")
            # Продолжаем анализ если не удалось проверить ограничения
        
    wait_message = await message.answer(i18n.gettext("Подождите, идет Анализ...", locale=user.lang))
    await message.chat.do("typing")
    response_solutions = None

    try:
        # Проверяем баланс токенов и подписку
        if not orm or not orm.user_repo:
            await message.answer(i18n.gettext("Ошибка: сервис временно недоступен", locale=user.lang))
            return
            
        initial_token_balance = await orm.user_repo.get_token_balance(user.user_id)
        active_subscription_for_balance_check = None

        response_solutions = await find_error_solutions(message=message, user=user)
        solution = response_solutions.solution
        phone_model_info = response_solutions.phone
        current_crash_reporter_key = getattr(phone_model_info, 'crash_reporter_key', None)
        
        if current_crash_reporter_key:
            current_crash_reporter_key = current_crash_reporter_key.lower()
            active_subscription_for_balance_check = await orm.user_repo.get_active_subscription(
                user.user_id, current_crash_reporter_key
            )

        # Проверяем, есть ли средства для анализа
        if initial_token_balance <= 0 and (
            not active_subscription_for_balance_check or 
            not active_subscription_for_balance_check.analysis_count > 0
        ):
            await delete_message(message.bot, wait_message)
            return await notify_no_funds(message=message, orm=orm, i18n=i18n, user=user)

        # Подготавливаем данные для ответа
        keyboard_builder = InlineKeyboardBuilder()
        token_message_parts = []

        # Создаем заголовок с информацией об устройстве
        header_solution_obj = SolutionAboutError(
            descriptions=[], 
            links=[], 
            error_code=solution.error_code if solution else None,
            date_of_failure=solution.date_of_failure if solution else ""
        )
        
        device_info_header = template_about_analysis_result_header(
            phone=phone_model_info,
            solution_about_error=header_solution_obj,
            i18n=i18n,
            lang=user.lang
        )

        user_final_text = device_info_header
        admin_notification_body_parts = [device_info_header]
        admin_solution_obj_for_notification = None

        # Обрабатываем результат анализа
        solution_found = solution and solution.descriptions
        
        if not solution_found:
            user_final_text = await _handle_no_solution(
                solution, response_solutions, keyboard_builder, user_final_text, 
                admin_notification_body_parts, token_message_parts, i18n, user
            )
            admin_solution_obj_for_notification = _create_no_solution_admin_obj(solution, i18n, user)
        else:
            user_final_text, admin_solution_obj_for_notification = await _handle_solution_found(
                solution, phone_model_info, keyboard_builder, user_final_text, 
                admin_notification_body_parts, state, i18n, user, message
            )

        # Обрабатываем токены и подписки ТОЛЬКО если найдено решение
        if solution_found:
            await _process_tokens_and_subscriptions(
                orm, user, current_crash_reporter_key, phone_model_info, 
                initial_token_balance, active_subscription_for_balance_check,
                token_message_parts, i18n
            )

        # Удаляем сообщение ожидания
        await delete_message(message.bot, wait_message)

        # Сохраняем анализ в истории
        file_hash_for_attempts = None
        try:
            # Вычисляем хеш для обновления счетчиков попыток
            file_obj = None
            if message.document:
                file_obj = await message.bot.download(message.document)
            elif message.photo:
                file_obj = await message.bot.download(message.photo[-1])
            
            if file_obj:
                from services.telegram.misc.utils import calculate_file_hash_from_file_like
                file_hash_for_attempts = await calculate_file_hash_from_file_like(file_obj)
        except Exception as e:
            logger.warning(f"Error calculating hash for attempt tracking: {e}")
        
        await _save_analysis_to_history(
            orm, user, message, response_solutions, solution, 
            phone_model_info, solution_found, token_message_parts
        )
        
        # Обновляем счетчики попыток по хешу файла
        if file_hash_for_attempts and orm and orm.async_sessionmaker:
            try:
                async with orm.async_sessionmaker() as session:
                    from database.repo.analysis_history import AnalysisHistoryRepo
                    history_repo = AnalysisHistoryRepo(session)
                    
                    if solution_found:
                        # При успешном анализе сбрасываем счетчик
                        await history_repo.reset_attempts_by_hash(user.user_id, file_hash_for_attempts)
                    else:
                        # При неуспешном анализе увеличиваем счетчик
                        await history_repo.increment_attempts_by_hash(user.user_id, file_hash_for_attempts)
            except Exception as e:
                logger.warning(f"Error updating attempt counters: {e}")

        # Добавляем кнопки лайка/дизлайка
        _add_feedback_buttons(keyboard_builder)
        
        # Отправляем финальный ответ
        await _send_final_response(
            message, user_final_text, token_message_parts, keyboard_builder, 
            state, solution, i18n, user
        )

        # Отправляем уведомление администратору
        if admin_solution_obj_for_notification:
            # Формируем информацию о токенах для админов
            token_info_for_admin = " ".join(token_message_parts) if token_message_parts else None
            
            await notification_about_analysis_result(
                message=message,
                solution=admin_solution_obj_for_notification,
                contents=admin_notification_body_parts,
                action_description=i18n.gettext("Получен результат анализа", locale=user.lang),
                include_extracted_text_for_admin=(
                    solution is not None and 
                    solution.extracted_error_text_for_admin is not None
                ),
                token_info=token_info_for_admin
            )

    except Exception as e:
        logger.exception(f"Произошла ошибка при анализе файла: {e}")
        await _handle_analysis_error(message, wait_message, e, i18n, user)
    finally:
        # Очищаем временные файлы
        await _cleanup_temp_files(response_solutions)


async def _handle_no_solution(solution, response_solutions, keyboard_builder, user_final_text, 
                            admin_notification_body_parts, token_message_parts, i18n, user):
    """Обрабатывает случай, когда решение не найдено"""
    no_solution_text = template_not_found_solution(
        content_type=response_solutions.content_type,
        i18n=i18n,
        lang=user.lang
    )
    token_message_parts.append(
        i18n.gettext("Токен не списан, т.к. готовое решение не найдено в базе.", locale=user.lang)
    )
    user_final_text += "\n" + (no_solution_text or "")
    keyboard_builder.row(Keyboards.show_diagnostics_button(i18n, user.lang).inline_keyboard[0][0])

    admin_notification_body_parts.append(no_solution_text or "")
    
    return user_final_text


def _create_no_solution_admin_obj(solution, i18n, user):
    """Создает объект для админского уведомления при отсутствии решения"""
    return SolutionAboutError(
        descriptions=[], 
        links=[],
        error_code=solution.error_code if solution else "N/A",
        panic_string=solution.panic_string if solution else None,
        date_of_failure=(
            solution.date_of_failure 
            if solution and hasattr(solution, 'date_of_failure') and solution.date_of_failure 
            else i18n.gettext("Не указана", locale=user.lang)
        ),
        extracted_error_text_for_admin=solution.extracted_error_text_for_admin if solution else None
    )


async def _handle_solution_found(solution, phone_model_info, keyboard_builder, user_final_text, 
                               admin_notification_body_parts, state, i18n, user, message):
    """Обрабатывает случай, когда решение найдено"""
    user_text_to_show = solution.descriptions
    admin_error_code_for_notification = solution.error_code
    admin_solution_body_text_parts = solution.descriptions

    # Обрабатываем мини-ответ с возможностью показать полный
    if solution.is_mini_response_shown and solution.has_full_solution_available:
        admin_error_code_for_notification = f"{solution.error_code} mini"
        
        if solution.full_descriptions:
            model_id_for_callback = phone_model_info.version or phone_model_info.model
            
            if solution.error_code and model_id_for_callback:
                safe_error_code = sanitize_callback_data(solution.error_code)
                keyboard_builder.button(
                    text=i18n.gettext("Полный ответ ⏬", locale=user.lang),
                    callback_data=FullButtonCallback(
                        action="show_full", 
                        error_code=safe_error_code, 
                        model=model_id_for_callback
                    ).pack()
                )
                
                # Сохраняем данные для полного ответа
                await _save_full_answer_data(
                    state, solution, phone_model_info, model_id_for_callback, 
                    message, user
                )

    # Формируем текст для пользователя
    solution_obj_for_user_display = SolutionAboutError(
        descriptions=user_text_to_show, 
        links=solution.links,
        date_of_failure=solution.date_of_failure, 
        is_full=not solution.is_mini_response_shown,
        error_code=solution.error_code
    )
    
    user_final_text += "\n" + template_about_analysis_result(
        solution_obj_for_user_display, 
        i18n=i18n, 
        lang=user.lang
    )
    
    # Формируем данные для админского уведомления
    solution_obj_for_admin_body_template = SolutionAboutError(
        descriptions=admin_solution_body_text_parts, 
        links=solution.links,
        date_of_failure=solution.date_of_failure,
        is_full=not (solution.is_mini_response_shown and solution.has_full_solution_available),
        error_code=admin_error_code_for_notification
    )
    
    admin_notification_body_parts.append(
        template_about_analysis_result(solution_obj_for_admin_body_template, i18n=i18n, lang=user.lang)
    )
    
    admin_solution_obj_for_notification = SolutionAboutError(
        descriptions=[], 
        links=[], 
        date_of_failure=solution.date_of_failure,
        error_code=admin_error_code_for_notification, 
        panic_string=solution.panic_string,
        extracted_error_text_for_admin=solution.extracted_error_text_for_admin
    )

    return user_final_text, admin_solution_obj_for_notification


async def _save_full_answer_data(state, solution, phone_model_info, model_id_for_callback, 
                               message, user):
    """Сохраняет данные для показа полного ответа"""
    data_to_save = {
        "descriptions": solution.full_descriptions, 
        "links": solution.full_links, 
        "error_code": solution.error_code,
        "phone_model_name": phone_model_info.model, 
        "phone_model_version": model_id_for_callback,
        "phone_ios_version": phone_model_info.ios_version, 
        "date_of_failure": solution.date_of_failure,
        "panic_string": solution.panic_string,
        "extracted_error_text_for_admin": solution.extracted_error_text_for_admin,
        "original_message_id": message.message_id, 
        "original_chat_id": message.chat.id,
    }
    
    # Безопасно получаем данные о пользователе
    if message.from_user:
        data_to_save.update({
            "original_from_user_id": message.from_user.id,
            "original_from_user_username": getattr(message.from_user, 'username', None),
            "original_from_user_full_name": getattr(message.from_user, 'full_name', None)
        })
    
    await state.update_data({
        f"full_answer_{user.user_id}_{solution.error_code}_{model_id_for_callback}": data_to_save
    })


async def _process_tokens_and_subscriptions(orm, user, current_crash_reporter_key, phone_model_info, 
                                          initial_token_balance, active_subscription_for_balance_check,
                                          token_message_parts, i18n):
    """Обрабатывает токены и подписки"""
    use_general_token = False

    if current_crash_reporter_key:
        active_subscription = await orm.user_repo.get_active_subscription(
            user.user_id, current_crash_reporter_key
        )

        if active_subscription and active_subscription.analysis_count > 0:
            updated_subscription = await orm.user_repo.decrement_subscription_analysis_count(
                user.user_id, current_crash_reporter_key
            )
            if updated_subscription is not None:
                remaining_analyses = updated_subscription.analysis_count
                token_message_parts.append(
                    i18n.gettext(
                        "Анализ по подписке (осталось {count} бесплатных для этого устройства).", 
                        locale=user.lang
                    ).format(count=remaining_analyses)
                )
            else:
                use_general_token = True
        else:
            use_general_token = True
    else:
        use_general_token = True

    if use_general_token and initial_token_balance > 0:
        new_balance = await orm.user_repo.deduct_token(user.user_id)
        if new_balance is not None:
            # Создаем новую подписку если есть crash_reporter_key
            if current_crash_reporter_key and phone_model_info.version:
                analyses_for_new_sub = SUBSCRIPTION_ANALYSIS_LIMIT - 1
                await orm.user_repo.create_or_update_subscription(
                    user_id=user.user_id,
                    crash_reporter_key=current_crash_reporter_key,
                    product=phone_model_info.version,
                    analysis_limit=analyses_for_new_sub
                )
                token_message_parts.append(
                    i18n.gettext(
                        "Списан 1 токен (остаток: {balance}).\nНачался 30-дневный период: "
                        "следующие {count} анализов для этого отчета будут бесплатными.",
                        locale=user.lang
                    ).format(balance=new_balance, count=analyses_for_new_sub)
                )
            else:
                token_message_parts.append(
                    i18n.gettext("Списан 1 токен (остаток: {balance}).", locale=user.lang)
                    .format(balance=new_balance)
                )
        else:
            token_message_parts.append(
                i18n.gettext("Произошла ошибка при списании токена.", locale=user.lang)
            )
    elif use_general_token:
        logger.warning(f"User {user.user_id} has 0 balance, but analysis proceeded to token deduction stage.")


def _add_feedback_buttons(keyboard_builder):
    """Добавляет кнопки лайка и дизлайка"""
    feedback_kb = InlineKeyboardBuilder()
    feedback_kb.button(text="👍", callback_data=LikeDislikeCallback(action="like").pack())
    feedback_kb.button(text="👎", callback_data=LikeDislikeCallback(action="dislike").pack())
    keyboard_builder.row(*feedback_kb.buttons)


async def _send_final_response(message, user_final_text, token_message_parts, keyboard_builder, 
                             state, solution, i18n, user):
    """Отправляет финальный ответ пользователю"""
    # Добавляем информацию о токенах
    final_token_status_message = " ".join(token_message_parts)
    if final_token_status_message:
        user_final_text += "\n\n" + final_token_status_message

    # Отправляем ответ
    final_reply_markup = keyboard_builder.as_markup()
    sent_message = await message.answer(user_final_text, reply_markup=final_reply_markup)

    # Сохраняем данные для системы обратной связи
    await _save_feedback_data(message, sent_message, user_final_text, state)

    # Отправляем кнопку консультации если есть решение
    if solution and solution.descriptions:
        await _send_consultation_button(message, user_final_text, i18n, user)


async def _save_feedback_data(message, sent_message, user_final_text, state):
    """Сохраняет данные для системы обратной связи"""
    # Определяем file_id
    if message.document:
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        file_id = "none"

    # Сохраняем данные для дизлайков
    if file_id != "none":
        await state.update_data({
            f"file_id_{sent_message.chat.id}_{sent_message.message_id}": file_id,
            f"original_msg_id_{sent_message.chat.id}_{sent_message.message_id}": message.message_id,
            f"analysis_text_{sent_message.chat.id}_{sent_message.message_id}": user_final_text,
        })


async def _send_consultation_button(message, user_final_text, i18n, user):
    """Отправляет кнопку для консультации специалиста"""
    short_info = _create_short_consultation_info(user_final_text, i18n, user.lang)
    consultation_keyboard = Keyboards.create_consultation_button(i18n, user.lang, short_info)
    consultation_message_text = i18n.gettext(
        "Если вам нужна дополнительная помощь специалиста или вы хотите обсудить полученный ответ, "
        "нажмите кнопку ниже. 👇\n\n"
        "Пожалуйста, не забудьте отправить файл лога или скриншот в следующем сообщении в чат с консультантом, "
        "чтобы он мог быстрее вам помочь.",
        locale=user.lang
    )
    await message.answer(text=consultation_message_text, reply_markup=consultation_keyboard)


def _create_short_consultation_info(user_final_text, i18n, lang):
    """Создает краткую информацию для консультации"""
    cleaned_text = re.sub(r'<[^>]+>', '', user_final_text)
    lines = cleaned_text.split('\n')
    
    # Извлекаем только основную информацию об устройстве и ошибках
    structured_message = []
    error_section = False
    
    for line in lines:
        if any(label in line for label in ["📱", "🛠️", "📅"]):
            structured_message.append(line.strip())
        elif any(label in line for label in [
            i18n.gettext("Найденные ошибки", locale=lang),
            "Found errors"
        ]):
            error_section = True
            structured_message.append(line.strip())
        elif error_section:
            if any(stop_word in line.lower() for stop_word in ["token", "токен", "subscription", "подписк"]):
                break
            if line.strip():
                structured_message.append(line.strip())
    
    short_info = "\n".join(structured_message)
    max_text_len = 1500
    if len(short_info) > max_text_len:
        short_info = short_info[:max_text_len] + "..."
        
    return short_info


async def _handle_analysis_error(message, wait_message, error, i18n, user):
    """Обрабатывает ошибки анализа"""
    if message.bot and wait_message:
        try:
            await delete_message(message.bot, wait_message)
        except Exception:
            pass
    
    error_details_for_admin = SolutionAboutError(
        descriptions=[f"Подробности для администратора: {error}"],
        links=[], 
        date_of_failure=datetime.now().isoformat(), 
        error_code="Exception",
        panic_string=str(error), 
        extracted_error_text_for_admin=str(error)
    )
    
    error_content_for_admin = [
        f"<b>Исключение при анализе файла</b>", 
        f"<b>Текст ошибки:</b>\n<pre>{error}</pre>"
    ]
    
    try:
        await notification_about_analysis_result(
            message=message, 
            solution=error_details_for_admin, 
            contents=error_content_for_admin,
            action_description="Критическая ошибка в обработчике анализа"
        )
    except Exception as notify_error:
        logger.error(f"Could not send error notification: {notify_error}")
    
    await message.answer(
        i18n.gettext("Произошла непредвиденная ошибка при анализе. Администраторы уведомлены.", 
                     locale=user.lang)
    )


async def _save_analysis_to_history(
    orm, user, message, response_solutions, solution, 
    phone_model_info, solution_found, token_message_parts
):
    """Сохраняет анализ в истории пользователя"""
    try:
        # Определяем тип файла и получаем file_id
        file_type = "unknown"
        original_filename = None
        file_size = None
        file_id = None  # Используем file_id вместо физического пути
        file_hash = None  # Хеш файла для дедупликации
        
        # Вычисляем хеш файла
        try:
            file_obj = None
            if message.document:
                original_filename = message.document.file_name
                file_size = message.document.file_size
                file_id = message.document.file_id  # Сохраняем file_id от Telegram
                file_obj = await message.bot.download(message.document)
                if original_filename:
                    if original_filename.endswith('.ips'):
                        file_type = "ips"
                    elif original_filename.endswith('.txt'):
                        file_type = "txt"
                    elif original_filename.endswith('.json'):
                        file_type = "json"
            elif message.photo:
                file_type = "photo"
                original_filename = "photo.jpg"
                file_id = message.photo[-1].file_id  # Берем самое большое фото
                file_obj = await message.bot.download(message.photo[-1])
                if message.photo:
                    file_size = message.photo[-1].file_size
            
            # Вычисляем хеш
            if file_obj:
                from services.telegram.misc.utils import calculate_file_hash_from_file_like
                file_hash = await calculate_file_hash_from_file_like(file_obj)
                logger.info(f"Calculated file hash: {file_hash}")
        except Exception as e:
            logger.warning(f"Error calculating file hash: {e}")
            # Продолжаем без хеша

        # Определяем количество потраченных токенов
        tokens_used = 0
        if solution_found and token_message_parts:
            # Пытаемся извлечь количество токенов из сообщений
            for token_msg in token_message_parts:
                if isinstance(token_msg, str) and "Списан 1 токен" in token_msg:
                    tokens_used = 1
                    break
        
        # Формируем текст решения - БЕЗОПАСНО
        solution_text = None
        if solution and hasattr(solution, 'descriptions') and solution.descriptions:
            try:
                if isinstance(solution.descriptions, list):
                    solution_text = "\n".join(str(desc) for desc in solution.descriptions if desc)
                else:
                    solution_text = str(solution.descriptions)
                # Обрезаем если слишком длинный
                if solution_text and len(solution_text) > 5000:
                    solution_text = solution_text[:5000] + "..."
            except Exception as e:
                logger.warning(f"Error processing solution.descriptions: {e}")
                solution_text = "Ошибка обработки решения"
        
        # Получаем информацию об ошибке - БЕЗОПАСНО
        error_code = None
        error_description = None
        
        if solution:
            try:
                if hasattr(solution, 'error_code') and solution.error_code:
                    error_code = str(solution.error_code)[:500]  # Обрезаем
            except Exception as e:
                logger.warning(f"Error processing error_code: {e}")
                
            try:
                if hasattr(solution, 'panic_string') and solution.panic_string:
                    error_description = str(solution.panic_string)[:1000]  # Обрезаем
            except Exception as e:
                logger.warning(f"Error processing panic_string: {e}")
        
        # Получаем информацию об устройстве - БЕЗОПАСНО
        device_model = None
        ios_version = None
        
        if phone_model_info:
            try:
                if hasattr(phone_model_info, 'model') and phone_model_info.model:
                    device_model = str(phone_model_info.model)[:200]  # Обрезаем
            except Exception as e:
                logger.warning(f"Error processing device_model: {e}")
                
            try:
                if hasattr(phone_model_info, 'ios_version') and phone_model_info.ios_version:
                    ios_version = str(phone_model_info.ios_version)[:100]  # Обрезаем
            except Exception as e:
                logger.warning(f"Error processing ios_version: {e}")

        # Безопасная обработка filename и размера
        if original_filename:
            original_filename = str(original_filename)[:500]  # Обрезаем
        if file_size and not isinstance(file_size, int):
            try:
                file_size = int(file_size)
            except:
                file_size = 0

        # Логируем параметры для отладки
        logger.info(f"Saving analysis with params: user_id={user.user_id}, "
                   f"device_model='{device_model}', ios_version='{ios_version}', "
                   f"original_filename='{original_filename}', file_type='{file_type}', "
                   f"file_size={file_size}, error_code='{error_code}', "
                   f"solution_found={solution_found}, tokens_used={tokens_used}, "
                   f"file_id='{file_id}'")

        # Сохраняем в базу данных
        if orm and orm.async_sessionmaker:
            async with orm.async_sessionmaker() as session:
                from database.repo.analysis_history import AnalysisHistoryRepo
                history_repo = AnalysisHistoryRepo(session)
                
                await history_repo.create_analysis_record(
                    user_id=int(user.user_id),
                    device_model=device_model,
                    ios_version=ios_version,
                    original_filename=original_filename,
                    file_type=str(file_type),
                    file_size=file_size,
                    file_path=file_id,  # Сохраняем file_id в поле file_path
                    file_hash=file_hash,  # Сохраняем хеш файла
                    error_code=error_code,
                    error_description=error_description,
                    solution_text=solution_text,
                    is_solution_found=bool(solution_found),
                    tokens_used=int(tokens_used)
                )
                
            logger.info(f"Analysis saved to history for user {user.user_id}")
        else:
            logger.error("ORM or async_sessionmaker not available for saving history")
        
    except Exception as e:
        logger.error(f"Error saving analysis to history for user {user.user_id}: {e}")
        # Не прерываем основной процесс анализа при ошибке сохранения истории


async def _cleanup_temp_files(response_solutions):
    """Очищает временные файлы"""
    if response_solutions and hasattr(response_solutions, 'file_path_to_delete'):
        file_path = getattr(response_solutions, 'file_path_to_delete', None)
        if file_path:
            try:
                remove_file(file_path)
            except Exception as e:
                logger.warning(f"Could not remove temp file {file_path}: {e}") 