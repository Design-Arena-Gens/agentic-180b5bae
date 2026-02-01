## Helvetia Meta — Async Telegram Uniqueizer

Helvetia Meta — Telegram-бот для безопасной уникализации фото и видео. Стек: Python 3.10, aiogram 3.x, SQLite (aiosqlite), FFmpeg, asyncio.Queue, Cryptomus.

### Структура

```
config.py
database/
  models.py
handlers/
  files.py
  menu.py
  states.py
keyboards/
  builders.py
services/
  crypto_pay.py
  media_processor.py
main.py
requirements.txt
Dockerfile
docker-compose.yml
.env.example
```

### Подготовка

1. Скопируйте `.env.example` в `.env` и заполните значения:
   - `BOT_TOKEN` — токен бота
   - `CRYPTOMUS_MERCHANT`, `CRYPTOMUS_API_KEY`, `CRYPTOMUS_CALLBACK_SECRET`
   - `BASE_URL` — публичный URL сервера (https://domain.com)
   - `PAYMENT_WEBHOOK_HOST`, `PAYMENT_WEBHOOK_PORT` — хост/порт для входящих вебхуков
   - `BANNER_URL` — ссылка на приветственный баннер
2. Убедитесь, что на сервере установлен `ffmpeg` (Dockerfile делает это автоматически).

### Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Для платежей нужен публичный доступ к вебхуку `http://<host>:<port>/payments/cryptomus`.

### Docker

```bash
docker compose up --build -d
```

Контейнер запускает `main.py` и слушает вебхук на `PAYMENT_WEBHOOK_PORT` (по умолчанию 8080). Ограничение памяти 1.5 ГБ задаётся в `docker-compose.yml`.

### Ключевые моменты

- FFmpeg запускается через единый worker (`asyncio.Queue`) с сериализацией задач.
- Очистка метаданных, шум, поворот, crop для изображений; битрейт, скорость, gamma для видео.
- SQLite хранит пользователей, подписки и платежи.
- Cryptomus-интеграция: создание инвойсов и проверка подписи вебхуков.
- Все временные файлы удаляются после отправки результата.

