import asyncio
import logging
import os
import re
import typing
import hashlib
import io

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardMarkup


async def delete_message(
        bot: Bot,
        message: Message
):
    if message is None:
        return
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        logging.info(e)


def remove_file(path):
    try:
        os.remove(path)
    except OSError as e:
        logging.error(f"Ошибка удаления временного файла {path}: {e}")


async def send_message(
        bot: Bot,
        text: str,
        user_id: int,
        reply_markup: typing.Optional[InlineKeyboardMarkup] = None,
        parse_mode: typing.Optional[str] = None
):
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as send_err:
        logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {send_err}")


async def save_file(message: Message, file_type: str = "document") -> str:
    try:
        os.makedirs("data/tmp", exist_ok=True)

        if file_type == "document":
            file_id = message.document.file_id
            original_filename = message.document.file_name
            file_extension = os.path.splitext(original_filename)[1].lower()
            # Используем file_id как основу для имени файла, чтобы избежать дублирования
            file_name = f"{file_id.replace('/', '_')}{file_extension}"
        elif file_type == "photo":
            file_id = message.photo[-1].file_id
            # Для фото используем file_unique_id для упрощения именования
            file_name = f"{message.photo[-1].file_unique_id}.jpg"
        else:
            raise ValueError(f"Неподдерживаемый тип файла: {file_type}")
        path = f"data/tmp/{file_name}"
        await message.bot.download(file=file_id, destination=path)
        return path
    except Exception as e:
        logging.error(f"Ошибка сохранения файла: {e}")
        return None


def split_message(text, max_length=4000):
    if not text:
        return ["Нет текста для отправки"]
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]


async def send_message_long(
        bot: Bot,
        chat_id: int,
        text: str,
        reply_markup: typing.Optional[InlineKeyboardMarkup] = None,
        parse_mode: typing.Optional[str] = ParseMode.HTML
):
    messages = split_message(text)
    max_messages = len(messages)
    markup = None

    payload = dict(
        bot=bot,
        user_id=chat_id,
    )

    if parse_mode is not None:
        payload['parse_mode'] = parse_mode

    for index, message in enumerate(messages, 1):

        if index == max_messages:
            markup = reply_markup

        await send_message(
            text=message,
            reply_markup=markup,
            **payload
        )
        await asyncio.sleep(0.3)


def escape_markdown_v2(text: str) -> str:
    """Экранирует специальные символы для MarkdownV2."""
    if not text:
        return ""
    # Порядок важен для некоторых символов (например, \ перед другими)
    escape_chars = r'\\_*[]()~`>#+-=|{}.!'  # Добавлен обратный слеш в начало
    # Создаем регулярное выражение для поиска любого из этих символов
    # r'([\_*[]()~`>#+-=|{}.!])' -> r'([\\_*[\]()~`>#+-=|{}.!])'
    # Необходимо экранировать ] и \ в самом выражении
    regex = r'([' + r'\\'.join(c for c in escape_chars) + r'])'  # Более безопасный способ создания regex
    # Заменяем каждый найденный спецсимвол на его экранированную версию (\\символ)
    return re.sub(regex, r'\\\1', text)


def calculate_file_hash(file_content: bytes) -> str:
    """
    Вычисляет SHA256 хеш для содержимого файла.
    
    Args:
        file_content: Содержимое файла в байтах
        
    Returns:
        Строка с SHA256 хешем в hex формате
    """
    return hashlib.sha256(file_content).hexdigest()


async def calculate_file_hash_from_file_like(file_obj) -> str:
    """
    Вычисляет SHA256 хеш для файло-подобного объекта.
    
    Args:
        file_obj: Файло-подобный объект (например, io.BytesIO)
        
    Returns:
        Строка с SHA256 хешем в hex формате
    """
    # Сохраняем текущую позицию
    current_pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    
    # Читаем содержимое
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    
    content = file_obj.read()
    if isinstance(content, str):
        content = content.encode('utf-8')
    
    # Восстанавливаем позицию
    if hasattr(file_obj, 'seek'):
        file_obj.seek(current_pos)
    
    return calculate_file_hash(content)
