"""Transcricao de audio via OpenAI Audio Transcriptions API."""

from __future__ import annotations

import io
import os
import time
import wave
from dataclasses import dataclass
from typing import BinaryIO


class TranscriptionError(RuntimeError):
    """Falha ao enviar ou transcrever o audio na OpenAI."""


# Guia o modelo a misturar PT (comandos) + EN (titulos) e evita idiomas aleatorios.
_DEFAULT_PROMPT = (
    "Voice commands for a music player. Spoken language is Portuguese or English. "
    "Commands in Portuguese (toque, pause, continue, pare, proxima). "
    "Song titles may be in Portuguese or English "
    "(ex: toque Evidencias, toque Bohemian Rhapsody, play Shape of You). "
    "Transcribe only Portuguese or English. Never Russian, Chinese, or other languages."
)


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    audio_seconds: float | None = None
    latency_ms: float | None = None


def estimate_wav_seconds(audio: bytes | BinaryIO) -> float | None:
    """Estima duracao de um WAV mono/stereo PCM."""
    pos = None
    try:
        if isinstance(audio, (bytes, bytearray)):
            handle = wave.open(io.BytesIO(bytes(audio)), "rb")
        else:
            if hasattr(audio, "tell"):
                pos = audio.tell()
            handle = wave.open(audio, "rb")
        with handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception:  # noqa: BLE001
        return None
    finally:
        if (
            pos is not None
            and not isinstance(audio, (bytes, bytearray))
            and hasattr(audio, "seek")
        ):
            try:
                audio.seek(pos)
            except Exception:  # noqa: BLE001
                pass


def _extract_usage(result: object) -> tuple[int | None, int | None, int | None]:
    usage = getattr(result, "usage", None)
    if usage is None:
        return None, None, None

    def _get(name: str) -> int | None:
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    input_tokens = _get("input_tokens")
    output_tokens = _get("output_tokens")
    total_tokens = _get("total_tokens")
    return input_tokens, output_tokens, total_tokens


def transcribe_audio(
    audio: bytes | BinaryIO,
    *,
    filename: str = "command.wav",
    model: str | None = None,
    language: str | None = None,
    prompt: str | None = None,
    api_key: str | None = None,
) -> TranscriptionResult:
    """Envia um clip de audio e retorna texto + usage quando disponivel.

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

    resolved_prompt = (
        prompt
        if prompt is not None
        else os.environ.get("OPENAI_STT_PROMPT", _DEFAULT_PROMPT).strip()
    )

    languages_env = os.environ.get("OPENAI_STT_LANGUAGES", "").strip()
    if language is not None:
        resolved_language = language.strip()
    else:
        resolved_language = os.environ.get("OPENAI_STT_LANGUAGE", "pt").strip()

    try:
        from openai import OpenAI
    except ImportError as error:
        raise TranscriptionError(
            "instale a dependencia openai com 'pip install -r requirements.txt'"
        ) from error

    audio_seconds = estimate_wav_seconds(audio)

    if isinstance(audio, (bytes, bytearray)):
        file_tuple = (filename, bytes(audio), "audio/wav")
    else:
        file_tuple = (filename, audio, "audio/wav")

    create_kwargs: dict = {
        "model": resolved_model,
        "file": file_tuple,
    }
    if resolved_prompt:
        create_kwargs["prompt"] = resolved_prompt

    if languages_env:
        create_kwargs["languages"] = [
            item.strip() for item in languages_env.split(",") if item.strip()
        ]
    elif resolved_language and resolved_language.lower() not in ("auto", "none"):
        create_kwargs["language"] = resolved_language

    client = OpenAI(api_key=key)
    started = time.monotonic()
    try:
        result = client.audio.transcriptions.create(**create_kwargs)
    except Exception as error:  # noqa: BLE001 — superficie unica para o main
        raise TranscriptionError(f"falha na transcricao OpenAI: {error}") from error
    latency_ms = round((time.monotonic() - started) * 1000.0, 1)

    text = str(getattr(result, "text", None) or "").strip()
    input_tokens, output_tokens, total_tokens = _extract_usage(result)
    return TranscriptionResult(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        audio_seconds=audio_seconds,
        latency_ms=latency_ms,
    )
