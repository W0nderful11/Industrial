import shutil
from datetime import datetime
import os
import logging

from aiogram import Router, F
from aiogram.types import Message

from database.database import ORM
from services.analyzer.xlsx import is_valid_panic_xlsx
from services.analyzer import reload_known_error_codes
from services.telegram.filters.role import RoleFilter
from aiogram.utils.i18n import I18n

from services.telegram.misc.keyboards import Keyboards

router = Router()
router.message.filter(RoleFilter(roles=["admin"]))

logger = logging.getLogger(__name__)

timestamp = datetime.now().strftime("%Y_%m_%d-%H:%M")
panic_codes = dict(
    new=f"./data/verifying.panic_codes.xlsx",
    exist=f"./data/panic_codes.xlsx",
    old=f"./data/old_panics/panic_codes_{timestamp}.xlsx",
    name="panic_codes.xlsx"
)
cities = dict(
    new=f"./data/verifying.cities.xlsx",
    exist=f"./data/cities.xlsx",
    old=f"./data/old_cities/cities_{timestamp}.xlsx",
    name="cities.xlsx"
)
nand_list = dict(
    new=f"./data/verifying.nand_list.xlsx",
    exist=f"./data/nand_list.xlsx",
    old=f"./data/old_cities/nand_list_{timestamp}.xlsx",
    name="nand_list.xlsx"
)
regional_prices = dict(
    new=f"./data/verifying.regional_prices.xlsx",
    exist=f"./data/regional_prices.xlsx",
    old=f"./data/old_prices/regional_prices_{timestamp}.xlsx",
    name="regional_prices.xlsx"
)


@router.message(F.document.file_name.endswith(".xlsx"))
async def replace_panic_file(message: Message, i18n: I18n, orm: ORM):
    await message.chat.do("typing")
    file_name = message.document.file_name
    paths = None

    if file_name.startswith("panic_codes"):
        paths = panic_codes
    elif file_name.startswith("cities"):
        paths = cities
    elif file_name.startswith("nand_list"):
        paths = nand_list
    elif file_name.startswith("regional_prices"):
        paths = regional_prices
    else:
        return await message.answer(i18n.gettext("Можно заменить только файлы cities, panic_codes, nand_list и regional_prices❗️"))

    await message.bot.download(file=message.document.file_id, destination=paths["new"])
    
    is_valid = True
    if paths == panic_codes:
        is_valid = is_valid_panic_xlsx(paths["new"])

    if is_valid:
        old_dir = os.path.dirname(paths["old"])
        os.makedirs(old_dir, exist_ok=True)

        if os.path.exists(paths["exist"]):
             shutil.move(paths["exist"], paths["old"])
        shutil.move(paths["new"], paths["exist"])
        
        if paths == regional_prices:
            from services.regional_pricing_service import load_regional_pricing_to_db
            try:
                await load_regional_pricing_to_db(orm, paths["exist"])
                await message.answer(text=i18n.gettext(f"Файл {paths['name']} заменен и данные обновлены."))
            except Exception as e:
                 logger.error(f"Ошибка при перезагрузке regional_prices: {e}")
                 await message.answer(text=i18n.gettext(f"Файл {paths['name']} заменен, но произошла ошибка при обновлении данных в базе."))
        elif paths == panic_codes:
            try:
                updated_codes = reload_known_error_codes()
                logger.info(f"Перезагружен список кодов ошибок. Всего кодов: {len(updated_codes)}")
                await message.answer(text=i18n.gettext(f"Файл {paths['name']} заменен и список кодов ошибок обновлен ({len(updated_codes)} кодов)."))
            except Exception as e:
                logger.error(f"Ошибка при перезагрузке списка кодов: {e}")
                await message.answer(text=i18n.gettext(f"Файл {paths['name']} заменен, но произошла ошибка при обновлении списка кодов."))
        else:
             await message.answer(text=i18n.gettext(f"Файл {paths['name']} заменен."))
        return
        
    return await message.answer(text=i18n.gettext(f"Файл {paths['name']} имеет неправильную структуру или не прошел проверку."))
