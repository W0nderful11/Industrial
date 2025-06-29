import urllib.parse

from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import I18n
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.database import ORM
from services.telegram.misc.callbacks import (
    AdminCallback, RenewSubscription, ChooseModelCallback,
    FullButtonCallback, LangCallback, LangChangeCallBack, 
    BroadcastLangCallback, BroadcastCallback, ShowDiagnosticsCallback, UserListPagination,
    MassTokenLangCallback, ResistorCalculatorCallback, ResistorCalculatorTypeCallback,
    AnalysisHistoryCallback, AnalysisDetailCallback, AnalysisHistoryPagination, AnalysisFilterCallback
)

CONSULTATION_USERNAME = "masterkazakhstan"

class Keyboards:
    @staticmethod
    def balance_keyboard(i18n: I18n, user) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=i18n.gettext("Пополнить баланс", locale=user.lang) + " 💳",
                callback_data="topup_balance_user"
            )]
        ])

    @staticmethod
    def send_phone(i18n: I18n, user):
        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            keyboard=[[
                KeyboardButton(
                    text=i18n.gettext('Поделиться номером телефона', locale=user.lang),
                    request_contact=True
                )
            ]]
        )

    @staticmethod
    def home(i18n: I18n, user) -> ReplyKeyboardMarkup:
        user_keyboard = [
            [
                KeyboardButton(text=i18n.gettext("Инструкция", locale=user.lang) + " 📕"),
                KeyboardButton(text=i18n.gettext("Мой баланс", locale=user.lang) + " 💰")
            ],
            [
                KeyboardButton(text=i18n.gettext("Referral link 🔗", locale=user.lang)),
                KeyboardButton(text=i18n.gettext("Пополнить баланс", locale=user.lang) + " 💳")
            ],
            [
                KeyboardButton(text=i18n.gettext("Сменить язык", locale=user.lang) + " 🏳️"),
                KeyboardButton(text=i18n.gettext("Наш канал", locale=user.lang) + " 👥", url="https://t.me/Yourrepairassistant")
            ],
            [
                KeyboardButton(text=i18n.gettext("Справочник дисков", locale=user.lang) + " 📚"),
                KeyboardButton(text=i18n.gettext("Калькулятор резисторов", locale=user.lang) + " 🧮")
            ],
            [
                KeyboardButton(text=i18n.gettext("Мои анализы", locale=user.lang) + " 📊")
            ]
        ]

        if user.role == 'admin':
            user_keyboard.append([KeyboardButton(text=i18n.gettext("Админ панель", locale=user.lang) + " ⚙️")])

        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=user_keyboard
        )

    @staticmethod
    def admin_panel(i18n: I18n, user) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Рассылка", locale='ru') + " 📣",
                    callback_data="broadcast"
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Список пользователей", locale='ru') + " 👥",
                    callback_data="users_list"
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Find user 🔎", locale='ru'),
                    switch_inline_query_current_chat=""
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Списать токены", locale='ru') + " ➖",
                    callback_data="admin_deduct_tokens"
                )
            ]
        ])
    
    def admin_balance_menu():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Пополнить баланс", callback_data="topup")],
            [InlineKeyboardButton(text="🔎 Проверить баланс", callback_data="admin_check_balance")],
            [InlineKeyboardButton(text="🧾 История операций", callback_data="admin_history")],
            [InlineKeyboardButton(text="🧼 Обнулить баланс", callback_data="admin_reset_balance")],
        ])
    
    @staticmethod
    def get_users_list_keyboard(total_pages: int, current_page: int, i18n: I18n, user) -> InlineKeyboardMarkup:
        buttons = []
        nav_buttons = []

        if current_page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=UserListPagination(page=current_page - 1).pack()
                )
            )

        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{current_page + 1}/{total_pages}",
                callback_data="nothing"
            )
        )

        if current_page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=UserListPagination(page=current_page + 1).pack()
                )
            )

        buttons.append(nav_buttons)
        buttons.append([
            InlineKeyboardButton(
                text=i18n.gettext("Удалить пользователя по ID", locale=user.lang),
                callback_data="delete_user_by_id"
            ),
            InlineKeyboardButton(
                text=i18n.gettext("Назад в админ панель", locale=user.lang) + " ↩️",
                callback_data="back_to_admin"
            )
        ])

        # Добавляем кнопку массового пополнения токенов
        buttons.append([InlineKeyboardButton(text="Начислить токены всем 🪙", callback_data="mass_token_topup")])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def back_to_home(i18n: I18n, user) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            keyboard=[[
                KeyboardButton(text=i18n.gettext("Назад ◀️", locale=user.lang))
            ]]
        )

    @staticmethod
    def balance_request_button(user_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="💰 Пополнить баланс",
                callback_data=f"request_topup:{user_id}"
            )]
        ])

    @staticmethod
    def lang(is_menu=False):
        builder = InlineKeyboardBuilder()
        builder.button(
            text="English 🇺🇸",
            callback_data=LangCallback(lang="en") if not is_menu else LangChangeCallBack(action='changed', lang="en")
        )
        builder.button(
            text="Русский 🇷🇺",
            callback_data=LangCallback(lang="ru") if not is_menu else LangChangeCallBack(action='changed', lang="ru")
        )
        return builder.as_markup()

    @staticmethod
    def links(links: list, i18n: I18n, user):
        builder = InlineKeyboardBuilder()
        for i, link in enumerate(links, start=1):
            builder.button(
                text=i18n.gettext("Материал {number} 📎", locale=user.lang).format(number=i), 
                url=link
            )
        builder.adjust(1, repeat=True)
        return builder.as_markup()

    @staticmethod
    def empty() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[])

    @staticmethod
    def guest(user_id: int, i18n: I18n, user) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=i18n.gettext("Принять ✅", locale=user.lang),
            callback_data=AdminCallback(action="accept", user_id=user_id).pack()
        )
        builder.button(
            text=i18n.gettext("Отклонить ❌", locale=user.lang),
            callback_data=AdminCallback(action="cancel", user_id=user_id).pack()
        )
        return builder.as_markup()

    @staticmethod
    def broadcast_confirmation(user_id: int, i18n: I18n, lang_code: str) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text=i18n.gettext("Accept ✅", locale=lang_code),
            callback_data=BroadcastCallback(action="accept", user_id=user_id).pack()
        )
        builder.button(
            text=i18n.gettext("Reject ❌", locale=lang_code),
            callback_data=BroadcastCallback(action="cancel", user_id=user_id).pack()
        )
        return builder.as_markup()

    @staticmethod
    def broadcast_lang_options(i18n: I18n) -> InlineKeyboardMarkup:
        """
        Generates keyboard for broadcast language selection.
        Uses 'ru' locale for button text as per admin panel conventions.
        """
        builder = InlineKeyboardBuilder()
        builder.button(
            text="English 🇺🇸", # Text can be hardcoded or use i18n.gettext with 'ru'
            callback_data=BroadcastLangCallback(lang="en").pack()
        )
        builder.button(
            text="Русский 🇷🇺", # Text can be hardcoded or use i18n.gettext with 'ru'
            callback_data=BroadcastLangCallback(lang="ru").pack()
        )
        return builder.as_markup()

    @staticmethod
    def months(user, i18n: I18n) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        periods = [
            (1, i18n.gettext("1 месяц", locale=user.lang)),
            (3, i18n.gettext("3 месяца", locale=user.lang)),
            (6, i18n.gettext("6 месяцев", locale=user.lang)),
            (12, i18n.gettext("1 год", locale=user.lang))
        ]
        
        for months, text in periods:
            builder.button(
                text=text,
                callback_data=RenewSubscription(user_id=user.user_id, months=months).pack())
        
        builder.adjust(2, repeat=True)
        return builder.as_markup()

    @staticmethod
    def models(models: list) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for model in models:
            builder.button(
                text=model,
                callback_data=ChooseModelCallback(model=model).pack()
            )
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def add_full_btn(builder: InlineKeyboardBuilder, error_code: str, model: str) -> InlineKeyboardBuilder:
        safe_error_code = error_code.replace(':', 'doubledott')
        builder.button(
            text="+FULL",
            callback_data=FullButtonCallback(action='full', error_code=safe_error_code, model=model).pack()
        )
        return builder

    @staticmethod
    def show_diagnostics_button(i18n: I18n, lang_code: str) -> InlineKeyboardMarkup:
        """Создает кнопку для показа детальной диагностики."""
        button_text = i18n.gettext("Показать подробную диагностику", locale=lang_code)
        builder = InlineKeyboardBuilder()
        builder.button(
            text=button_text,
            callback_data=ShowDiagnosticsCallback().pack()
        )
        return builder.as_markup()

    @staticmethod
    def get_topup_keyboard(user_id: int):
        builder = InlineKeyboardBuilder()
        builder.button(text="100₸", callback_data=f"topup:{user_id}:100")
        builder.button(text="500₸", callback_data=f"topup:{user_id}:500") 
        builder.button(text="1000₸", callback_data=f"topup:{user_id}:1000")
        builder.button(text="Другая сумма", callback_data=f"topup_custom:{user_id}")
        builder.adjust(3, 1)
        return builder.as_markup()

    @staticmethod
    def confirm_mass_token_topup(i18n: I18n, lang: str) -> InlineKeyboardMarkup:
        """Клавиатура подтверждения для массового начисления токенов."""
        buttons = [
            [
                InlineKeyboardButton(
                    text=i18n.gettext("✅ Да, начислить всем", locale=lang),
                    callback_data="confirm_mass_token_topup"
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("❌ Нет, отменить", locale=lang),
                    callback_data="cancel_mass_token_topup"
                )
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def create_consultation_button(i18n: I18n, user_lang: str, bot_response_text: str) -> InlineKeyboardMarkup:
        """
        Создает кнопку для запроса консультации с предзаполненным текстом.
        """
        base_text = i18n.gettext(
            "Здравствуйте! Я получил ответ от бота, но хочу проконсультироваться лично.\n\n"
            "Вот мой файл: [Пожалуйста, не забудьте отправить файл лога или скриншот в следующем сообщении в чат]\n\n"
            "Заранее спасибо за помощь!",
            locale=user_lang
        )
        
        # Используем format-строку вместо конкатенации
        full_text = f"{base_text}\n\n{bot_response_text}" 

        # Telegram имеет ограничение на длину текста в URL, обрежем если нужно
        # Максимальная длина URL должна быть меньше 2000 символов для предотвращения ошибки "reply markup is too long"
        # Учитываем, что URL-кодирование увеличивает длину, поэтому берем меньший лимит
        max_text_len = 1200
        if len(full_text) > max_text_len:
            full_text = full_text[:max_text_len] + "..."
            
        # Используем urllib.parse.quote вместо quote_plus, чтобы пробелы не заменялись на +
        url_encoded_text = urllib.parse.quote(full_text)
        
        # Проверяем, что закодированный URL не превышает допустимую длину
        if len(url_encoded_text) > 2000:
            # Если превышает, обрезаем исходный текст еще сильнее
            max_text_len = int(max_text_len * 0.8)  # Уменьшаем на 20%
            full_text = full_text[:max_text_len] + "..."
            url_encoded_text = urllib.parse.quote(full_text)
        
        consultation_url = f"https://t.me/{CONSULTATION_USERNAME}?text={url_encoded_text}"

        builder = InlineKeyboardBuilder()
        builder.button(
            text=i18n.gettext("Запросить консультацию 🧑‍🔧", locale=user_lang),
            url=consultation_url
        )
        return builder.as_markup()

    @staticmethod
    def mass_token_lang_options(i18n: I18n) -> InlineKeyboardMarkup:
        """Клавиатура для выбора языка при массовом начислении токенов."""
        builder = InlineKeyboardBuilder()
        builder.button(
            text="English 🇺🇸", 
            callback_data=MassTokenLangCallback(action='select', lang="en").pack() # Используем action='select'
        )
        builder.button(
            text="Русский 🇷🇺", 
            callback_data=MassTokenLangCallback(action='select', lang="ru").pack() # Используем action='select'
        )
        return builder.as_markup()

    @staticmethod
    def resistor_calculator_menu(i18n: I18n, user) -> InlineKeyboardMarkup:
        """Главное меню калькулятора резисторов."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Рассчитать по цветам", locale=user.lang) + " 🎨",
                    callback_data=ResistorCalculatorTypeCallback(calculator_type="color").pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Рассчитать по номиналу", locale=user.lang) + " 🔢",
                    callback_data=ResistorCalculatorTypeCallback(calculator_type="reverse_color").pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Рассчитать по коду", locale=user.lang) + " 📱",
                    callback_data=ResistorCalculatorTypeCallback(calculator_type="smd_code").pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.gettext("Рассчитать по номиналу", locale=user.lang) + " ⚙️",
                    callback_data=ResistorCalculatorTypeCallback(calculator_type="smd_value").pack()
                )
            ]
        ])

    # Клавиатуры для истории анализов
    @staticmethod
    def analysis_history_main(i18n: I18n, user, total_analyses: int = 0) -> InlineKeyboardMarkup:
        """Главное меню истории анализов."""
        builder = InlineKeyboardBuilder()
        
        # Основные действия в два ряда
        builder.button(
            text=i18n.gettext("📊 Список анализов", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="list", page=0).pack()
        )
        
        builder.button(
            text=i18n.gettext("🔍 Фильтр", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="filter").pack()
        )
        
        # Добавляем кнопку очистки истории, только если есть анализы
        if total_analyses > 0:
            builder.button(
                text=i18n.gettext("🗑 Очистить всю историю", locale=user.lang),
                callback_data=AnalysisHistoryCallback(action="clear_all").pack()
            )
        
        # Добавляем кнопку "Статистика"
        builder.button(
            text=i18n.gettext("📈 Статистика", locale=user.lang),
            callback_data="home_menu"
        )
        
        # Размещаем кнопки: 2 в первом ряду, остальные по одной
        if total_analyses > 0:
            builder.adjust(2, 1, 1)  # 2 в первом ряду, по 1 в остальных
        else:
            builder.adjust(2, 1)  # 2 в первом ряду, 1 во втором
        
        return builder.as_markup()

    @staticmethod
    def analysis_history_list(
        i18n: I18n, 
        user, 
        analyses: list, 
        page: int, 
        total_pages: int,
        current_filter: dict | None = None
    ) -> InlineKeyboardMarkup:
        """Клавиатура списка анализов с пагинацией."""
        builder = InlineKeyboardBuilder()
        
        # Добавляем кнопки для каждого анализа
        for i, analysis in enumerate(analyses, 1):
            number = page * 5 + i  # 5 анализов на страницу
            device_emoji = "📱" if "iPhone" in (analysis.device_model or "") or "iPad" in (analysis.device_model or "") else "📱"
            status_emoji = "✅" if analysis.is_solution_found else "❌"
            
            # Укорачиваем название устройства для кнопки
            device_name = analysis.device_model or i18n.gettext("Неизвестно", locale=user.lang)
            if len(device_name) > 20:
                device_name = device_name[:17] + "..."
            
            button_text = f"{number}. {device_emoji} {device_name} {status_emoji}"
            builder.button(
                text=button_text,
                callback_data=AnalysisDetailCallback(analysis_id=analysis.id, action="view").pack()
            )
        
        # Размещаем анализы по одному в ряду для лучшей читаемости
        builder.adjust(1)
        
        # Кнопки навигации с циклической логикой в одной строке
        nav_buttons = []
        
        # Кнопка "Назад" - циклическая навигация
        prev_page = page - 1 if page > 0 else total_pages - 1
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=AnalysisHistoryPagination(
                    page=prev_page,
                    filter_type=current_filter.get("type") if current_filter else None,
                    filter_value=current_filter.get("value") if current_filter else None
                ).pack()
            )
        )
        
        # Индикатор страницы
        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}" if total_pages > 0 else "1/1",
                callback_data="nothing"
            )
        )
        
        # Кнопка "Вперед" - циклическая навигация  
        next_page = page + 1 if page < total_pages - 1 else 0
        nav_buttons.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=AnalysisHistoryPagination(
                    page=next_page,
                    filter_type=current_filter.get("type") if current_filter else None,
                    filter_value=current_filter.get("value") if current_filter else None
                ).pack()
            )
        )
        
        # Добавляем кнопки навигации в одну строку
        if nav_buttons:
            builder.row(*nav_buttons)
        
        # Дополнительные кнопки управления
        builder.button(
            text=i18n.gettext("🔍 Фильтр", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="filter").pack()
        )
        
        builder.button(
            text=i18n.gettext("🗑 Очистить всю историю", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="clear_all").pack()
        )
        
        builder.button(
            text=i18n.gettext("🏠 Главная", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="main").pack()
        )
        
        # Корректируем размещение: анализы по одному, навигация в одну строку, управление в три кнопки
        adjust_args = [1] * len(analyses) + [3, 3]  # анализы по 1, навигация 3 в ряд, управление 3 в ряд
        builder.adjust(*adjust_args)
        
        return builder.as_markup()

    @staticmethod
    def analysis_detail(i18n: I18n, user, analysis, can_repeat: bool = True, attempts_info: str | None = None) -> InlineKeyboardMarkup:
        """Клавиатура детального просмотра анализа."""
        builder = InlineKeyboardBuilder()
        
        # Основные действия в два ряда
        if can_repeat:
            repeat_text = i18n.gettext("🔄 Повторить анализ", locale=user.lang)
            if attempts_info:
                repeat_text += f" ({attempts_info})"
            
            builder.button(
                text=repeat_text,
                callback_data=AnalysisDetailCallback(analysis_id=analysis.id, action="repeat").pack()
            )
        else:
            # Заблокированная кнопка
            builder.button(
                text=i18n.gettext("🔒 Повторный анализ заблокирован", locale=user.lang),
                callback_data="blocked_repeat"
            )
        
        builder.button(
            text=i18n.gettext("💾 Скачать файл", locale=user.lang),
            callback_data=AnalysisDetailCallback(analysis_id=analysis.id, action="download").pack()
        )
        
        builder.button(
            text=i18n.gettext("📤 Поделиться", locale=user.lang),
            callback_data=AnalysisDetailCallback(analysis_id=analysis.id, action="share").pack()
        )
        
        builder.button(
            text=i18n.gettext("🗑 Удалить", locale=user.lang),
            callback_data=AnalysisDetailCallback(analysis_id=analysis.id, action="delete").pack()
        )
        
        # Кнопки возврата
        builder.button(
            text=i18n.gettext("⬅️ Назад к списку", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="list", page=0).pack()
        )
        
        builder.button(
            text=i18n.gettext("📈 Статистика", locale=user.lang),
            callback_data="home_menu"
        )
        
        # Размещаем кнопки: 2 в первом ряду, 2 во втором, 2 в третьем
        builder.adjust(2, 2, 2)
        return builder.as_markup()

    @staticmethod
    def analysis_filter_menu(i18n: I18n, user) -> InlineKeyboardMarkup:
        """Меню фильтров для истории анализов."""
        builder = InlineKeyboardBuilder()
        
        builder.button(
            text=i18n.gettext("📄 По типу файла", locale=user.lang),
            callback_data=AnalysisFilterCallback(filter_type="file_type").pack()
        )
        
        builder.button(
            text=i18n.gettext("✅ Успешные", locale=user.lang),
            callback_data=AnalysisFilterCallback(filter_type="success", filter_value="true").pack()
        )
        
        builder.button(
            text=i18n.gettext("❌ Неуспешные", locale=user.lang),
            callback_data=AnalysisFilterCallback(filter_type="success", filter_value="false").pack()
        )
        
        builder.button(
            text=i18n.gettext("📅 По дате", locale=user.lang),
            callback_data=AnalysisFilterCallback(filter_type="date").pack()
        )
        
        builder.button(
            text=i18n.gettext("🔄 Сбросить фильтр", locale=user.lang),
            callback_data=AnalysisFilterCallback(filter_type="reset").pack()
        )
        
        builder.button(
            text=i18n.gettext("🔙 Назад", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="main").pack()
        )
        
        builder.button(
            text=i18n.gettext("📈 Статистика", locale=user.lang),
            callback_data="home_menu"
        )
        
        builder.adjust(2, 2, 1, 2)
        return builder.as_markup()

    @staticmethod
    def analysis_file_type_filter(i18n: I18n, user) -> InlineKeyboardMarkup:
        """Фильтр по типам файлов."""
        builder = InlineKeyboardBuilder()
        
        file_types = [
            ("ips", "📄 .ips файлы"),
            ("txt", "📝 .txt файлы"),
            ("photo", "🖼️ Фото"),
            ("json", "🔧 .json файлы")
        ]
        
        for file_type, display_name in file_types:
            builder.button(
                text=i18n.gettext(display_name, locale=user.lang),
                callback_data=AnalysisFilterCallback(filter_type="file_type", filter_value=file_type).pack()
            )
        
        builder.button(
            text=i18n.gettext("🔙 Назад", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="filter").pack()
        )
        
        builder.button(
            text=i18n.gettext("📈 Статистика", locale=user.lang),
            callback_data="home_menu"
        )
        
        builder.adjust(2, 2, 2)
        return builder.as_markup()

    @staticmethod
    def analysis_delete_confirm(i18n: I18n, user, analysis_id: int) -> InlineKeyboardMarkup:
        """Подтверждение удаления анализа."""
        builder = InlineKeyboardBuilder()
        
        builder.button(
            text=i18n.gettext("✅ Да, удалить", locale=user.lang),
            callback_data=AnalysisDetailCallback(analysis_id=analysis_id, action="confirm_delete").pack()
        )
        
        builder.button(
            text=i18n.gettext("❌ Отмена", locale=user.lang),
            callback_data=AnalysisDetailCallback(analysis_id=analysis_id, action="view").pack()
        )
        
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def analysis_clear_all_confirm(i18n: I18n, user) -> InlineKeyboardMarkup:
        """Подтверждение очистки всей истории анализов."""
        builder = InlineKeyboardBuilder()
        
        builder.button(
            text=i18n.gettext("✅ Да, очистить всё", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="confirm_clear_all").pack()
        )
        
        builder.button(
            text=i18n.gettext("❌ Отмена", locale=user.lang),
            callback_data=AnalysisHistoryCallback(action="main").pack()
        )
        
        builder.adjust(2)
        return builder.as_markup()

