from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR
ENV_PATH = ROOT_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()


@dataclass(slots=True)
class Settings:
    bot_token: str
    cryptomus_merchant: str
    cryptomus_api_key: str
    cryptomus_callback_secret: str
    payment_webhook_host: str
    payment_webhook_port: int
    base_url: str
    banner_url: str
    log_level: str
    sqlite_path: Path
    queue_maxsize: int
    temp_dir: Path


def _ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_settings() -> Settings:
    sqlite_path = Path(os.getenv("SQLITE_PATH", "./data/helvetia_meta.db")).resolve()
    _ensure_directory(sqlite_path.parent)

    temp_dir = Path(os.getenv("TEMP_DIR", "./data/tmp")).resolve()
    temp_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        cryptomus_merchant=os.getenv("CRYPTOMUS_MERCHANT", "").strip(),
        cryptomus_api_key=os.getenv("CRYPTOMUS_API_KEY", "").strip(),
        cryptomus_callback_secret=os.getenv("CRYPTOMUS_CALLBACK_SECRET", "").strip(),
        payment_webhook_host=os.getenv("PAYMENT_WEBHOOK_HOST", "0.0.0.0"),
        payment_webhook_port=int(os.getenv("PAYMENT_WEBHOOK_PORT", "8080")),
        base_url=os.getenv("BASE_URL", "").strip(),
        banner_url=os.getenv("BANNER_URL", "").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        sqlite_path=sqlite_path,
        queue_maxsize=int(os.getenv("QUEUE_MAXSIZE", "3")),
        temp_dir=temp_dir,
    )


settings = load_settings()
