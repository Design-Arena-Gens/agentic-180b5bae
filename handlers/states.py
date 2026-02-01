from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class UniqueizerStates(StatesGroup):
    waiting_for_file = State()

