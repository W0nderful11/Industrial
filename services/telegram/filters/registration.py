from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message


class RegistrationFilter(BaseFilter):
    def __init__(self, filter_column):
        self.filter_column = filter_column

    async def __call__(self, message: Message, state: FSMContext):
        data = await state.get_data()
        columns: list = data.get("columns")
        print(self.filter_column, data)
        if columns and self.filter_column in columns:
            columns.remove(self.filter_column)
            await state.update_data(columns=columns)
            return True
        return False
