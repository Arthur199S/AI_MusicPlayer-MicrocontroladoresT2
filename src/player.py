"""Controle do reprodutor mpv."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from typing import Any


class PlayerError(RuntimeError):
    """Indica que o reprodutor nao pode ser controlado."""


def _default_audio_device() -> str:
    """Device ALSA do jack P2 (bcm2835 Headphones).

    Usa o nome da placa (``CARD=Headphones``), nao o indice numerico —
    o Voice HAT pode deslocar ``hw:N,0`` apos reboot. Sobrescreva com
    ``MPV_AUDIO_DEVICE`` no ``.env`` se precisar.
    """
    return os.environ.get(
        "MPV_AUDIO_DEVICE",
        "alsa/plughw:CARD=Headphones,DEV=0",
    ).strip()


def seconds_left_from(duration: float | None, time_pos: float | None) -> float | None:
    """Calcula segundos restantes a partir de duration/time-pos do mpv."""
    if duration is None or time_pos is None:
        return None
    try:
        left = float(duration) - float(time_pos)
    except (TypeError, ValueError):
        return None
    if left < 0:
        return 0.0
    return round(left, 1)


class Player:
    def __init__(self, audio_device: str | None = None) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self.socket_path = "/tmp/ai_music_player.sock"
        self.audio_device = audio_device or _default_audio_device()

    def play(self, url: str) -> None:
        """Inicia uma nova reproducao, encerrando a anterior."""
        self.stop()
        executable = shutil.which("mpv")
        if executable is None:
            raise PlayerError("mpv nao foi encontrado no PATH")
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self.process = subprocess.Popen(
            [
                executable,
                "--no-video",
                "--really-quiet",
                f"--input-ipc-server={self.socket_path}",
                f"--audio-device={self.audio_device}",
                "--volume=90",
                url,
            ],
            stdin=subprocess.DEVNULL,
        )

    def pause(self) -> None:
        self._send_command(["cycle", "pause"])

    def set_pause(self, paused: bool) -> None:
        """Pausa/retoma de forma idempotente (sem alternar)."""
        self._send_command(["set_property", "pause", bool(paused)])

    def resume(self) -> None:
        self._send_command(["set_property", "pause", False])

    def next(self) -> None:
        self._send_command(["playlist-next", "force"])

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                self._send_command(["quit"])
                self.process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=3)
        self.process = None
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

    def playback_snapshot(self) -> dict[str, Any]:
        """Le status de reproducao via IPC (para telemetria)."""
        alive = self.process is not None and self.process.poll() is None
        if not alive:
            return {
                "alive": False,
                "paused": None,
                "time_pos": None,
                "duration": None,
                "seconds_left": None,
            }
        paused = self._get_property("pause")
        time_pos = self._get_property("time-pos")
        duration = self._get_property("duration")
        return {
            "alive": True,
            "paused": paused if isinstance(paused, bool) else None,
            "time_pos": float(time_pos) if isinstance(time_pos, (int, float)) else None,
            "duration": float(duration) if isinstance(duration, (int, float)) else None,
            "seconds_left": seconds_left_from(
                float(duration) if isinstance(duration, (int, float)) else None,
                float(time_pos) if isinstance(time_pos, (int, float)) else None,
            ),
        }

    def _get_property(self, name: str) -> Any:
        response = self._send_command(["get_property", name], expect_response=True)
        if not isinstance(response, dict):
            return None
        if response.get("error") not in (None, "success"):
            return None
        return response.get("data")

    def _send_command(
        self,
        command: list[object],
        *,
        expect_response: bool = False,
    ) -> dict[str, Any] | None:
        if self.process is None or self.process.poll() is not None:
            return None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(1.0)
                connection.connect(self.socket_path)
                connection.sendall((json.dumps({"command": command}) + "\n").encode())
                if not expect_response:
                    return None
                buffer = b""
                while b"\n" not in buffer:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                line = buffer.split(b"\n", 1)[0].decode("utf-8", errors="replace")
                if not line:
                    return None
                payload = json.loads(line)
                return payload if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError, TimeoutError) as error:
            if expect_response:
                return None
            raise PlayerError("nao foi possivel controlar o mpv") from error
