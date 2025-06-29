import typing
from dataclasses import dataclass


@dataclass
class ModelPhone:
    model: typing.Optional[str] = None
    version: typing.Optional[str] = None
    ios_version: typing.Optional[str] = None
    crash_reporter_key: typing.Optional[str] = None


@dataclass
class SolutionAboutError:
    """

                "solutions": [],
                "links": [],
                "is_full": True,
                "error_code": None,
                "date": self.log_dict.get('date')
    """
    descriptions: list[str]
    links: list[str]
    date_of_failure: str
    is_full: bool = True
    error_code: typing.Optional[str] = None
    panic_string: typing.Optional[str] = None
    extracted_error_text_for_admin: typing.Optional[str] = None
    is_mini_response_shown: bool = False
    has_full_solution_available: bool = False
    full_descriptions: typing.Optional[list[str]] = None
    full_links: typing.Optional[list[str]] = None

    def show_solution(self):
        return "\n".join(self.descriptions)


@dataclass
class ResponseSolution:
    phone: ModelPhone
    content_type: str
    solution: typing.Optional[SolutionAboutError] = None

