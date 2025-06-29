from typing import Optional
from aiogram.filters.callback_data import CallbackData


class HomeCallback(CallbackData, prefix="home"):
    action: str


class ProductSelect(CallbackData, prefix="product_select"):
    name: str


class AdminCallback(CallbackData, prefix="admin"):
    action: str
    user_id: Optional[int] = None


class UserListPagination(CallbackData, prefix="user_page"):
    page: int


class DeleteUser(CallbackData, prefix="delete_user"):
    user_id: int 


class LangCallback(CallbackData, prefix="lang"):
    lang: str


class LangChangeCallBack(CallbackData, prefix="lang_change"):
    action: str
    lang: str


class RenewSubscription(CallbackData, prefix="renew"):
    user_id: int
    months: int


class ChooseModelCallback(CallbackData, prefix="model"):
    model: str


class FullButtonCallback(CallbackData, prefix="full_button"):
    action: str
    error_code: str
    model: str


class BroadcastLangCallback(CallbackData, prefix="brd_lang"):
    lang: str


class BroadcastCallback(CallbackData, prefix="brd_confirm"):
    action: str
    user_id: int


class ShowDiagnosticsCallback(CallbackData, prefix="show_diagnostics"):
    error_code: Optional[str] = None
    model: Optional[str] = None


class LikeDislikeCallback(CallbackData, prefix="like_dislike"):
    action: str


class ReportCallback(CallbackData, prefix="report"):
    action: str


class MassTokenLangCallback(CallbackData, prefix="mass_token_lang"):
    action: str
    lang: str


class UserSearchPagination(CallbackData, prefix="user_search_page"):
    page: int
    query: str


class ResistorCallback(CallbackData, prefix="resistor"):
    action: str
    color: str | None = None
    num_bands: int | None = None


class SmdSizeCallback(CallbackData, prefix="smd_size"):
    action: str  # e.g., 'select_smd_power'
    size: str
    value: float
    tolerance: str | None = None
    series: str | None = None


class ResistorPowerCallback(CallbackData, prefix="res_power"):
    action: str
    value: float
    tolerance: float
    power: float


class ResistorModeCallback(CallbackData, prefix="res_mode"):
    action: str


class ResistorInfoCallback(CallbackData, prefix="res_info"):
    action: str


class SmdModeCallback(CallbackData, prefix="smd_mode"):
    action: str


class ResistorCalculatorCallback(CallbackData, prefix="calc_menu"):
    action: str


class ResistorCalculatorTypeCallback(CallbackData, prefix="calc_type"):
    calculator_type: str  # "color", "smd", "reverse_color", "reverse_smd"


# Callbacks для истории анализов
class AnalysisHistoryCallback(CallbackData, prefix="hist"):
    action: str  # "list", "filter", "stats"
    page: Optional[int] = None


class AnalysisDetailCallback(CallbackData, prefix="hist_detail"):
    analysis_id: int
    action: str  # "view", "delete", "retry", "download", "share"


class AnalysisFilterCallback(CallbackData, prefix="hist_filter"):
    filter_type: str  # "file_type", "success", "date"
    filter_value: Optional[str] = None


class AnalysisHistoryPagination(CallbackData, prefix="hist_page"):
    page: int
    filter_type: Optional[str] = None
    filter_value: Optional[str] = None
