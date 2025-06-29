import asyncio
import logging
import os
from typing import Tuple, Optional

from aiogram import types
from aiogram.types import Message

from config import DEBUG_MODE
from database.models import User
from services.analyzer import LogAnalyzer, TxtAnalyzer, PhotoAnalyzer
from services.telegram.misc.utils import save_file, remove_file
from services.telegram.schemas.analyzer import ResponseSolution, SolutionAboutError


async def find_error_solutions(
        message: Message,
        user: User
) -> ResponseSolution:
    file_path = await save_file(
        message, file_type=message.content_type
    )
    try:
        content_type = types.ContentType.DOCUMENT

        if message.document and message.document.file_name.endswith(".ips"):
            analyzer = LogAnalyzer(user.lang, file_path, message.from_user.username)
        elif message.document and message.document.file_name.endswith(".txt"):
            analyzer = TxtAnalyzer(user.lang, file_path, message.from_user.username)
        elif (message.document and message.document.file_name.endswith(".png", ".jpg", ".jpg")) or message.photo:
            content_type = types.ContentType.PHOTO
            analyzer = PhotoAnalyzer(user.lang, file_path)
        else:
            return await message.answer(text='Бот не читает эти файлы')

        # Включаем режим отладки для поиска и анализа мини-решений
        enable_debug = True
        solution_about_error = await analyzer.find_error_solutions(debug=DEBUG_MODE or enable_debug)

        return ResponseSolution(
            phone=analyzer.get_model(),
            solution=solution_about_error,
            content_type=content_type
        )
    except Exception as e:
        raise e
    finally:
        remove_file(file_path)
