from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiohttp
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import settings
from database import models
from handlers.states import UniqueizerStates
from keyboards import builders
from services.crypto_pay import create_invoice, CryptomusError


router = Router(name="menu")


WELCOME_TEXT = (
    "🛡 <b>Helvetia Meta</b> — Швейцарский стандарт приватности.\n"
    "Загрузите креатив, и мы очистим его цифровой след.\n"
    "<i>Логи отключены.</i>"
)


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await models.add_user(message.from_user.id, message.from_user.username)
    markup = builders.main_menu().as_markup()
    if settings.banner_url:
        await message.answer_photo(
            photo=settings.banner_url,
            caption=WELCOME_TEXT,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            WELCOME_TEXT,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
        )


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    markup = builders.main_menu().as_markup()
    await _smart_edit(callback, WELCOME_TEXT, markup)
    await callback.answer()


@router.callback_query(F.data == "plans")
async def show_plans(callback: CallbackQuery) -> None:
    text = (
        "💎 <b>Тарифы Helvetia Meta</b>\n\n"
        "• Trial — 3 бесплатные обработки\n"
        "• Pro Month — 15 USDT\n"
        "• Pro Lifetime — 90 USDT\n\n"
        "Оплата через Cryptomus. После оплаты подписка активируется автоматически."
    )
    await _smart_edit(callback, text, builders.plans_menu().as_markup())
    await callback.answer()


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery) -> None:
    status = await models.check_sub(callback.from_user.id)
    plan_descriptions = {
        "lifetime": "Pro Lifetime",
        "pro_month": "Pro Month",
        None: "Trial",
    }
    plan = plan_descriptions.get(status.plan_type, "Trial")

    expires = (
        status.plan_expires.astimezone(timezone.utc).strftime("%d.%m.%Y")
        if status.plan_expires
        else "—"
    )
    text = (
        "👤 <b>Мой профиль</b>\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Текущий план: {plan}\n"
        f"Активная подписка: {'Да' if status.is_active else 'Нет'}\n"
        f"Свободных обработок: {status.free_remaining}\n"
        f"Подписка до: {expires}"
    )
    await _smart_edit(callback, text, builders.back_button().as_markup())
    await callback.answer()


@router.callback_query(F.data == "support")
async def show_support(callback: CallbackQuery) -> None:
    text = (
        "💬 <b>Поддержка</b>\n"
        "• FAQ: https://helvetia-meta.example/faq\n"
        "• Поддержка: @helvetia_support\n\n"
        "Мы отвечаем в течение 15 минут."
    )
    await _smart_edit(callback, text, builders.back_button().as_markup())
    await callback.answer()


@router.callback_query(F.data == "start_process")
async def start_process(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UniqueizerStates.waiting_for_file)
    await _smart_edit(
        callback,
        (
            "🪄 <b>Загрузите фото или видео</b>\n"
            "• Фото: JPG/PNG\n"
            "• Видео: MP4/MOV до 50 МБ\n\n"
            "Очередь выполняется по одному файлу. Исходники удаляются сразу после обработки."
        ),
        builders.cancel_button().as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_process")
async def cancel_process(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _smart_edit(callback, WELCOME_TEXT, builders.main_menu().as_markup())
    await callback.answer("Отменено")


@router.callback_query(F.data == "plan_pro_month")
async def buy_pro_month(callback: CallbackQuery) -> None:
    await _initiate_invoice(callback, amount="15", plan="pro_month")


@router.callback_query(F.data == "plan_pro_lifetime")
async def buy_pro_lifetime(callback: CallbackQuery) -> None:
    await _initiate_invoice(callback, amount="90", plan="pro_lifetime")


@router.callback_query(F.data == "plan_trial")
async def explain_trial(callback: CallbackQuery) -> None:
    await callback.answer("Trial уже активирован при регистрации.", show_alert=True)


async def _initiate_invoice(callback: CallbackQuery, amount: str, plan: str) -> None:
    session: aiohttp.ClientSession = callback.bot["http_session"]
    order_id = f"{plan}-{callback.from_user.id}-{int(datetime.now().timestamp())}"
    callback_url = f"{settings.base_url}/payments/cryptomus"
    success_url = f"{settings.base_url}/success"
    fail_url = f"{settings.base_url}/failed"

    try:
        invoice = await create_invoice(
            session=session,
            amount=amount,
            currency="USDT",
            order_id=order_id,
            description=f"Helvetia Meta {plan}",
            callback_url=callback_url,
            success_url=success_url,
            fail_url=fail_url,
            customer_telegram_id=callback.from_user.id,
        )
    except CryptomusError as exc:
        await callback.answer(f"Ошибка платежа: {exc}", show_alert=True)
        return

    payment_url: Optional[str] = invoice.get("result", {}).get("url")
    if not payment_url:
        await callback.answer("Не удалось создать ссылку на оплату.", show_alert=True)
        return

    text = (
        "💎 <b>Оплата подписки</b>\n"
        f"План: {plan}\n"
        f"Сумма: {amount} USDT\n\n"
        f"Оплатите по ссылке:\n{payment_url}\n\n"
        "После подтверждения платежа подписка активируется автоматически."
    )
    await _smart_edit(callback, text, builders.back_button().as_markup())
    await callback.answer()


async def _smart_edit(callback: CallbackQuery, text: str, markup) -> None:
    try:
        await callback.message.edit_caption(
            caption=text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest:
        await callback.message.edit_text(
            text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
        )
