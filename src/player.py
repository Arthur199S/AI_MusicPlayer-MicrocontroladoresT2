"""Controle do reprodutor mpv."""

import json
import os
import shutil
import socket
import subprocess


class PlayerError(RuntimeError):
    """Indica que o reprodutor nao pode ser controlado."""


class Player:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self.socket_path = "/tmp/ai_music_player.sock"

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
                url,
            ],
            stdin=subprocess.DEVNULL,
        )

    def pause(self) -> None:
        self._send_command(["cycle", "pause"])

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

    def _send_command(self, command: list[object]) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.connect(self.socket_path)
                connection.sendall((json.dumps({"command": command}) + "\n").encode())
        except OSError as error:
            raise PlayerError("nao foi possivel controlar o mpv") from error
