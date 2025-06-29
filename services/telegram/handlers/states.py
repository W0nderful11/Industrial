from aiogram.fsm.state import StatesGroup, State


class BalanceStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_payment_confirmation = State()
    waiting_for_user_id = State()
    waiting_for_pricing = State()


class HomeDatetime(StatesGroup):
    wait_date = State()
    wait_time = State()


class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_deduction = State()
    waiting_for_new_fee = State()
    waiting_for_topup = State()
    admin_topup_wait = State()
    waiting_for_broadcast_message = State()
    waiting_for_broadcast_confirmation = State()
    waiting_for_user_id_to_delete = State()
    waiting_for_user_id_to_add_tokens = State()
    waiting_for_tokens_to_add = State()
    waiting_for_user_id_to_deduct_tokens = State()
    waiting_for_tokens_to_deduct = State()
    waiting_for_excel_file = State()
    waiting_for_file_replace = State()
    find_user_query = State()
    # NEW STATES for mass token top-up
    waiting_for_mass_token_language = State()
    waiting_for_mass_token_amount = State()
    waiting_for_mass_token_confirmation = State()
    waiting_for_reply = State()


class BroadcastStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_message = State()
    confirming_message = State()


class DeleteUserStates(StatesGroup):
    waiting_for_user_id = State()


class RegistrationStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_language = State()
    waiting_for_fullname = State()
    waiting_for_affiliate = State()
    waiting_for_country = State()
    waiting_for_city = State()


# --- Новые состояния для пополнения баланса ---
class TopUpStates(StatesGroup):
    waiting_for_location = State()
    # Можно добавить состояния для выбора суммы, способа оплаты и т.д.
    # waiting_for_amount = State()
    # waiting_for_payment_method = State()


# Добавляем новое состояние для пополнения токенов
class TokenTopUpStates(StatesGroup):
    waiting_for_user_id_amount = State()
    waiting_for_action = State()  # Если будет выбор между валютой и токенами
