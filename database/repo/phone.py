from aiogram import Dispatcher
from database.repo.exceptions import InsufficientFundsError, UserNotFoundError

def register_error_handlers(dp: Dispatcher):
    @dp.errors_handler(exception=InsufficientFundsError)
    async def handle_insufficient_funds(error: InsufficientFundsError):
        pass
    
    @dp.errors_handler(exception=UserNotFoundError)
    async def handle_user_not_found(error: UserNotFoundError):
        pass