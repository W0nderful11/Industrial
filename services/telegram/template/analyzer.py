import typing

from aiogram import types
from aiogram.utils.i18n import I18n

from services.telegram.schemas.analyzer import ModelPhone, SolutionAboutError


def template_about_analysis_result_header(
        phone: ModelPhone,
        solution_about_error: typing.Optional[SolutionAboutError],
        i18n: I18n,
        lang: str
):
    header_text = i18n.gettext("Информация об устройстве:", locale=lang)
    model_text = i18n.gettext("📱 Модель:", locale=lang)
    ios_version_text = i18n.gettext("🛠️ Версия iOS:", locale=lang)
    failure_date_text = i18n.gettext("📅 Дата сбоя:", locale=lang)

    text = """
<b>{header}</b>
{model_label} {model} ({model_version})
{ios_label} {ios_version}
{date_label} {date_of_failure}
""".format(
        header=header_text,
        model_label=model_text,
        model=phone.model,
        model_version=phone.version,
        ios_label=ios_version_text,
        ios_version=phone.ios_version,
        date_label=failure_date_text,
        date_of_failure=solution_about_error.date_of_failure if solution_about_error and solution_about_error.date_of_failure else i18n.gettext("Не указана", locale=lang)
    )
    return text


def template_about_analysis_result(
        solution_about_error: SolutionAboutError,
        i18n: I18n,
        lang: str
) -> str:
    header_text = i18n.gettext("Найденные ошибки и рекомендации по ремонту:", locale=lang)
    text = f"""
<b>{header_text}</b>
{solution_about_error.show_solution()}
"""

    return text


def template_not_found_solution(
        content_type: str,
        i18n: I18n,
        lang: str
):

    texts = {
        types.ContentType.DOCUMENT: i18n.gettext(
                    """
К сожалению, поиск ключевого слова по нашей базе анализов не дал результата.
Мы обязательно добавим решение по данному анализу в ближайших обновлениях.

Если у вас есть другие panic-файлы, рекомендуем их также изучить и отправить нам, особенно если в них встречаются отличия. Иногда полезная информация о сбое содержится только в одном из нескольких файлов.

А пока предлагаем провести расширенную диагностику на основе опыта типовых неисправностей. Ниже собраны ключевые рекомендации, которые помогут быстрее локализовать проблему даже без точного описания ошибки:
                    """, locale=lang
                ),
        types.ContentType.PHOTO: i18n.gettext(
            """
⚠️ Скриншот не читается — проверьте указана ли модель телефона на скриншоте без нее анализ по фото не будет работать, возможны блики, размытость или слабое качество.
Чтобы бот точно определил проблему, пожалуйста, *прикрепите файл в формате .ips или .txt* (panic-файл или лог).

Так результат будет точнее. Спасибо за понимание! 
            """, locale=lang
            # EN: ⚠️ Screenshot is not readable - check if the phone model is indicated on the screenshot, without it the photo analysis will not work, glare, blurriness or poor quality are possible.
        )
    }

    return texts.get(content_type)