from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict

import aiohttp

from config import settings


API_BASE = "https://api.cryptomus.com/v1"


class CryptomusError(RuntimeError):
    pass


def _make_signature(payload: Dict[str, Any]) -> str:
    message = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    signature = hmac.new(
        settings.cryptomus_api_key.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return signature


async def create_invoice(
    session: aiohttp.ClientSession,
    amount: str,
    currency: str,
    order_id: str,
    description: str,
    callback_url: str,
    success_url: str,
    fail_url: str,
    customer_telegram_id: int,
) -> Dict[str, Any]:
    payload = {
        "amount": amount,
        "currency": currency,
        "order_id": order_id,
        "url_return": success_url,
        "url_callback": callback_url,
        "url_success": success_url,
        "url_error": fail_url,
        "is_payment_multiple": False,
        "network": "USDT",
        "customer_telegram_id": str(customer_telegram_id),
        "description": description,
    }

    signature = _make_signature(payload)

    headers = {
        "merchant": settings.cryptomus_merchant,
        "sign": signature,
        "Content-Type": "application/json",
    }

    async with session.post(
        f"{API_BASE}/payment",
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=aiohttp.ClientTimeout(total=20),
    ) as response:
        data = await response.json(content_type=None)
        if response.status >= 400 or data.get("state") != 0:
            raise CryptomusError(f"Failed to create invoice: {data}")
        return data


def check_signature(body: Dict[str, Any], received_signature: str) -> bool:
    expected_signature = hmac.new(
        settings.cryptomus_callback_secret.encode(),
        json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, received_signature)

