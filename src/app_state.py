"""Estado compartilhado entre o motor de voz e o dashboard."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    """Estado thread-safe da aplicacao."""

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    app_status: str = "stopped"
    engine_running: bool = False

    current_track: str = ""
    last_track: str = ""
    recognized_phrase: str = ""
    last_wake: str = ""
    last_action: str = ""

    request_count: int = 0
    web_play_count: int = 0
    transcribed_lines: int = 0
    transcribed_chars: int = 0
    stt_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    audio_seconds_est: float = 0.0

    mic_name: str = ""
    audio_device: str = ""
    recent_messages: deque[str] = field(default_factory=lambda: deque(maxlen=20))
    recent_usage: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=10)
    )

    def set_status(self, status: str) -> None:
        with self.lock:
            self.app_status = status

    def set_engine_running(self, running: bool) -> None:
        with self.lock:
            self.engine_running = running
            if not running and self.app_status not in ("error",):
                self.app_status = "stopped"

    def log(self, message: str) -> None:
        with self.lock:
            self.recent_messages.appendleft(message)

    def set_wake(self, text: str) -> None:
        with self.lock:
            self.last_wake = text

    def set_recognized(self, text: str) -> None:
        with self.lock:
            self.recognized_phrase = text

    def set_action(self, action: str) -> None:
        with self.lock:
            self.last_action = action

    def set_playing(self, track: str) -> None:
        with self.lock:
            if self.current_track:
                self.last_track = self.current_track
            self.current_track = track
            self.app_status = "playing"

    def clear_current_track(self, *, paused: bool = False, stopped: bool = False) -> None:
        with self.lock:
            if self.current_track:
                self.last_track = self.current_track
            if stopped:
                self.current_track = ""
                if self.engine_running:
                    self.app_status = "listening_wake"
                else:
                    self.app_status = "stopped"
            elif paused:
                self.app_status = "paused"

    def record_stt(
        self,
        text: str,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        audio_seconds: float | None = None,
    ) -> None:
        with self.lock:
            self.request_count += 1
            self.stt_calls += 1
            if audio_seconds:
                self.audio_seconds_est += audio_seconds
            if input_tokens is not None:
                self.input_tokens += input_tokens
            if output_tokens is not None:
                self.output_tokens += output_tokens
            if total_tokens is not None:
                self.total_tokens += total_tokens
            elif input_tokens is not None or output_tokens is not None:
                self.total_tokens += (input_tokens or 0) + (output_tokens or 0)

            cleaned = (text or "").strip()
            self.recognized_phrase = cleaned
            if cleaned:
                self.transcribed_lines += 1
                self.transcribed_chars += len(cleaned)

            self.recent_usage.appendleft(
                {
                    "text": cleaned,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "audio_seconds": audio_seconds,
                }
            )

    def record_web_play(self) -> None:
        with self.lock:
            self.web_play_count += 1
            self.request_count += 1

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "app_status": self.app_status,
                "engine_running": self.engine_running,
                "current_track": self.current_track,
                "last_track": self.last_track,
                "recognized_phrase": self.recognized_phrase,
                "last_wake": self.last_wake,
                "last_action": self.last_action,
                "request_count": self.request_count,
                "web_play_count": self.web_play_count,
                "transcribed_lines": self.transcribed_lines,
                "transcribed_chars": self.transcribed_chars,
                "stt_calls": self.stt_calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "audio_seconds_est": round(self.audio_seconds_est, 2),
                "mic_name": self.mic_name,
                "audio_device": self.audio_device,
                "recent_messages": list(self.recent_messages),
                "recent_usage": list(self.recent_usage),
            }
