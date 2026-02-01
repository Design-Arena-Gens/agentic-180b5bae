from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from config import settings
from database import models
from handlers import files, menu
from services.crypto_pay import check_signature
from services.media_processor import processor


PAYMENT_ROUTE = "/payments/cryptomus"


async def handle_payment_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    data = await request.json()
    signature = request.headers.get("sign") or request.headers.get("Sign")

    if not signature or not check_signature(data, signature):
        return web.json_response({"status": "invalid signature"}, status=403)

    status = data.get("status")
    order_id = data.get("order_id", "")
    amount = float(data.get("amount", 0))
    currency = data.get("currency", "USDT")
    invoice_id = data.get("uuid", order_id)

    segments = order_id.split("-")
    if len(segments) < 3:
        return web.json_response({"status": "ignored"}, status=200)

    plan = segments[0]
    user_id = int(segments[1])

    await models.add_payment(
        user_id=user_id,
        invoice_id=invoice_id,
        amount=amount,
        currency=currency,
        plan=plan,
        status=status,
        paid_at=datetime.now(timezone.utc) if status == "paid" else None,
    )

    if status == "paid":
        await models.activate_plan(user_id=user_id, plan=plan)
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "💎 Подписка активирована!\n"
                    "Спасибо за оплату. Теперь обработки без лимитов."
                ),
            )
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("Failed to notify user %s", user_id)

    return web.json_response({"status": "ok"})


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    if not settings.cryptomus_api_key or not settings.cryptomus_merchant:
        logging.warning("Cryptomus credentials are not fully configured.")

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    await models.init_db()
    await processor.start()

    session = aiohttp.ClientSession()
    bot = Bot(settings.bot_token, parse_mode=ParseMode.HTML)
    bot["http_session"] = session

    dp = Dispatcher()
    dp.include_router(menu.router)
    dp.include_router(files.router)

    app = web.Application()
    app["bot"] = bot
    app.router.add_post(PAYMENT_ROUTE, handle_payment_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host=settings.payment_webhook_host,
        port=settings.payment_webhook_port,
    )
    await site.start()
    logging.info("Payment webhook listening on %s:%s", settings.payment_webhook_host, settings.payment_webhook_port)

    try:
        await dp.start_polling(bot)
    finally:
        await session.close()
        await processor.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

