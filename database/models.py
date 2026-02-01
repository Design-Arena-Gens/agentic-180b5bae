from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite

from config import settings


_DB_LOCK = asyncio.Lock()


@dataclass(slots=True)
class SubscriptionStatus:
    user_id: int
    free_remaining: int
    plan_type: Optional[str]
    plan_expires: Optional[datetime]
    is_active: bool


async def init_db() -> None:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                free_remaining INTEGER DEFAULT 3,
                plan_type TEXT,
                plan_expires TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                invoice_id TEXT UNIQUE,
                amount REAL,
                currency TEXT,
                plan TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )
        await db.commit()


async def add_user(user_id: int, username: Optional[str]) -> None:
    async with _DB_LOCK:
        async with aiosqlite.connect(settings.sqlite_path) as db:
            await db.execute(
                """
                INSERT INTO users (user_id, username, free_remaining)
                VALUES (?, ?, 3)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, username),
            )
            await db.commit()


async def get_user(user_id: int) -> Optional[SubscriptionStatus]:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id, free_remaining, plan_type, plan_expires
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None

            plan_expires = (
                datetime.fromisoformat(row["plan_expires"])
                if row["plan_expires"]
                else None
            )
            is_active = _is_plan_active(row["plan_type"], plan_expires)
            return SubscriptionStatus(
                user_id=row["user_id"],
                free_remaining=row["free_remaining"],
                plan_type=row["plan_type"],
                plan_expires=plan_expires,
                is_active=is_active or row["free_remaining"] > 0,
            )


async def check_sub(user_id: int) -> SubscriptionStatus:
    status = await get_user(user_id)
    if status is None:
        await add_user(user_id, username=None)
        status = await get_user(user_id)
        assert status is not None
    return status


def _is_plan_active(plan_type: Optional[str], plan_expires: Optional[datetime]) -> bool:
    if plan_type == "lifetime":
        return True
    if plan_type and plan_expires:
        return datetime.now(timezone.utc) < plan_expires.astimezone(timezone.utc)
    return False


async def consume_credit(user_id: int) -> None:
    async with _DB_LOCK:
        async with aiosqlite.connect(settings.sqlite_path) as db:
            await db.execute(
                """
                UPDATE users
                SET free_remaining = MAX(free_remaining - 1, 0),
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (user_id,),
            )
            await db.commit()


async def activate_plan(user_id: int, plan: str) -> None:
    async with _DB_LOCK:
        async with aiosqlite.connect(settings.sqlite_path) as db:
            plan_type: Optional[str] = None
            plan_expires: Optional[datetime] = None

            if plan == "pro_month":
                plan_type = "pro_month"
                plan_expires = datetime.now(timezone.utc) + timedelta(days=30)
            elif plan == "pro_lifetime":
                plan_type = "lifetime"
            else:
                plan_type = None

            await db.execute(
                """
                UPDATE users
                SET plan_type = ?,
                    plan_expires = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (plan_type, plan_expires.isoformat() if plan_expires else None, user_id),
            )
            await db.commit()


async def add_payment(
    user_id: int,
    invoice_id: str,
    amount: float,
    currency: str,
    plan: str,
    status: str,
    paid_at: Optional[datetime] = None,
) -> None:
    async with _DB_LOCK:
        async with aiosqlite.connect(settings.sqlite_path) as db:
            await db.execute(
                """
                INSERT INTO payments (user_id, invoice_id, amount, currency, plan, status, paid_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(invoice_id) DO UPDATE SET
                    status = excluded.status,
                    paid_at = excluded.paid_at
                """,
                (
                    user_id,
                    invoice_id,
                    amount,
                    currency,
                    plan,
                    status,
                    paid_at.isoformat() if paid_at else None,
                ),
            )
            await db.commit()

