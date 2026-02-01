from __future__ import annotations

import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from config import settings
from database import models
from handlers.states import UniqueizerStates
from services.media_processor import processor, MediaProcessingError


router = Router(name="files")

PROCESSED_DIR = settings.temp_dir / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


@router.message(UniqueizerStates.waiting_for_file, F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1]
    await _process_file(
        message=message,
        state=state,
        file_id=photo.file_id,
        extension=".jpg",
        is_video=False,
        size=photo.file_size,
    )


@router.message(UniqueizerStates.waiting_for_file, F.document)
async def handle_document(message: Message, state: FSMContext) -> None:
    document = message.document
    extension = Path(document.file_name or "").suffix.lower()
    is_video = document.mime_type.startswith("video/") if document.mime_type else False
    await _process_file(
        message=message,
        state=state,
        file_id=document.file_id,
        extension=extension or (".mp4" if is_video else ".jpg"),
        is_video=is_video,
        size=document.file_size,
    )


@router.message(UniqueizerStates.waiting_for_file, F.video)
async def handle_video(message: Message, state: FSMContext) -> None:
    video = message.video
    await _process_file(
        message=message,
        state=state,
        file_id=video.file_id,
        extension=".mp4",
        is_video=True,
        size=video.file_size,
    )


@router.message(UniqueizerStates.waiting_for_file)
async def unsupported_content(message: Message) -> None:
    await message.answer(
        "Поддерживаются только фото (JPG/PNG) и видео (MP4/MOV до 50 МБ). Попробуйте снова."
    )


async def _process_file(
    message: Message,
    state: FSMContext,
    file_id: str,
    extension: str,
    is_video: bool,
    size: int,
) -> None:
    if is_video and size and size > 50 * 1024 * 1024:
        await message.answer("Видео превышает 50 МБ. Сожмите файл и попробуйте снова.")
        return

    user_status = await models.check_sub(message.from_user.id)
    if not user_status.is_active:
        await message.answer(
            "У вас закончились бесплатные обработки. Перейдите в раздел тарифов и активируйте подписку."
        )
        await state.clear()
        return

    input_path = settings.temp_dir / f"input_{uuid.uuid4().hex}{extension}"
    output_path: Path | None = None

    try:
        await message.bot.download(file=file_id, destination=input_path)

        if is_video:
            output_path = await processor.enqueue_video(input_path, PROCESSED_DIR)
        else:
            output_path = await processor.enqueue_photo(input_path, PROCESSED_DIR)

        if not user_status.plan_type or user_status.plan_type == "trial":
            await models.consume_credit(message.from_user.id)

        caption = "Готово. Отправьте следующий файл или нажмите Отмена."
        input_file = FSInputFile(output_path)

        if is_video:
            await message.answer_document(document=input_file, caption=caption)
        else:
            await message.answer_photo(photo=input_file, caption=caption)
    except MediaProcessingError as exc:
        await message.answer(f"Ошибка обработки: {exc}")
    finally:
        await _cleanup_paths([input_path, output_path])


async def _cleanup_paths(paths: list[Path | None]) -> None:
    for path in paths:
        if path and path.exists():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
