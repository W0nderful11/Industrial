import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.utils.i18n import I18n, gettext as _
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Optional


from database.models import User
from services.analyzer.resistor_calculator import (
    smd_to_value, value_to_smd, parse_resistance_value, format_resistance,
    calculate_resistance_from_colors, BAND_OPTIONS, SMD_POWER_RATINGS, value_to_colors,
    get_tolerance_for_smd_code, determine_resistor_series, find_closest_e24_value
)
from services.telegram.filters.role import RoleFilter
from services.telegram.misc.callbacks import (
    ResistorCallback, SmdSizeCallback, ResistorPowerCallback, ResistorModeCallback, SmdModeCallback,
    ResistorInfoCallback, LikeDislikeCallback
)

router = Router()
router.message.filter(RoleFilter(roles=["admin", "user"]))
router.callback_query.filter(RoleFilter(roles=["admin", "user"]))


class ResistorColorState(StatesGroup):
    calculating = State()


class ReverseResistorState(StatesGroup):
    waiting_for_numeric_value = State()
    waiting_for_multiplier = State()
    waiting_for_tolerance = State()


class SmdCalculatorState(StatesGroup):
    waiting_for_code = State()
    waiting_for_value = State()


# --- Helper Functions for Color Calculator ---

COLOR_EMOJIS = {
    'black': '⚫️', 'brown': '🟤', 'red': '🔴',
    'orange': '🟠', 'yellow': '🟡', 'green': '🟢',
    'blue': '🔵', 'violet': '🟣', 'grey': '⚪️',
    'white': '⬜️', 'gold': '🌟', 'silver': '🥈'
}


def get_band_name(index: int, num_bands: int, i18n: I18n, lang: str) -> str:
    if num_bands == 4:
        names = ["1-я цифра", "2-я цифра", "Множитель", "Погрешность"]
    elif num_bands == 5:
        names = ["1-я цифра", "2-я цифра", "3-я цифра", "Множитель", "Погрешность"]
    else:  # 6 bands
        names = ["1-я цифра", "2-я цифра", "3-я цифра", "Множитель", "Погрешность", "ТКС"]

    return i18n.gettext(names[index], locale=lang)


async def generate_resistor_display(state: FSMContext, i18n: I18n, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    data = await state.get_data()
    num_bands = data.get("num_bands")
    colors = data.get("colors", [])

    if num_bands is None:
        return i18n.gettext("Ошибка: Количество полос не установлено.", locale=lang), InlineKeyboardBuilder().as_markup()

    current_band = len(colors)
    text_parts = [i18n.gettext("<b>Калькулятор цветовой маркировки</b>\n\n", locale=lang)]
    builder = InlineKeyboardBuilder()

    if colors:
        selected_str = " ".join([COLOR_EMOJIS.get(c, '❓') for c in colors])
        text_parts.append(i18n.gettext("Выбранные цвета: {colors}\n", locale=lang).format(colors=selected_str))

    if len(colors) == num_bands:
        value, tolerance, tcr = calculate_resistance_from_colors(colors)
        if value is not None:
            res_str = format_resistance(value, i18n, lang)
            tol_str = f"±{tolerance}%" if tolerance is not None else ""
            tcr_str = f" (ТКС: {tcr} ppm/K)" if tcr is not None else ""
            
            # Create a list of color names for display
            color_names = [i18n.gettext(color.capitalize(), locale=lang) for color in colors]
            color_lines = [f"{COLOR_EMOJIS.get(colors[i], '❓')} {name}" for i, name in enumerate(color_names)]
            
            text_parts.append(i18n.gettext(
                "\n<b>Результат:</b>\n{colors_list}\n\n"
                "<b>Сопротивление: {res} {tol}{tcr}</b>\n\n"
                "<i>*Мощность не влияет на цветовую маркировку. "
                "Она определяется физическим размером резистора.</i>",
                locale=lang
            ).format(
                colors_list="\n".join(color_lines),
                res=res_str,
                tol=tol_str,
                tcr=tcr_str
            ))

            # Add button for power rating info
            builder.button(
                text=i18n.gettext("Как определить мощность на глаз?", locale=lang),
                callback_data=ResistorInfoCallback(action="show_power_image").pack()
            )
            builder.adjust(1)
        else:
            text_parts.append(i18n.gettext("\n<b>Ошибка:</b> Неверная комбинация цветов.", locale=lang))

    elif current_band < num_bands:
        band_name = get_band_name(current_band, num_bands, i18n, lang)
        text_parts.append(
            i18n.gettext("\nВыберите цвет для <b>{band_name}</b>:", locale=lang).format(band_name=band_name))

        if num_bands == 4:
            band_type = ['band1', 'band2', 'multiplier', 'tolerance'][current_band]
        elif num_bands == 5:
            band_type = ['band1', 'band2', 'band3', 'multiplier', 'tolerance'][current_band]
        else:
            band_type = ['band1', 'band2', 'band3', 'multiplier', 'tolerance', 'tcr'][current_band]

        available_colors = BAND_OPTIONS.get(band_type, [])
        for color in available_colors:
            builder.button(
                text=f"{COLOR_EMOJIS.get(color, '')} {i18n.gettext(color.capitalize(), locale=lang)}",
                callback_data=ResistorCallback(action="select_color", color=color).pack()
            )
        builder.adjust(3)

    reset_btn = InlineKeyboardButton(text=i18n.gettext("Сброс", locale=lang),
                                     callback_data=ResistorCallback(action="reset").pack())
    back_btn = InlineKeyboardButton(text=i18n.gettext("Назад", locale=lang),
                                    callback_data=ResistorCallback(action="back").pack())
    builder.row(reset_btn, back_btn)

    return "".join(text_parts), builder.as_markup()


# --- SMD Calculator Handlers ---

async def process_smd_code_calculation(message: Message, code: str, user: User, i18n: I18n):
    """Helper function to process SMD code calculation and send response."""
    value = smd_to_value(code)

    if value is None:
        await message.answer(i18n.gettext(
            "<b>Неверный SMD-код</b> 😕\n\n"
            "Пожалуйста, проверьте правильность ввода. "
            "Код должен соответствовать одному из стандартных форматов:\n"
            "• 2 цифры (<code>45</code>)\n"
            "• 3 цифры (<code>103</code>)\n"
            "• 4 цифры (<code>4702</code>)\n"
            "• С 'R' (<code>4R7</code>)\n"
            "• EIA-96 (<code>01A</code>)\n\n"
            "Если вы уверены в коде, возможно, это специфическая маркировка. "
            "Попробуйте найти даташит на компонент.",
            locale=user.lang
        ))
        return

    # Determine tolerance and series
    tolerance = get_tolerance_for_smd_code(code)
    series = determine_resistor_series(value)
    closest_e24 = find_closest_e24_value(value)
    
    resistance_str = format_resistance(value, i18n, user.lang)
    
    # Check if we need to show closest E24 value
    if abs(value - closest_e24) / closest_e24 > 0.01:  # If more than 1% difference
        closest_e24_str = format_resistance(closest_e24, i18n, user.lang)
        series_info = i18n.gettext(
            "\n\n<i>Внимание! Производители объединяют резисторы в серии или ряды: E6, E12, E24…\n"
            "Для подбора компонента будет использована серия E24.\n"
            "Ближайший номинал: {closest}</i>",
            locale=user.lang
        ).format(closest=closest_e24_str)
    else:
        series_info = ""

    builder = InlineKeyboardBuilder()
    for size, power in SMD_POWER_RATINGS.items():
        builder.button(
            text=f"{size} ({power} Вт)",
            callback_data=SmdSizeCallback(action="select_smd_power", size=size, value=value, tolerance=tolerance, series=series).pack()
        )
    builder.adjust(2)

    response = i18n.gettext(
        "<b>Код:</b> <code>{code}</code>\n<b>Номинал:</b> {res}, {tolerance}\n\n"
        "Выберите типоразмер для определения мощности:",
        locale=user.lang
    ).format(code=code, res=resistance_str, tolerance=tolerance) + series_info

    # Send photo with package sizes
    try:
        photo = FSInputFile("data/typorazmer.jpg")
        await message.answer_photo(photo, caption=response, reply_markup=builder.as_markup())
    except Exception as e:
        # Fallback to text if photo not found
        await message.answer(response, reply_markup=builder.as_markup())


@router.message(Command("smd"))
async def smd_command_handler(message: Message, state: FSMContext, user: User, i18n: I18n):
    await state.clear()
    if not message.text:
        return
    args = message.text.split()
    if len(args) > 1:
        code = args[1]
        await process_smd_code_calculation(message, code, user, i18n)
        return

    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.gettext("🔢 Рассчитать по коду", locale=user.lang),
        callback_data=SmdModeCallback(action="code_to_value").pack()
    )
    builder.button(
        text=i18n.gettext("✍️ Рассчитать по номиналу", locale=user.lang),
        callback_data=SmdModeCallback(action="value_to_code").pack()
    )
    builder.adjust(1)
    
    instruction_text = i18n.gettext(
        "<b>Калькулятор SMD-резисторов</b>\n\n"
        "Я могу рассчитать номинал по коду или найти код по номиналу.\n\n"
        "<b>Примеры по коду (режим 'Рассчитать по коду'):</b>\n"
        "• <code>103</code> (3 цифры)\n"
        "• <code>4702</code> (4 цифры)\n"
        "• <code>4R7</code> (с 'R')\n"
        "• <code>01A</code> (EIA-96)\n\n"
        "<b>Примеры по номиналу (режим 'Рассчитать по номиналу'):</b>\n"
        "• <code>10k</code>\n"
        "• <code>4.7M</code>\n"
        "• <code>150</code> (будет понято как 150 Ом)\n\n"
        "Также можно вызывать команды напрямую: <code>/smd 103</code> или <code>/smdvalue 10k</code>.",
        locale=user.lang
    )

    await message.answer(
        instruction_text,
        reply_markup=builder.as_markup()
    )


@router.callback_query(SmdModeCallback.filter(F.action == "code_to_value"))
async def start_smd_code_to_value(query: CallbackQuery, state: FSMContext, user: User, i18n: I18n):
    await state.set_state(SmdCalculatorState.waiting_for_code)
    if isinstance(query.message, Message):
        await query.message.edit_text(
            i18n.gettext(
                "Введите код с корпуса резистора, например: 4R7, 4702, 03B ...",
                locale=user.lang
            ),
            reply_markup=None
        )
    await query.answer()


@router.message(SmdCalculatorState.waiting_for_code)
async def process_smd_code(message: Message, state: FSMContext, user: User, i18n: I18n):
    if not message.text:
        return
    code = message.text.strip().upper()
    # Only clear state if code is successfully processed
    value = smd_to_value(code)
    if value is not None:
        await state.clear()
    await process_smd_code_calculation(message, code, user, i18n)


@router.callback_query(SmdModeCallback.filter(F.action == "value_to_code"))
async def start_smd_value_to_code(query: CallbackQuery, state: FSMContext, user: User, i18n: I18n):
    await state.set_state(SmdCalculatorState.waiting_for_value)
    if isinstance(query.message, Message):
        await query.message.edit_text(
            i18n.gettext(
                "Введите номинал для подбора SMD-кода.\n"
                "Примеры: 10k, 4.7M, 150, 4R7",
                locale=user.lang
            )
        )
    await query.answer()


@router.message(SmdCalculatorState.waiting_for_value)
async def process_smd_value(message: Message, state: FSMContext, user: User, i18n: I18n, provided_value: Optional[str] = None):
    value_str = provided_value if provided_value is not None else message.text
    if not value_str:
        return

    # Allow comma as a decimal separator
    normalized_input = value_str.strip().replace(',', '.')
    value = parse_resistance_value(normalized_input)

    if value is None:
        await message.answer(i18n.gettext("Неверный формат. Введите число, например: 4.7 или 150.", locale=user.lang))
        return

    codes = value_to_smd(value)
    if not codes:
        await message.answer(i18n.gettext("Не удалось найти подходящий SMD код для этого номинала.", locale=user.lang))
        return

    await state.clear()
    resistance_str = format_resistance(value, i18n, user.lang)
    response_lines = [i18n.gettext("<b>Value:</b> {resistance}\n", locale=user.lang).format(resistance=resistance_str)]
    if 'standard' in codes:
        response_lines.append(i18n.gettext("<b>Code (3/4 digits):</b> <code>{code}</code>", locale=user.lang).format(code=codes['standard']))
    if 'eia96' in codes:
        response_lines.append(i18n.gettext("<b>EIA-96 Code (1%):</b> <code>{code}</code>", locale=user.lang).format(code=codes['eia96']))

    await message.answer("\n".join(response_lines))


@router.callback_query(SmdSizeCallback.filter(F.action == "select_smd_power"))
async def smd_size_select_handler(query: CallbackQuery, callback_data: SmdSizeCallback, i18n: I18n, user: User, state: FSMContext):
    size = callback_data.size
    value = callback_data.value
    tolerance = callback_data.tolerance or "5%"
    series = callback_data.series or "E24"
    power = SMD_POWER_RATINGS.get(size)

    resistance_str = format_resistance(value, i18n, user.lang)
    
    # Find closest E24 value for comparison
    closest_e24 = find_closest_e24_value(value)
    closest_e24_str = format_resistance(closest_e24, i18n, user.lang)
    
    # Build response with series information
    response_lines = [
        i18n.gettext("<b>Номинал:</b> {res}, {tolerance}", locale=user.lang).format(res=resistance_str, tolerance=tolerance),
        i18n.gettext("<b>Типоразмер:</b> {size}", locale=user.lang).format(size=size),
        i18n.gettext("<b>Рекомендуемая мощность:</b> {power} Вт", locale=user.lang).format(power=power),
        "",
        i18n.gettext("<i>*Мощность определяется физическим размером корпуса (типоразмером), а не значением сопротивления.</i>", locale=user.lang)
    ]
    
    # Always add series information for website search (like chipdip.ru does)
    response_lines.insert(-2, "")
    response_lines.insert(-2, i18n.gettext(
        "<b>Поиск SMD-резистора на сайте</b>\n"
        "Внимание! Производители объединяют резисторы в серии или ряды: E6, E12, E24…\n"
        "Для подбора компонента будет использована серия E24.\n\n"
        "<b>{closest}, {size}</b>",
        locale=user.lang
    ).format(closest=closest_e24_str, size=size))
    
    response = "\n".join(response_lines)

    # Add like/dislike buttons
    builder = InlineKeyboardBuilder()
    builder.button(text="👍", callback_data=LikeDislikeCallback(action="like").pack())
    builder.button(text="👎", callback_data=LikeDislikeCallback(action="dislike").pack())

    if isinstance(query.message, Message):
        # Check if message has photo (caption) or just text
        if query.message.photo:
            await query.message.edit_caption(caption=response, reply_markup=builder.as_markup())
        else:
            await query.message.edit_text(response, reply_markup=builder.as_markup())
        
        # Save context for dislike system
        await state.update_data({
            f"analysis_text_{query.message.chat.id}_{query.message.message_id}": response
        })
    await query.answer()


@router.callback_query(ResistorPowerCallback.filter(F.action == "select_power"))
async def resistor_power_select_handler(query: CallbackQuery, callback_data: ResistorPowerCallback, i18n: I18n,
                                        user: User):
    value = callback_data.value
    tolerance = callback_data.tolerance
    power = callback_data.power
    res_str = format_resistance(value, i18n, user.lang)
    tol_str = f"±{tolerance}%" if tolerance != 0 else ""
    power_str = f"{power} Вт"

    response = i18n.gettext(
        "<b>Итоговые параметры резистора:</b>\n\n"
        "<b>Номинал:</b> {res}\n"
        "<b>Точность:</b> {tol}\n"
        "<b>Мощность:</b> {power}",
        locale=user.lang
    ).format(res=res_str, tol=tol_str, power=power_str)

    if isinstance(query.message, Message):
        await query.message.edit_text(response, reply_markup=None)
    await query.answer()


@router.message(Command("smdvalue"))
async def smd_value_command_handler(message: Message, user: User, i18n: I18n, state: FSMContext):
    if not message.text:
        return
    args = message.text.split()
    if len(args) > 1:
        value_str = " ".join(args[1:])
        await process_smd_value(message, state, user, i18n, provided_value=value_str)
        return

    await message.answer(i18n.gettext(
        "<b>Калькулятор SMD-резисторов (Номинал -> Код)</b>\n\n"
        "Пожалуйста, укажите номинал сопротивления после команды.\n\n"
        "<b>Примеры:</b>\n"
        "• <code>/smdvalue 10k</code>\n"
        "• <code>/smdvalue 4.7M</code>\n"
        "• <code>/smdvalue 150</code>\n"
        "• <code>/smdvalue 4R7</code>",
        locale=user.lang
    ))


# --- Color Code Calculator Handlers ---

@router.message(Command("resistor"))
async def resistor_command_handler(message: Message, state: FSMContext, user: User, i18n: I18n):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.gettext("🎨 Рассчитать по цветам", locale=user.lang),
        callback_data=ResistorModeCallback(action="to_value").pack()
    )
    builder.button(
        text=i18n.gettext("🔢 Рассчитать по номиналу", locale=user.lang),
        callback_data=ResistorModeCallback(action="from_value").pack()
    )
    builder.adjust(1)
    await message.answer(
        i18n.gettext("<b>Калькулятор резисторов</b>\n\nВыберите режим работы:", locale=user.lang),
        reply_markup=builder.as_markup()
    )


@router.callback_query(ResistorModeCallback.filter(F.action == "to_value"))
async def start_color_to_value_calculator(query: CallbackQuery, state: FSMContext, user: User, i18n: I18n):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.gettext("4 полоски", locale=user.lang),
                   callback_data=ResistorCallback(action="set_bands", num_bands=4).pack())
    builder.button(text=i18n.gettext("5 полосок", locale=user.lang),
                   callback_data=ResistorCallback(action="set_bands", num_bands=5).pack())
    builder.button(text=i18n.gettext("6 полосок", locale=user.lang),
                   callback_data=ResistorCallback(action="set_bands", num_bands=6).pack())
    builder.adjust(3)
    if isinstance(query.message, Message):
        await query.message.edit_text(
            i18n.gettext("Выберите количество цветовых полос на резисторе:", locale=user.lang),
            reply_markup=builder.as_markup()
        )
    await query.answer()


@router.callback_query(ResistorModeCallback.filter(F.action == "from_value"))
async def start_value_to_color_calculator(query: CallbackQuery, state: FSMContext, user: User, i18n: I18n):
    await state.set_state(ReverseResistorState.waiting_for_numeric_value)
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(
                i18n.gettext(
                    "Введите числовое значение сопротивления (например: 4.7, 150, 22)",
                    locale=user.lang
                ),
                parse_mode=None  # Убираем HTML форматирование
            )
        except Exception:
            # Skip if message can't be edited
            pass
    await query.answer()


@router.message(ReverseResistorState.waiting_for_numeric_value)
async def process_resistor_numeric_value(message: Message, state: FSMContext, user: User, i18n: I18n):
    if not message.text:
        return
        
    # Allow comma as a decimal separator
    normalized_input = message.text.strip().replace(',', '.')
    
    try:
        # Check for 'R' notation and convert it
        if 'r' in normalized_input.lower():
            value_str = normalized_input.lower().replace('r', '.')
            value = float(value_str)
        else:
            value = float(normalized_input)

        if value <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(i18n.gettext("Неверный формат. Введите число, например: 4.7 или 150.", locale=user.lang))
        return

    await state.update_data(numeric_value=value)
    await state.set_state(ReverseResistorState.waiting_for_multiplier)

    builder = InlineKeyboardBuilder()
    multipliers = [
        (i18n.gettext("Ом", locale=user.lang), 1), 
        (i18n.gettext("кОм", locale=user.lang), 1e3), 
        (i18n.gettext("МОм", locale=user.lang), 1e6), 
        (i18n.gettext("ГОм", locale=user.lang), 1e9)
    ]
    for name, value in multipliers:
        builder.button(
            text=name,
            # Using color field to pass multiplier value
            callback_data=ResistorCallback(action="select_multiplier", color=str(value)).pack()
        )
    builder.adjust(4)
    await message.answer(i18n.gettext("Выберите единицу измерения:", locale=user.lang), reply_markup=builder.as_markup())


@router.callback_query(ResistorCallback.filter(F.action == "select_multiplier"), ReverseResistorState.waiting_for_multiplier)
async def process_resistor_multiplier(query: CallbackQuery, callback_data: ResistorCallback, state: FSMContext, user: User, i18n: I18n):
    if not callback_data.color:
        return
    multiplier = float(callback_data.color)
    data = await state.get_data()
    numeric_value = data.get("numeric_value")

    if numeric_value is None:
        await query.answer(i18n.gettext("Ошибка: числовое значение не найдено.", locale=user.lang), show_alert=True)
        return

    value = numeric_value * multiplier
    await state.update_data(value=value)
    await state.set_state(ReverseResistorState.waiting_for_tolerance)

    builder = InlineKeyboardBuilder()
    tolerances = [10, 5, 2, 1, 0.5, 0.25, 0.1, 0.05]
    for t in tolerances:
        builder.button(
            text=f"±{t}%",
            callback_data=ResistorCallback(action="select_tolerance", color=str(t)).pack()
        )
    builder.adjust(2)

    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(i18n.gettext("Выберите точность:", locale=user.lang), reply_markup=builder.as_markup())
        except Exception:
            # Skip if message can't be edited
            pass
    await query.answer()


@router.callback_query(ResistorCallback.filter(F.action == "select_tolerance"), ReverseResistorState.waiting_for_tolerance)
async def process_resistor_tolerance(query: CallbackQuery, callback_data: ResistorCallback, state: FSMContext, user: User, i18n: I18n):
    data = await state.get_data()
    
    # Get the final resistance value that was calculated in process_resistor_multiplier
    final_value = data.get("value")
    tolerance_str = callback_data.color
    
    if final_value is None or tolerance_str is None:
        if isinstance(query.message, Message):
            await query.message.edit_text(i18n.gettext("Произошла ошибка, попробуйте снова.", locale=user.lang))
        await state.clear()
        return

    try:
        tolerance_percent = float(tolerance_str)
    except (ValueError, TypeError):
        if isinstance(query.message, Message):
            await query.message.edit_text(i18n.gettext("Произошла ошибка, неверное значение точности.", locale=user.lang))
        await state.clear()
        return

    colors = value_to_colors(final_value, tolerance_percent)

    if not colors:
        if isinstance(query.message, Message):
            await query.message.edit_text(i18n.gettext("Не удалось подобрать цвета для указанного номинала.", locale=user.lang))
        await state.clear()
        return

    color_names = [i18n.gettext(color.capitalize(), locale=user.lang) for color in colors]
    color_lines = [f"{COLOR_EMOJIS.get(color, '❓')} {name}" for color, name in zip(colors, color_names)]

    response = i18n.gettext(
        "<b>Цветовая маркировка для {value} (±{tolerance}%):</b>\n\n{colors_list}",
        locale=user.lang
    ).format(
        value=format_resistance(final_value, i18n, user.lang),
        tolerance=tolerance_percent,
        colors_list="\n".join(color_lines)
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.gettext("Как определить мощность на глаз?", locale=user.lang),
        callback_data=ResistorInfoCallback(action="show_power_image").pack()
    )
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(response, reply_markup=builder.as_markup())
        except Exception:
            # Skip if message can't be edited
            pass
    await state.clear()
    await query.answer()


@router.callback_query(ResistorCallback.filter(F.action == "set_bands"))
async def set_resistor_bands(query: CallbackQuery, callback_data: ResistorCallback, state: FSMContext, user: User,
                             i18n: I18n):
    await state.set_state(ResistorColorState.calculating)
    await state.update_data(num_bands=callback_data.num_bands, colors=[])
    text, keyboard = await generate_resistor_display(state, i18n, user.lang)
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            # Skip if message can't be edited
            pass
    await query.answer()


@router.callback_query(ResistorCallback.filter(F.action == "select_color"), ResistorColorState.calculating)
async def select_resistor_color(query: CallbackQuery, callback_data: ResistorCallback, state: FSMContext, user: User,
                                i18n: I18n):
    data = await state.get_data()
    colors = data.get("colors", [])
    num_bands = data.get("num_bands", 0)

    if len(colors) < num_bands:
        colors.append(callback_data.color)
        await state.update_data(colors=colors)

    text, keyboard = await generate_resistor_display(state, i18n, user.lang)
    if isinstance(query.message, Message) and (query.message.text != text or query.message.reply_markup != keyboard):
        try:
            await query.message.edit_text(text, reply_markup=keyboard)
        except Exception:  # Can fail if message is not modified
            pass
    await query.answer()


@router.callback_query(ResistorCallback.filter(F.action.in_(["reset", "back"])))
async def reset_or_back_resistor_calculator(query: CallbackQuery, callback_data: ResistorCallback, state: FSMContext,
                                            user: User, i18n: I18n):
    if isinstance(query.message, Message):
        if callback_data.action == 'back':
            # Check current state and go back one step
            data = await state.get_data()
            colors = data.get("colors", [])
            
            if len(colors) > 0:
                # Remove last selected color and regenerate display
                colors.pop()
                await state.update_data(colors=colors)
                text, keyboard = await generate_resistor_display(state, i18n, user.lang)
                try:
                    await query.message.edit_text(text, reply_markup=keyboard)
                except Exception:
                    # Skip if message is already the same
                    pass
            else:
                # Return to band selection
                await state.clear()
                builder = InlineKeyboardBuilder()
                builder.button(text=i18n.gettext("4 полоски", locale=user.lang),
                               callback_data=ResistorCallback(action="set_bands", num_bands=4).pack())
                builder.button(text=i18n.gettext("5 полосок", locale=user.lang),
                               callback_data=ResistorCallback(action="set_bands", num_bands=5).pack())
                builder.button(text=i18n.gettext("6 полосок", locale=user.lang),
                               callback_data=ResistorCallback(action="set_bands", num_bands=6).pack())
                builder.adjust(3)
                try:
                    await query.message.edit_text(
                        i18n.gettext("Выберите количество цветовых полос на резисторе:", locale=user.lang),
                        reply_markup=builder.as_markup()
                    )
                except Exception:
                    # Skip if message is already the same
                    pass
                
        elif callback_data.action == 'reset':
            await state.clear()
            builder = InlineKeyboardBuilder()
            builder.button(text=i18n.gettext("4 полоски", locale=user.lang),
                           callback_data=ResistorCallback(action="set_bands", num_bands=4).pack())
            builder.button(text=i18n.gettext("5 полосок", locale=user.lang),
                           callback_data=ResistorCallback(action="set_bands", num_bands=5).pack())
            builder.button(text=i18n.gettext("6 полосок", locale=user.lang),
                           callback_data=ResistorCallback(action="set_bands", num_bands=6).pack())
            builder.adjust(3)
            try:
                await query.message.edit_text(
                    i18n.gettext("Выберите количество цветовых полос на резисторе:", locale=user.lang),
                    reply_markup=builder.as_markup()
                )
            except Exception:
                # Skip if message is already the same
                pass

    await query.answer()


@router.callback_query(ResistorInfoCallback.filter(F.action == "show_power_image"))
async def show_power_image(query: CallbackQuery, i18n: I18n, user: User):
    """Sends an image explaining how to determine resistor power by size."""
    photo = FSInputFile("data/res.jpg")
    caption = i18n.gettext(
        "Мощность резистора определяется физическим размером корпуса, а не цветовой маркировкой.\n"
        "Приблизительную мощность можно определить визуально по размеру резистора.",
        locale=user.lang
    )
    if isinstance(query.message, Message):
        await query.message.answer_photo(photo, caption=caption)
    await query.answer() 