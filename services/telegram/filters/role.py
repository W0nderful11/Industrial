from aiogram.filters import BaseFilter
from aiogram.types import Message

from database.database import ORM


class RoleFilter(BaseFilter):
    def __init__(self, roles):
        self.roles: list[str] = roles

    async def __call__(self, message: Message):
        orm = ORM()
        await orm.create_repos()
        user = await orm.user_repo.find_user_by_user_id(message.from_user.id)
        if user is None:  
            return False 
        if user.role in self.roles:
            return True 
        return False
