import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InaccessibleMessage
from aiogram.utils.i18n import I18n
from aiogram.enums import ParseMode
from typing import Union
import urllib.parse

from database.database import ORM
from database.models import User
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import (
    AnalysisHistoryCallback, AnalysisDetailCallback, 
    AnalysisHistoryPagination, AnalysisFilterCallback
)
from services.telegram.misc.keyboards import Keyboards

logger = logging.getLogger(__name__)
router = Router()

# Применяем фильтры ко всем хэндлерам в этом роутере
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


@router.message(
    (F.text.contains("Мои анализы") | F.text.contains("My Analyses")) & 
    F.text.contains("📊")
)
async def show_analysis_history_main(message: Message, user: User, orm: ORM, i18n: I18n):
    """Показать главное меню истории анализов."""
    try:
        if not orm or not hasattr(orm, 'analysis_history_repo') or not orm.analysis_history_repo or not orm.async_sessionmaker:
            await message.answer(
                i18n.gettext("❌ Сервис истории анализов временно недоступен", locale=user.lang)
            )
            return

        # Получаем статистику
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            stats = await history_repo.get_user_statistics(user.user_id)
        
        text = i18n.gettext(
            "📊 *История анализов*\n\n"
            "📈 *Ваша статистика:*\n"
            "• Всего анализов: {total}\n"
            "• Успешных: {successful} ✅\n"
            "• Неудачных: {failed} ❌\n"
            "• Процент успеха: {success_rate:.1f}%\n",
            locale=user.lang
        ).format(
            total=stats["total_analyses"],
            successful=stats["successful_analyses"],
            failed=stats["failed_analyses"],
            success_rate=stats["success_rate"]
        )
        
        # Добавляем статистику по типам файлов
        if stats["file_types"]:
            text += i18n.gettext("📄 *По типам файлов:*\n", locale=user.lang)
            for file_type, count in stats["file_types"].items():
                emoji = {
                    "ips": "📄",
                    "txt": "📝",
                    "photo": "🖼️", 
                    "json": "🔧"
                }.get(file_type, "📄")
                
                # Переводим типы файлов
                file_type_display = {
                    "ips": ".ips",
                    "txt": ".txt", 
                    "photo": i18n.gettext("фото", locale=user.lang),
                    "json": ".json"
                }.get(file_type, file_type)
                
                text += f"• {emoji} {file_type_display}: {count}\n"
        
        text += i18n.gettext(
            "\n_Исходные файлы хранятся в течение 30 дней, затем автоматически удаляются._\n"
            "_В Telegram файлы могут стать недоступными раньше срока._",
            locale=user.lang
        )
        
        keyboard = Keyboards.analysis_history_main(i18n, user, stats["total_analyses"])
        
        await message.answer(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error showing analysis history main: {e}")
        await message.answer(
            i18n.gettext("❌ Произошла ошибка при загрузке истории анализов", locale=user.lang)
        )


@router.callback_query(AnalysisHistoryCallback.filter(F.action == "list"))
async def show_analysis_list(
    callback: CallbackQuery, 
    callback_data: AnalysisHistoryCallback,
    user: User, 
    orm: ORM, 
    i18n: I18n
):
    """Показать список анализов с пагинацией."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        page = callback_data.page or 0
        page_size = 5  # Увеличиваем до 5 элементов на странице
        
        # Получаем список анализов
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            history_data = await history_repo.get_user_history(
                user_id=user.user_id,
                page=page,
                page_size=page_size
            )
        
        analyses = history_data["analyses"]
        total_pages = history_data["total_pages"]
        
        if not analyses:
            text = i18n.gettext(
                "📭 *У вас пока нет анализов*\n\n"
                "Отправьте файл для анализа, чтобы он появился в истории!",
                locale=user.lang
            )
            keyboard = Keyboards.analysis_history_main(i18n, user)
        else:
            text = i18n.gettext(
                "📊 *Ваши последние анализы:*\n\n", 
                locale=user.lang
            )
            
            # Формируем список анализов
            for i, analysis in enumerate(analyses, 1):
                number = page * page_size + i
                device_emoji = "📱" if analysis.device_model and ("iPhone" in analysis.device_model or "iPad" in analysis.device_model) else "📱"
                
                file_type_emoji = {
                    "ips": "📄",
                    "txt": "📝", 
                    "photo": "🖼️",
                    "json": "🔧"
                }.get(analysis.file_type, "📄")
                
                status_text = i18n.gettext("✅ Solution found", locale=user.lang) if analysis.is_solution_found else i18n.gettext("❌ Solution not found", locale=user.lang)
                
                # Безопасное экранирование для Markdown
                device_name = analysis.device_model or i18n.gettext("Неизвестное устройство", locale=user.lang)
                device_name = device_name.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
                
                ios_version = analysis.ios_version or ""
                ios_version = ios_version.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
                
                # Правильное отображение типа файла
                file_type_display = {
                    "ips": ".ips",
                    "txt": ".txt", 
                    "photo": "photo",
                    "json": ".json"
                }.get(analysis.file_type, analysis.file_type or "file")
                
                # Форматируем дату
                date_str = analysis.created_at.strftime("%d.%m.%Y, %H:%M")
                
                text += i18n.gettext(
                    "   {number}. {device_emoji} {device}, {ios}\n"
                    "      {file_emoji} Тип: {file_type}\n"
                    "      📅 {date}\n"
                    "      {status}\n\n",
                    locale=user.lang
                ).format(
                    number=number,
                    device_emoji=device_emoji,
                    device=device_name,
                    ios=ios_version,
                    file_emoji=file_type_emoji,
                    file_type=file_type_display,
                    date=date_str,
                    status=status_text
                )
            
            # Исправляем отображение пагинации - убираем текст
            # current_start = page * page_size + 1
            # current_end = min((page + 1) * page_size, history_data["total_count"])
            
            # text += i18n.gettext(
            #     "\\[{current_start}\\-{current_end} из {total}\\] ◀️ ▶️",
            #     locale=user.lang
            # ).format(
            #     current_start=current_start,
            #     current_end=current_end,
            #     total=history_data["total_count"]
            # )
            
            keyboard = Keyboards.analysis_history_list(
                i18n, user, analyses, page, total_pages
            )
        
        try:
            if callback.message and hasattr(callback.message, 'edit_text'):
                await callback.message.edit_text(  # type: ignore
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing analysis list: {e}")
        await callback.answer(
            i18n.gettext("❌ Произошла ошибка при загрузке списка", locale=user.lang)
        )


@router.callback_query(AnalysisDetailCallback.filter(F.action == "view"))
async def show_analysis_detail(
    callback: CallbackQuery,
    callback_data: AnalysisDetailCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Показать детальную информацию об анализе."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            analysis = await history_repo.get_analysis_by_id(
                callback_data.analysis_id, user.user_id
            )
        
        if not analysis:
            await callback.answer(
                i18n.gettext("❌ Анализ не найден", locale=user.lang)
            )
            return
            
        device_emoji = "📱" if analysis.device_model and ("iPhone" in analysis.device_model or "iPad" in analysis.device_model) else "📱"
        date_str = analysis.created_at.strftime("%d.%m.%Y, %H:%M")
        
        text = i18n.gettext(
            "{device_emoji} *{device}, {ios}*\n"
            "📄 Файл: {filename}\n"
            "📅 Дата анализа: {date}\n\n",
            locale=user.lang
        ).format(
            device_emoji=device_emoji,
            device=analysis.device_model or i18n.gettext("Неизвестное устройство", locale=user.lang),
            ios=analysis.ios_version or "",
            filename=analysis.original_filename or i18n.gettext("файл", locale=user.lang),
            date=date_str
        )
        
        if analysis.is_solution_found and analysis.solution_text:
            text += i18n.gettext("📋 *Решение:*\n{solution}\n\n", locale=user.lang).format(
                solution=analysis.solution_text
            )
        else:
            text += i18n.gettext("❌ *Решение не найдено*\n\n", locale=user.lang)
            
        if analysis.tokens_used > 0:
            text += i18n.gettext("💰 Потрачено токенов: {tokens}\n", locale=user.lang).format(
                tokens=analysis.tokens_used
            )
        
        # Проверяем возможность повторного анализа
        async with orm.async_sessionmaker() as session:
            history_repo = AnalysisHistoryRepo(session)
            can_repeat, error_message = await history_repo.can_repeat_analysis(
                analysis.id, user.user_id
            )
            
            attempts_info = None
            if analysis.repeat_attempts > 0:
                attempts_info = i18n.gettext(
                    "🔄 Круг {current} из 2", 
                    locale=user.lang
                ).format(current=analysis.repeat_attempts)
        
        keyboard = Keyboards.analysis_detail(i18n, user, analysis, can_repeat, attempts_info)
        
        try:
            if callback.message and hasattr(callback.message, 'edit_text'):
                await callback.message.edit_text(  # type: ignore
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing analysis detail: {e}")
        await callback.answer(
            i18n.gettext("❌ Произошла ошибка при загрузке анализа", locale=user.lang)
        )


@router.callback_query(AnalysisDetailCallback.filter(F.action == "delete"))
async def confirm_delete_analysis(
    callback: CallbackQuery,
    callback_data: AnalysisDetailCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Подтверждение удаления анализа."""
    text = i18n.gettext(
        "❗️ *Подтверждение удаления*\n\n"
        "Вы уверены, что хотите удалить этот анализ?\n"
        "Это действие нельзя отменить.",
        locale=user.lang
    )
    
    keyboard = Keyboards.analysis_delete_confirm(i18n, user, callback_data.analysis_id)
    
    try:
        if callback.message and hasattr(callback.message, 'edit_text'):
            await callback.message.edit_text(  # type: ignore
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
    await callback.answer()


@router.callback_query(AnalysisDetailCallback.filter(F.action == "confirm_delete"))
async def delete_analysis(
    callback: CallbackQuery,
    callback_data: AnalysisDetailCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Удалить анализ."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            success = await history_repo.delete_analysis(
                callback_data.analysis_id, user.user_id
            )
        
        if success:
            text = i18n.gettext("✅ Анализ успешно удален", locale=user.lang)
            # Возвращаемся к списку
            await show_analysis_list(
                callback, 
                AnalysisHistoryCallback(action="list", page=0),
                user, orm, i18n
            )
        else:
            await callback.answer(
                i18n.gettext("❌ Не удалось удалить анализ", locale=user.lang)
            )
            
    except Exception as e:
        logger.error(f"Error deleting analysis: {e}")
        await callback.answer(
            i18n.gettext("❌ Произошла ошибка при удалении", locale=user.lang)
        )



@router.callback_query(AnalysisHistoryCallback.filter(F.action == "main"))
async def return_to_main(
    callback: CallbackQuery,
    callback_data: AnalysisHistoryCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Вернуться к главному меню истории анализов."""
    try:
        if not orm or not hasattr(orm, 'analysis_history_repo') or not orm.analysis_history_repo or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис истории анализов временно недоступен", locale=user.lang),
                show_alert=True
            )
            return

        # Получаем статистику
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            stats = await history_repo.get_user_statistics(user.user_id)
        
        text = i18n.gettext(
            "📊 *История анализов*\n\n"
            "📈 *Ваша статистика:*\n"
            "• Всего анализов: {total}\n"
            "• Успешных: {successful} ✅\n"
            "• Неудачных: {failed} ❌\n"
            "• Процент успеха: {success_rate:.1f}%\n",
            locale=user.lang
        ).format(
            total=stats["total_analyses"],
            successful=stats["successful_analyses"],
            failed=stats["failed_analyses"],
            success_rate=stats["success_rate"]
        )
        
        # Добавляем статистику по типам файлов
        if stats["file_types"]:
            text += i18n.gettext("📄 *По типам файлов:*\n", locale=user.lang)
            for file_type, count in stats["file_types"].items():
                emoji = {
                    "ips": "📄",
                    "txt": "📝",
                    "photo": "🖼️", 
                    "json": "🔧"
                }.get(file_type, "📄")
                
                # Переводим типы файлов
                file_type_display = {
                    "ips": ".ips",
                    "txt": ".txt", 
                    "photo": i18n.gettext("фото", locale=user.lang),
                    "json": ".json"
                }.get(file_type, file_type)
                
                text += f"• {emoji} {file_type_display}: {count}\n"
        
        text += i18n.gettext(
            "\n_Исходные файлы хранятся в течение 30 дней, затем автоматически удаляются._\n"
            "_В Telegram файлы могут стать недоступными раньше срока._",
            locale=user.lang
        )
        
        keyboard = Keyboards.analysis_history_main(i18n, user, stats["total_analyses"])
        
        try:
            if callback.message and hasattr(callback.message, 'edit_text'):
                await callback.message.edit_text(  # type: ignore
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error returning to main: {e}")
        await callback.answer(
            i18n.gettext("❌ Произошла ошибка при возврате в главное меню", locale=user.lang)
        )


@router.callback_query(AnalysisHistoryPagination.filter())
async def handle_history_pagination(
    callback: CallbackQuery,
    callback_data: AnalysisHistoryPagination,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Обработка пагинации истории анализов с циклической навигацией."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        page = callback_data.page
        page_size = 5  # Размер страницы 5
        
        # Получаем общее количество анализов для корректной циклической навигации
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            history_data = await history_repo.get_user_history(
                user_id=user.user_id,
                page=0,  # Сначала получаем первую страницу для определения общего количества
                page_size=page_size
            )
        
        total_pages = history_data["total_pages"]
        
        # Если запрошенная страница выходит за пределы, корректируем (циклическая навигация)
        if page >= total_pages and total_pages > 0:
            page = 0  # Переход на первую страницу
        elif page < 0:
            page = max(0, total_pages - 1)  # Переход на последнюю страницу
        
        # Создаем новый callback для отображения списка с корректной страницей
        history_callback = AnalysisHistoryCallback(action="list", page=page)
        await show_analysis_list(callback, history_callback, user, orm, i18n)
        
    except Exception as e:
        logger.error(f"Error handling pagination: {e}")
        await callback.answer(
            i18n.gettext("❌ Ошибка при переключении страниц", locale=user.lang)
        )


@router.callback_query(AnalysisDetailCallback.filter(F.action == "download"))
async def download_analysis_file(
    callback: CallbackQuery,
    callback_data: AnalysisDetailCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Скачать файл анализа."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            analysis = await history_repo.get_analysis_by_id(
                callback_data.analysis_id, user.user_id
            )
        
        if not analysis:
            await callback.answer(
                i18n.gettext("❌ Анализ не найден", locale=user.lang)
            )
            return
            
        # Проверяем наличие file_id
        if analysis.file_path and analysis.file_path.strip():
            try:
                # Отправляем файл по file_id (file_path содержит file_id)
                if analysis.file_type == "photo":
                    # Для фото используем send_photo
                    if callback.message and hasattr(callback.message, 'answer_photo'):
                        await callback.message.answer_photo(  # type: ignore
                            photo=analysis.file_path,  # file_id
                            caption=i18n.gettext("📄 Исходный файл анализа", locale=user.lang)
                        )
                else:
                    # Для документов используем send_document
                    if callback.message and hasattr(callback.message, 'answer_document'):
                        await callback.message.answer_document(  # type: ignore
                            document=analysis.file_path,  # file_id
                            caption=i18n.gettext("📄 Исходный файл анализа", locale=user.lang)
                        )
                
                await callback.answer(
                    i18n.gettext("💾 Файл отправлен", locale=user.lang)
                )
                
            except Exception as e:
                logger.error(f"Error sending file by file_id: {e}")
                await callback.answer(
                    i18n.gettext("💾 Файл больше недоступен (ссылка устарела)", locale=user.lang),
                    show_alert=True
                )
        else:
            await callback.answer(
                i18n.gettext("💾 Файл больше недоступен (ссылка устарела)", locale=user.lang),
                show_alert=True
            )
            
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        await callback.answer(
            i18n.gettext("❌ Ошибка при скачивании файла", locale=user.lang)
        )


@router.callback_query(AnalysisDetailCallback.filter(F.action == "share"))
async def share_analysis(
    callback: CallbackQuery,
    callback_data: AnalysisDetailCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Поделиться анализом."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            analysis = await history_repo.get_analysis_by_id(
                callback_data.analysis_id, user.user_id
            )
        
        if not analysis:
            await callback.answer(
                i18n.gettext("❌ Анализ не найден", locale=user.lang)
            )
            return
            
        # Формируем текст для шаринга
        device_info = f"{analysis.device_model}, {analysis.ios_version}" if analysis.device_model else i18n.gettext("Неизвестное устройство", locale=user.lang)
        date_str = analysis.created_at.strftime("%d.%m.%Y")
        status = i18n.gettext("✅ Solution found", locale=user.lang) if analysis.is_solution_found else i18n.gettext("❌ Solution not found", locale=user.lang)
        
        share_text = i18n.gettext(
            "📱 *Device Analysis*\n\n"
            "🔧 Device: {device}\n"
            "📅 Analysis date: {date}\n"
            "📄 File type: {file_type}\n"
            "🔍 Result: {status}\n\n",
            locale=user.lang
        ).format(
            device=device_info,
            date=date_str,
            file_type=analysis.file_type,
            status=status
        )
        
        # Добавляем решение если оно есть
        if analysis.is_solution_found and analysis.solution_text:
            share_text += i18n.gettext("📋 Solution:\n{solution}\n\n", locale=user.lang).format(
                solution=analysis.solution_text
            )
        
        share_text += i18n.gettext("Analysis performed with @PanicDoctorBot", locale=user.lang)
        
        # Создаем кнопку для выбора получателя (как в консультации)
        max_text_len = 1200
        if len(share_text) > max_text_len:
            share_text = share_text[:max_text_len] + "..."
        
        url_encoded_text = urllib.parse.quote(share_text)
        
        # Проверяем длину URL
        if len(url_encoded_text) > 2000:
            max_text_len = int(max_text_len * 0.8)
            share_text = share_text[:max_text_len] + "..."
            url_encoded_text = urllib.parse.quote(share_text)
        
        # Создаем кнопку для выбора чата
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        
        # Кнопка для выбора чата (использует стандартный механизм Telegram)
        builder.button(
            text=i18n.gettext("📤 Поделиться в чате", locale=user.lang),
            switch_inline_query=share_text
        )
        
        builder.button(
            text=i18n.gettext("⬅️ Назад", locale=user.lang),
            callback_data=AnalysisDetailCallback(analysis_id=analysis.id, action="view").pack()
        )
        
        keyboard = builder.as_markup()
        
        # Отправляем сообщение с предпросмотром и кнопкой поделиться
        preview_text = i18n.gettext(
            "📤 *Поделиться анализом*\n\n"
            "Предварительный просмотр сообщения:\n\n", 
            locale=user.lang
        ) + share_text
        
        try:
            if callback.message and hasattr(callback.message, 'edit_text'):
                await callback.message.edit_text(  # type: ignore
                    preview_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error sharing analysis: {e}")
        await callback.answer(
            i18n.gettext("❌ Ошибка при отправке", locale=user.lang)
        )


@router.callback_query(AnalysisDetailCallback.filter(F.action == "repeat"))
async def repeat_analysis(
    callback: CallbackQuery,
    callback_data: AnalysisDetailCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Повторить анализ автоматически."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            
            # Проверяем лимит попыток
            can_repeat, error_message = await history_repo.can_repeat_analysis(
                callback_data.analysis_id, user.user_id
            )
            
            if not can_repeat:
                # Показываем сообщение о блокировке
                text = i18n.gettext(
                    "⏰ *Повторные круги ограничены*\n\n{message}\n\n"
                    "Кнопка повторного анализа будет заблокирована до истечения времени ожидания.",
                    locale=user.lang
                ).format(message=error_message)
                
                await callback.answer(
                    error_message,
                    show_alert=True
                )
                return
            
            analysis = await history_repo.get_analysis_by_id(
                callback_data.analysis_id, user.user_id
            )
        
        if not analysis:
            await callback.answer(
                i18n.gettext("❌ Анализ не найден", locale=user.lang)
            )
            return
            
        # Проверяем наличие file_id для повторного анализа
        if not analysis.file_path or not analysis.file_path.strip():
            await callback.answer(
                i18n.gettext("🔄 Файл больше недоступен, отправьте файл заново", locale=user.lang),
                show_alert=True
            )
            return
            
        # Отправляем сообщение о начале анализа
        if not callback.message or not hasattr(callback.message, 'answer'):
            await callback.answer(
                i18n.gettext("❌ Произошла ошибка", locale=user.lang)
            )
            return
            
        wait_message = await callback.message.answer(  # type: ignore
            i18n.gettext("🔄 Запускаю повторный анализ...", locale=user.lang)
        )
        
        try:
            # Получаем бота
            from aiogram import Bot
            bot = callback.bot
            if not bot or not isinstance(bot, Bot):
                raise Exception("Bot not available")
            
            # Создаем объект файла для повторного анализа и автоматически запускаем анализ
            if analysis.file_type == "photo":
                # Для фото отправляем как фото
                sent_message = await bot.send_photo(
                    chat_id=callback.message.chat.id,  # type: ignore
                    photo=analysis.file_path,
                    caption="🔄 Re-analysis"
                )
            else:
                # Для документов отправляем как документ
                sent_message = await bot.send_document(
                    chat_id=callback.message.chat.id,  # type: ignore
                    document=analysis.file_path,
                    caption="🔄 Re-analysis"
                )
            
            # Импортируем и запускаем главный обработчик анализа
            from services.telegram.handlers.analyzer.handlers import document_analyze
            from aiogram.fsm.context import FSMContext
            from aiogram.fsm.storage.memory import MemoryStorage
            from config import Environ
            
            # Создаем временный FSM контекст
            from aiogram.fsm.storage.base import StorageKey
            storage = MemoryStorage()
            storage_key = StorageKey(bot_id=bot.id, chat_id=callback.message.chat.id, user_id=user.user_id)  # type: ignore
            state = FSMContext(storage=storage, key=storage_key)
            env = Environ()
            
            # Удаляем сообщение ожидания перед запуском анализа
            from services.telegram.misc.utils import delete_message
            if wait_message and bot:
                await delete_message(bot, wait_message)  # type: ignore
            
            # Увеличиваем счетчик попыток ДО запуска анализа
            async with orm.async_sessionmaker() as session:
                history_repo = AnalysisHistoryRepo(session)
                await history_repo.increment_repeat_attempts(
                    callback_data.analysis_id, user.user_id
                )
                
                # Получаем текущее количество попыток
                current_analysis = await history_repo.get_analysis_by_id(
                    callback_data.analysis_id, user.user_id
                )
                current_attempts = current_analysis.repeat_attempts if current_analysis else 0
            
            # Запускаем полный анализ файла
            await document_analyze(sent_message, user, orm, i18n, state, env)
            
            # Проверяем результат и показываем информацию о кругах
            async with orm.async_sessionmaker() as session:
                history_repo = AnalysisHistoryRepo(session)
                # Получаем результат анализа
                updated_analysis = await history_repo.get_analysis_by_id(
                    callback_data.analysis_id, user.user_id
                )
                
                if updated_analysis:
                    if updated_analysis.is_solution_found:
                        # Если анализ успешен, сбрасываем счетчик
                        await history_repo.reset_repeat_attempts(
                            callback_data.analysis_id, user.user_id
                        )
                    else:
                        # Показываем информацию о количестве кругов для неуспешного анализа
                        attempts_left = 2 - current_attempts
                        if attempts_left > 0:
                            attempt_info = i18n.gettext(
                                "🔄 Круг {current} из 2", 
                                locale=user.lang
                            ).format(current=current_attempts)
                            
                            if hasattr(callback.message, 'answer'):
                                await callback.message.answer(  # type: ignore
                                    f"{attempt_info}\n"
                                    f"{i18n.gettext('Осталось кругов: {attempts_left}', locale=user.lang).format(attempts_left=attempts_left)}"
                                )
                        elif attempts_left == 0:
                            # Достигнут лимит
                            if hasattr(callback.message, 'answer'):
                                await callback.message.answer(  # type: ignore
                                    i18n.gettext(
                                        "⏰ Достигнут лимит повторных кругов для этого файла. "
                                        "Анализ будет заблокирован на 3 часа.", 
                                        locale=user.lang
                                    )
                                )
            
            # Удаляем служебное сообщение с файлом
            try:
                await delete_message(bot, sent_message)  # type: ignore
            except:
                pass
            
            await callback.answer(
                i18n.gettext("✅ Анализ завершен", locale=user.lang)
            )
                
        except Exception as e:
            logger.error(f"Error in re-analysis process: {e}")
            try:
                if 'bot' in locals() and 'wait_message' in locals() and bot:
                    await delete_message(bot, wait_message)  # type: ignore
            except:
                pass
            await callback.answer(
                i18n.gettext("🔄 Файл больше недоступен, отправьте файл заново", locale=user.lang),
                show_alert=True
            )
            
    except Exception as e:
        logger.error(f"Error repeating analysis: {e}")
        await callback.answer(
            i18n.gettext("❌ Произошла ошибка", locale=user.lang)
        )




@router.callback_query(AnalysisHistoryCallback.filter(F.action == "filter"))
async def show_filter_menu(
    callback: CallbackQuery,
    callback_data: AnalysisHistoryCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Показать меню фильтров."""
    text = i18n.gettext(
        "🔍 *Фильтры для истории анализов*\n\n"
        "Выберите критерий для фильтрации:",
        locale=user.lang
    )
    
    keyboard = Keyboards.analysis_filter_menu(i18n, user)
    
    try:
        if callback.message and hasattr(callback.message, 'edit_text'):
            await callback.message.edit_text(  # type: ignore
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
    await callback.answer()


@router.callback_query(AnalysisFilterCallback.filter(F.filter_type == "file_type"))
async def show_file_type_filter(
    callback: CallbackQuery,
    callback_data: AnalysisFilterCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Показать фильтр по типам файлов."""
    # Если есть filter_value, то это применение фильтра, а не показ меню
    if callback_data.filter_value:
        await apply_filter(callback, callback_data, user, orm, i18n)
        return
        
    text = i18n.gettext(
        "📄 *Фильтр по типу файлов*\n\n"
        "Выберите тип файлов:",
        locale=user.lang
    )
    
    keyboard = Keyboards.analysis_file_type_filter(i18n, user)
    
    try:
        if callback.message and hasattr(callback.message, 'edit_text'):
            await callback.message.edit_text(  # type: ignore
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
    await callback.answer()


@router.callback_query(AnalysisFilterCallback.filter())
async def apply_filter(
    callback: CallbackQuery,
    callback_data: AnalysisFilterCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Применить фильтр к истории анализов."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        # Если это сброс фильтра
        if callback_data.filter_type == "reset":
            history_callback = AnalysisHistoryCallback(action="list", page=0)
            await show_analysis_list(callback, history_callback, user, orm, i18n)
            return
        
        # Если это file_type без filter_value - перенаправляем к show_file_type_filter
        if callback_data.filter_type == "file_type" and not callback_data.filter_value:
            await show_file_type_filter(callback, callback_data, user, orm, i18n)
            return
        
        # Применяем фильтр
        page_size = 5
        filter_dict = {
            "type": callback_data.filter_type,
            "value": callback_data.filter_value
        }
        
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            
            # Получаем отфильтрованные данные
            if callback_data.filter_type == "file_type" and callback_data.filter_value:
                # Фильтр по типу файла
                history_data = await history_repo.get_user_history(
                    user_id=user.user_id,
                    page=0,
                    page_size=page_size,
                    file_type_filter=callback_data.filter_value
                )
            elif callback_data.filter_type == "success":
                # Фильтр по успешности
                is_success = callback_data.filter_value == "true"
                history_data = await history_repo.get_user_history(
                    user_id=user.user_id,
                    page=0,
                    page_size=page_size,
                    success_filter=is_success
                )
            else:
                # По умолчанию без фильтра
                history_data = await history_repo.get_user_history(
                    user_id=user.user_id,
                    page=0,
                    page_size=page_size
                )
        
        analyses = history_data["analyses"]
        total_pages = history_data["total_pages"]
        
        if not analyses:
            text = i18n.gettext(
                "📭 *Анализы не найдены*\n\n"
                "По выбранному фильтру анализы не найдены.",
                locale=user.lang
            )
            keyboard = Keyboards.analysis_filter_menu(i18n, user)
        else:
            text = i18n.gettext(
                "📊 *Отфильтрованные анализы:*\n\n", 
                locale=user.lang
            )
            
            # Формируем список анализов (та же логика что и в show_analysis_list)
            for i, analysis in enumerate(analyses, 1):
                device_emoji = "📱" if analysis.device_model and ("iPhone" in analysis.device_model or "iPad" in analysis.device_model) else "📱"
                
                file_type_emoji = {
                    "ips": "📄",
                    "txt": "📝", 
                    "photo": "🖼️",
                    "json": "🔧"
                }.get(analysis.file_type, "📄")
                
                status_text = i18n.gettext("✅ Solution found", locale=user.lang) if analysis.is_solution_found else i18n.gettext("❌ Solution not found", locale=user.lang)
                
                # Безопасное экранирование для Markdown
                device_name = analysis.device_model or i18n.gettext("Неизвестное устройство", locale=user.lang)
                device_name = device_name.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
                
                ios_version = analysis.ios_version or ""
                ios_version = ios_version.replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
                
                # Правильное отображение типа файла
                file_type_display = {
                    "ips": ".ips",
                    "txt": ".txt", 
                    "photo": "photo",
                    "json": ".json"
                }.get(analysis.file_type, analysis.file_type or "file")
                
                # Форматируем дату
                date_str = analysis.created_at.strftime("%d.%m.%Y, %H:%M")
                
                text += i18n.gettext(
                    "   {number}. {device_emoji} {device}, {ios}\n"
                    "      {file_emoji} Тип: {file_type}\n"
                    "      📅 {date}\n"
                    "      {status}\n\n",
                    locale=user.lang
                ).format(
                    number=i,
                    device_emoji=device_emoji,
                    device=device_name,
                    ios=ios_version,
                    file_emoji=file_type_emoji,
                    file_type=file_type_display,
                    date=date_str,
                    status=status_text
                )
            
            keyboard = Keyboards.analysis_history_list(
                i18n, user, analyses, 0, total_pages, filter_dict
            )
        
        try:
            if callback.message and hasattr(callback.message, 'edit_text'):
                await callback.message.edit_text(  # type: ignore
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error applying filter: {e}")
        await callback.answer(
            i18n.gettext("❌ Ошибка при применении фильтра", locale=user.lang)
        )


@router.callback_query(AnalysisHistoryCallback.filter(F.action == "clear_all"))
async def confirm_clear_all_history(
    callback: CallbackQuery,
    callback_data: AnalysisHistoryCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Подтверждение очистки всей истории."""
    text = i18n.gettext(
        "⚠️ *Подтверждение очистки*\n\n"
        "Вы уверены, что хотите удалить ВСЮ историю анализов?\n"
        "Это действие нельзя отменить.\n\n"
        "Будут удалены все ваши сохраненные анализы.",
        locale=user.lang
    )
    
    keyboard = Keyboards.analysis_clear_all_confirm(i18n, user)
    
    try:
        if callback.message and hasattr(callback.message, 'edit_text'):
            await callback.message.edit_text(  # type: ignore
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")
    await callback.answer()


@router.callback_query(AnalysisHistoryCallback.filter(F.action == "confirm_clear_all"))
async def clear_all_history(
    callback: CallbackQuery,
    callback_data: AnalysisHistoryCallback,
    user: User,
    orm: ORM,
    i18n: I18n
):
    """Очистить всю историю анализов."""
    try:
        if not orm or not orm.async_sessionmaker:
            await callback.answer(
                i18n.gettext("❌ Сервис временно недоступен", locale=user.lang), 
                show_alert=True
            )
            return
            
        async with orm.async_sessionmaker() as session:
            from database.repo.analysis_history import AnalysisHistoryRepo
            history_repo = AnalysisHistoryRepo(session)
            deleted_count = await history_repo.clear_user_history(user.user_id)
        
        if deleted_count > 0:
            text = i18n.gettext(
                "✅ *История очищена*\n\n"
                "Удалено анализов: {count}\n\n"
                "Ваша история анализов полностью очищена.",
                locale=user.lang
            ).format(count=deleted_count)
        else:
            text = i18n.gettext(
                "📭 *История уже пуста*\n\n"
                "У вас нет сохраненных анализов для удаления.",
                locale=user.lang
            )
        
        # Возвращаемся к главному меню истории
        keyboard = Keyboards.analysis_history_main(i18n, user, 0)  # 0 анализов после очистки
        
        try:
            if callback.message and hasattr(callback.message, 'edit_text'):
                await callback.message.edit_text(  # type: ignore
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.warning(f"Could not edit message: {e}")
        
        await callback.answer(
            i18n.gettext("✅ История очищена", locale=user.lang)
        )
            
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        await callback.answer(
            i18n.gettext("❌ Произошла ошибка при очистке истории", locale=user.lang)
        )


@router.callback_query(F.data == "home_menu")
async def return_to_home_menu(callback: CallbackQuery, user: User, orm: ORM, i18n: I18n):
    """Возврат к главной статистике анализов."""
    try:
        # Вызываем главное меню истории анализов (вместо домашнего меню)
        history_callback = AnalysisHistoryCallback(action="main")
        await return_to_main(callback, history_callback, user, orm, i18n)
        
    except Exception as e:
        logger.error(f"Error returning to analysis history main: {e}")
        await callback.answer(
            i18n.gettext("❌ Произошла ошибка при возврате к статистике", locale=user.lang)
        ) 