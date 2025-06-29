from aiogram import Router
import logging


home_router = Router()


logger = logging.getLogger(__name__) 

# URL канала, если он используется в нескольких модулях и импортируется отсюда
CHANNEL_URL = "https://t.me/Yourrepairassistant"

# Импорт и подключение роутеров из других файлов этого пакета
from .user_commands import router as user_commands_router
from .admin_commands import router as admin_commands_router
from .admin_callbacks import router as admin_callbacks_router
from .admin_states import router as admin_states_router
from .user_callbacks import router as user_callbacks_router
from .inline_handlers import router as inline_handlers_router

home_router.include_routers(
    user_commands_router,
    admin_commands_router,
    admin_callbacks_router,
    admin_states_router,
    user_callbacks_router,
    inline_handlers_router
)


# TODO: Добавить сюда RoleFilter после импорта RoleFilter