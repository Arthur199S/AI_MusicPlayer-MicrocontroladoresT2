"""Busca uma musica no YouTube usando o executavel yt-dlp."""

import shutil
import subprocess


class YouTubeSearchError(RuntimeError):
    """Indica que a busca no YouTube falhou."""


def find_audio_url(query: str) -> str:
    """Retorna a URL de audio do primeiro resultado encontrado."""
    executable = shutil.which("yt-dlp")
    if executable is None:
        raise YouTubeSearchError("yt-dlp nao foi encontrado no PATH")

    command = [
        executable,
        "--no-playlist",
        "--format",
        "bestaudio/best",
        "--get-url",
        f"ytsearch1:{query}",
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

    url = result.stdout.strip().splitlines()
    if not url:
        raise YouTubeSearchError("nenhuma musica foi encontrada")
    return url[-1]
