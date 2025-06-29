"""
Утилиты для анализатора файлов
"""


def sanitize_callback_data(text):
    """Удаляет или заменяет символы, запрещенные в callback_data"""
    if not text:
        return text
    # Заменяем двоеточие и другие запрещенные символы
    replacements = {
        ':': '_COLON_',
        '=': '_EQ_',
        ';': '_SEMI_',
        '&': '_AMP_',
        '?': '_QM_'
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def desanitize_callback_data(text):
    """Восстанавливает исходный текст из callback_data"""
    if not text:
        return text
    # Возвращаем символы обратно
    replacements = {
        '_COLON_': ':',
        '_EQ_': '=',
        '_SEMI_': ';',
        '_AMP_': '&',
        '_QM_': '?'
    }
    for replacement, char in replacements.items():
        text = text.replace(replacement, char)
    return text 