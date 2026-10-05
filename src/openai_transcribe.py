"""Transcricao de audio via OpenAI Audio Transcriptions API."""

from __future__ import annotations

import os
from typing import BinaryIO


class TranscriptionError(RuntimeError):
    """Falha ao enviar ou transcrever o audio na OpenAI."""


def transcribe_audio(
    audio: bytes | BinaryIO,
    *,
    filename: str = "command.wav",
    model: str | None = None,
    language: str = "pt",
    api_key: str | None = None,
) -> str:
    """Envia um clip de audio e retorna o texto reconhecido.

    Usa ``gpt-4o-mini-transcribe`` por padrao (ou ``OPENAI_STT_MODEL``).
    A chave vem de ``api_key`` ou ``OPENAI_API_KEY``.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise TranscriptionError(
            "defina OPENAI_API_KEY no ambiente ou no arquivo .env"
        )

    resolved_model = (
        model
        or os.environ.get("OPENAI_STT_MODEL", "").strip()
        or "gpt-4o-mini-transcribe"
    )

    try:
        from openai import OpenAI
    except ImportError as error:
        raise TranscriptionError(
            "instale a dependencia openai com 'pip install -r requirements.txt'"
        ) from error

    if isinstance(audio, (bytes, bytearray)):
        file_tuple = (filename, bytes(audio), "audio/wav")
    else:
        file_tuple = (filename, audio, "audio/wav")

    client = OpenAI(api_key=key)
    try:
        result = client.audio.transcriptions.create(
            model=resolved_model,
            file=file_tuple,
            language=language,
        )
    except Exception as error:  # noqa: BLE001 — superficie unica para o main
        raise TranscriptionError(f"falha na transcricao OpenAI: {error}") from error

    text = getattr(result, "text", None) or ""
    return str(text).strip()
