"""
Обработчики callback запросов для анализатора файлов
"""
import re
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InaccessibleMessage
from aiogram.utils.i18n import I18n

from database.models import User
from services.telegram.misc.callbacks import ShowDiagnosticsCallback, FullButtonCallback
from services.telegram.misc.keyboards import Keyboards
from services.telegram.template.analyzer import template_about_analysis_result, template_about_analysis_result_header, SolutionAboutError
from services.telegram.schemas.analyzer import ModelPhone
from .utils import desanitize_callback_data

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(ShowDiagnosticsCallback.filter())
async def show_detailed_diagnostics(callback: CallbackQuery, i18n: I18n, user: User):
    """Отправляет подробные шаги диагностики и удаляет кнопку."""
    lang = user.lang

    diagnostic_parts = [
        i18n.gettext("""
Что проверить в первую очередь (по функционалу):
 1. Работоспособность Wi-Fi и модема — часто связаны с межплатными обрывами или RF-модулем.
 2. Функции вибрации (Taptic Engine) — обратите внимание, работает ли вибрация корректно, без посторонних звуков.
 3. Проверка компаса и гироскопа — зайдите в соответствующие системные приложения или через сторонние тестеры. При сбоях — возможна проблема с передним шлейфом или контроллерами.
 4. Звук и запись микрофона — тестируем диктофон, аудио в видео, звонках.
 5. Автоповорот экрана — косвенно указывает на работу гироскопа и акселерометра.
 6. Работа датчиков освещённости, барометра и приближения — особенно после ударов или попадания влаги.
 7. Функция зарядки и подключение к ПК — может указывать на сбой контроллера Lightning и Type-C
        """, locale=lang),
        i18n.gettext("""
На что обратить внимание при осмотре:
 1. Следы окислов на шлейфах и коннекторах (особенно нижний шлейф, шлейф беспроводной зарядки, разъём Taptic Engine).
 2. Наличие мелких сколов, трещин или выгибов платы — это может указывать на внутренние межслойные обрывы.
        """, locale=lang),
        i18n.gettext("""
Что подкинуть для проверки:
 1. Полностью рабочий дисплей с передним шлейфом — для исключения проблем с датчиками освещения, компасом и гироскопом.
 2. Заведомо исправный нижний шлейф с вибромотором и Lightning (Type-C) -коннектором.
 3. Заведомо рабочий корпус в сборе с кнопками, динамиками и периферией — чтобы исключить влияние внешних компонентов.
 4. Другой аккумулятор — при нестабильной загрузке или странных перезагрузках.
 5. Оригинальный шлейф беспроводной зарядки — даже если сбой в другой части, этот модуль часто мешает другим.
        """, locale=lang),
        i18n.gettext("""
Важно:
При скрытых межплатных обрывах, повреждениях слоя платы или повреждениях способе попадании влаги, симптомы могут проявляться в неожиданных узлах — например, неработающий компас может быть следствием неисправного вибромотора или барометра. Поэтому при отсутствии чёткой ошибки обязательно проверяйте всю периферию в сборе, шаг за шагом подкидывая исправные модули.
        """, locale=lang),
        i18n.gettext(
            "Желаем удачи в ремонте! Если появятся уточняющие данные по этой ошибке — бот обязательно подскажет решение.",
            locale=lang),
    ]

    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_reply_markup()
            for content in diagnostic_parts:
                await callback.message.answer(text=content, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Could not send diagnostics: {e}")

    await callback.answer()


@router.callback_query(FullButtonCallback.filter(F.action == "show_full"))
async def handle_show_full_answer(
    callback_query: CallbackQuery,
    callback_data: FullButtonCallback,
    user: User,
    state: FSMContext,
    i18n: I18n,
):
    """Обработчик кнопки "Полный ответ" """
    await callback_query.answer()

    error_code = desanitize_callback_data(callback_data.error_code)
    model_id = callback_data.model
    
    data = await state.get_data()
    key = f"full_answer_{user.user_id}_{error_code}_{model_id}"
    
    if key not in data:
        key = f"full_answer_{user.user_id}_{callback_data.error_code}_{model_id}"
    
    stored_data = data.get(key)

    if not stored_data:
        await callback_query.answer(
            i18n.gettext("Полный ответ больше недоступен или истек срок его хранения.", locale=user.lang), 
            show_alert=True
        )
        try:
            if callback_query.message and not isinstance(callback_query.message, InaccessibleMessage):
                await callback_query.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            logger.warning(f"Could not edit reply markup: {e}")
        return

    # Извлекаем данные
    full_descriptions = stored_data.get("descriptions")
    full_links = stored_data.get("links", [])
    error_code = stored_data.get("error_code")
    phone_model_name = stored_data.get("phone_model_name")
    phone_model_version = stored_data.get("phone_model_version")
    phone_ios_version = stored_data.get("phone_ios_version")
    date_of_failure = stored_data.get("date_of_failure")

    # Создаем объекты для шаблонов
    phone_for_header = ModelPhone(
        model=phone_model_name,
        version=phone_model_version,
        ios_version=phone_ios_version
    )
    
    solution_for_user_header = SolutionAboutError(
        descriptions=[], 
        links=[], 
        date_of_failure=date_of_failure,
        error_code=error_code,
        is_mini_response_shown=False, 
        has_full_solution_available=False 
    )
    
    user_header_text = template_about_analysis_result_header(
        phone=phone_for_header, 
        solution_about_error=solution_for_user_header,
        i18n=i18n,
        lang=user.lang
    )
    
    solution_for_user_body = SolutionAboutError(
        descriptions=full_descriptions if full_descriptions else [],
        links=full_links if full_links else [],
        date_of_failure=date_of_failure, 
        error_code=error_code,
        is_full=True 
    )
    
    user_body_text = template_about_analysis_result(
        solution_for_user_body,
        i18n=i18n,
        lang=user.lang
    )
    
    user_message_text = f"{user_header_text}\n{user_body_text}"
    
    # Отправляем полный ответ
    if callback_query.bot:
        try:
            await callback_query.bot.send_message(
                chat_id=callback_query.from_user.id, 
                text=user_message_text
            )
        except Exception as e:
            logger.error(f"Could not send full answer: {e}")
    
    # Создаем краткую информацию для консультации
    short_info = _create_short_info_for_consultation(user_message_text, i18n, user.lang)
    
    consultation_keyboard_after_full = Keyboards.create_consultation_button(i18n, user.lang, short_info)
    consultation_message_text_after_full = i18n.gettext(
        "Если вам нужна дополнительная помощь специалиста или вы хотите обсудить полученный ответ, "
        "нажмите кнопку ниже. 👇\n\n"
        "Пожалуйста, не забудьте отправить файл лога или скриншот в следующем сообщении в чат с консультантом, "
        "чтобы он мог быстрее вам помочь.",
        locale=user.lang
    )
    
    if callback_query.message and not isinstance(callback_query.message, InaccessibleMessage):
        try:
            await callback_query.message.answer(
                text=consultation_message_text_after_full, 
                reply_markup=consultation_keyboard_after_full
            )
            await callback_query.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            logger.warning(f"Could not send consultation message or edit markup: {e}")

    # Отправляем уведомление админу
    from .feedback import send_admin_notification_for_full_answer
    await send_admin_notification_for_full_answer(callback_query, stored_data, i18n, user)

    # Удаляем данные из состояния
    if key in data:
        del data[key]
        await state.set_data(data)


def _create_short_info_for_consultation(user_message_text: str, i18n: I18n, lang: str) -> str:
    """Создает краткую информацию для кнопки консультации"""
    cleaned_text = re.sub(r'<[^>]+>', '', user_message_text)
    lines = cleaned_text.split('\n')
    
    device_info_header = i18n.gettext("Device Information:", locale=lang)
    model_label = i18n.gettext("📱 Модель:", locale=lang)
    ios_label = i18n.gettext("🛠️ Версия iOS:", locale=lang)
    date_label = i18n.gettext("📅 Дата сбоя:", locale=lang)
    errors_label = i18n.gettext("Найденные ошибки и рекомендации по ремонту:", locale=lang)
    
    device_info_header_en = "Device Information:"
    model_label_en = "📱 Model:"
    ios_label_en = "🛠️ iOS Version:"
    date_label_en = "📅 Failure Date:"
    errors_label_en = "Found errors and repair recommendations:"
    
    structured_message = [device_info_header if lang == 'ru' else device_info_header_en]
    
    # Извлекаем информацию об устройстве
    for line in lines:
        if any(label in line for label in [model_label, model_label_en]):
            structured_message.append(line.strip())
            break
    
    for line in lines:
        if any(label in line for label in [ios_label, ios_label_en]):
            structured_message.append(line.strip())
            break
    
    for line in lines:
        if any(label in line for label in [date_label, date_label_en]):
            structured_message.append(line.strip())
            break
    
    structured_message.append("")
    
    # Извлекаем ошибки
    error_section = False
    error_lines = []
    for line in lines:
        if any(label in line for label in [errors_label, errors_label_en]):
            error_section = True
            error_lines.append(line.strip())
            continue
        if error_section:
            if "token" in line.lower() or "токен" in line.lower() or "subscription" in line.lower() or "подписк" in line.lower():
                break
            if not line.strip() and not error_lines:
                continue
            error_lines.append(line.strip())
    
    structured_message.extend(error_lines)
    short_info = "\n".join(structured_message)
    
    max_text_len = 1500
    if len(short_info) > max_text_len:
        short_info = short_info[:max_text_len] + "..."
        
    return short_info 