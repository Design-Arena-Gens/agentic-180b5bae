from __future__ import annotations

import asyncio
import os
import random
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import contextlib

from config import settings


class MediaProcessingError(RuntimeError):
    pass


@dataclass(slots=True)
class MediaJob:
    kind: str
    source_path: Path
    destination_dir: Path
    future: asyncio.Future[Path]


class MediaProcessor:
    """
    Serialises ffmpeg executions to guarantee low memory footprint.
    """

    def __init__(self, queue_maxsize: int) -> None:
        self.queue: asyncio.Queue[MediaJob] = asyncio.Queue(maxsize=queue_maxsize)
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        if self._shutdown.is_set():
            self._shutdown.clear()
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker(), name="media-worker")

    async def stop(self) -> None:
        self._shutdown.set()
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

    async def enqueue_photo(self, source: Path, destination: Path) -> Path:
        return await self._enqueue("photo", source, destination)

    async def enqueue_video(self, source: Path, destination: Path) -> Path:
        return await self._enqueue("video", source, destination)

    async def _enqueue(self, kind: str, source: Path, destination_dir: Path) -> Path:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Path] = loop.create_future()
        job = MediaJob(kind=kind, source_path=source, destination_dir=destination_dir, future=future)
        await self.queue.put(job)
        return await future

    async def _worker(self) -> None:
        while not self._shutdown.is_set():
            job = await self.queue.get()
            try:
                if job.kind == "photo":
                    result = await process_photo(job.source_path, job.destination_dir)
                elif job.kind == "video":
                    result = await process_video(job.source_path, job.destination_dir)
                else:
                    raise MediaProcessingError(f"Unknown job type: {job.kind}")
                if not job.future.done():
                    job.future.set_result(result)
            except Exception as exc:  # noqa: BLE001
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                self.queue.task_done()


async def process_photo(source_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower() or ".jpg"

    codec = "mjpeg"
    if suffix in {".png"}:
        codec = "png"
    elif suffix in {".jpeg", ".jpg"}:
        codec = "mjpeg"

    rotation = random.choice([-0.3, -0.2, 0.2, 0.3])
    noise_level = random.uniform(1.0, 2.0)

    output_name = f"{uuid.uuid4().hex}{suffix}"
    output_path = destination_dir / output_name

    vf_filters = [
        f"rotate={rotation}*PI/180:fillcolor=white@0",
        "crop=iw-2:ih-2",
        f"noise=alls={noise_level:.2f}:allf=t",
    ]

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source_path),
        "-map_metadata",
        "-1",
        "-vf",
        ",".join(vf_filters),
        "-c:v",
        codec,
        str(output_path),
    ]

    await _run_subprocess(cmd)
    return output_path


async def process_video(source_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".mkv"}:
        suffix = ".mp4"

    output_name = f"{uuid.uuid4().hex}{suffix}"
    output_path = destination_dir / output_name

    bitrate = await _probe_bitrate(source_path)
    bitrate_delta = random.uniform(-0.05, 0.05)
    target_bitrate = max(int(bitrate * (1 + bitrate_delta)), 300_000)

    speed_delta = random.uniform(-0.02, 0.02)
    speed_factor = max(0.98, min(1.02, 1 + speed_delta))
    gamma_shift = 1 + random.uniform(-0.01, 0.01)

    has_audio = await _probe_has_audio(source_path)

    vf_filters = [
        f"setpts={1/speed_factor:.5f}*PTS",
        f"eq=gamma={gamma_shift:.4f}",
    ]

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source_path),
        "-map_metadata",
        "-1",
        "-vf",
        ",".join(vf_filters),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-b:v",
        str(target_bitrate),
        "-movflags",
        "+faststart",
    ]

    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-af", f"atempo={speed_factor:.4f}"])
    else:
        cmd.append("-an")

    cmd.append(str(output_path))

    await _run_subprocess(cmd)
    return output_path


async def _run_subprocess(cmd: list[str]) -> None:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise MediaProcessingError(
            f"ffmpeg exited with {process.returncode}: {stderr.decode().strip() or stdout.decode().strip()}"
        )


async def _probe_bitrate(path: Path) -> int:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=bit_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    if process.returncode == 0:
        try:
            return int(stdout.decode().strip())
        except ValueError:
            return 2_000_000
    return 2_000_000


async def _probe_has_audio(path: Path) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(path),
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    return bool(stdout and stdout.decode().strip())


processor = MediaProcessor(queue_maxsize=settings.queue_maxsize)
