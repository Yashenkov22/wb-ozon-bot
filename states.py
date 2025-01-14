from aiogram.fsm.state import StatesGroup, State


class SwiftSepaStates(StatesGroup):
    coords = State()


class FeedbackFormStates(StatesGroup):
    reason = State()
    description = State()
    contact = State()
    username = State()


class ProductStates(StatesGroup):
    _id = State()
    percent = State()



class OzonProduct(StatesGroup):
    product = State()
    percent = State()