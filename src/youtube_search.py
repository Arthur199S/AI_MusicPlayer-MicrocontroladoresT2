"""Busca uma musica no YouTube usando o executavel yt-dlp."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


class YouTubeSearchError(RuntimeError):
    """Indica que a busca no YouTube falhou."""


@dataclass(frozen=True)
class AudioResult:
    url: str
    title: str
    query: str


def find_audio(query: str) -> AudioResult:
    """Retorna URL de audio + titulo do primeiro resultado do YouTube."""
    cleaned = (query or "").strip()
    if not cleaned:
        raise YouTubeSearchError("query de busca vazia")

    executable = shutil.which("yt-dlp")
    if executable is None:
        raise YouTubeSearchError("yt-dlp nao foi encontrado no PATH")

    command = [
        executable,
        "--no-playlist",
        "--format",
        "bestaudio/best",
        "--print",
        "%(title)s",
        "--print",
        "%(url)s",
        f"ytsearch1:{cleaned}",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise YouTubeSearchError("nao foi possivel buscar a musica") from error

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise YouTubeSearchError("nenhuma musica foi encontrada")

    title = lines[0]
    url = lines[-1]
    if not title or not url:
        raise YouTubeSearchError("nenhuma musica foi encontrada")
    return AudioResult(url=url, title=title, query=cleaned)


def find_audio_url(query: str) -> str:
    """Compat: retorna so a URL de audio do primeiro resultado."""
    return find_audio(query).url
