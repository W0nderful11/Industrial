from aiogram.fsm.state import StatesGroup, State

 
class ReportState(StatesGroup):
    waiting_for_report = State() 