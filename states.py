from aiogram.fsm.state import State, StatesGroup
class GroupCreation(StatesGroup):
    wating_for_group_name = State()

class PollCreation(StatesGroup):
    waiting_for_question = State()
    waiting_for_options = State()
    waiting_for_correct_option = State()
    waiting_for_duration = State()
    
class UserCreation(StatesGroup):
    waiting_for_user_data = State()

