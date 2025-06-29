from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import config
from services.telegram.filters.role import RoleFilter

router = Router()
router.message.filter(RoleFilter(roles=["admin"]))

@router.message(Command("debug_on"))
async def enable_debug_mode(message: Message):
    """Включить debug режим для анализатора"""
    config.DEBUG_MODE = True
    await message.answer("🐛 Debug режим анализатора ВКЛЮЧЕН\n\nТеперь в логах будет показываться детальная информация о поиске ошибок.")

@router.message(Command("debug_off"))
async def disable_debug_mode(message: Message):
    """Выключить debug режим для анализатора"""
    config.DEBUG_MODE = False
    await message.answer("✅ Debug режим анализатора ВЫКЛЮЧЕН\n\nОтладочная информация больше не будет показываться в логах.")

@router.message(Command("debug_status"))
async def debug_status(message: Message):
    """Показать статус debug режима"""
    status = "ВКЛЮЧЕН" if config.DEBUG_MODE else "ВЫКЛЮЧЕН"
    emoji = "🐛" if config.DEBUG_MODE else "✅"
    await message.answer(f"{emoji} Debug режим анализатора: {status}") 