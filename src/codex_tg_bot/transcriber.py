from __future__ import annotations

from pathlib import Path

import aiohttp


class TranscriptionError(RuntimeError):
    pass


async def transcribe_audio_file(path: Path, api_key: str, model: str) -> str:
    form = aiohttp.FormData()
    form.add_field("model", model)
    form.add_field("language", "ru")
    form.add_field(
        "file",
        path.read_bytes(),
        filename=path.name,
        content_type="audio/ogg",
    )

    headers = {"Authorization": f"Bearer {api_key}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post("https://api.openai.com/v1/audio/transcriptions", data=form) as response:
            payload = await response.json(content_type=None)
            if response.status >= 400:
                detail = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
                raise TranscriptionError(detail or f"Transcription failed with HTTP {response.status}")

    text = payload.get("text") if isinstance(payload, dict) else None
    if not text:
        raise TranscriptionError("Transcription response did not contain text.")

    return " ".join(text.split())
