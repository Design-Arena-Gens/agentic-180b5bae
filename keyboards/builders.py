from __future__ import annotations

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🪄 Начать уникализацию", callback_data="start_process")
    )
    builder.row(
        InlineKeyboardButton(text="💎 Тарифы", callback_data="plans"),
        InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile"),
    )
    builder.row(
        InlineKeyboardButton(text="💬 Поддержка / FAQ", callback_data="support"),
    )
    return builder


def plans_menu() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Trial — бесплатно", callback_data="plan_trial"),
    )
    builder.row(
        InlineKeyboardButton(text="Pro Month — 15 USDT", callback_data="plan_pro_month"),
    )
    builder.row(
        InlineKeyboardButton(text="Pro Lifetime — 90 USDT", callback_data="plan_pro_lifetime"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"),
    )
    return builder


def back_button(callback: str = "back_to_main") -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=callback)
    return builder


def cancel_button() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Отмена", callback_data="cancel_process")
    return builder

