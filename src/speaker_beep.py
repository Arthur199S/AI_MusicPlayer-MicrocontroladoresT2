"""Feedback sonoro pelo alto-falante / jack analogico do Pi."""

from __future__ import annotations

import array
import math
import os
import time


class SpeakerBeepError(RuntimeError):
    """Falha ao tocar bip no alto-falante."""


def _tone_pcm(
    frequency_hz: float,
    duration: float,
    sample_rate: int,
    channels: int,
    gain: float,
) -> bytes:
    total = max(int(sample_rate * duration), 1)
    fade = max(int(sample_rate * 0.01), 1)
    pcm = array.array("h")
    two_pi_f = 2.0 * math.pi * frequency_hz
    for index in range(total):
        envelope = 1.0
        if index < fade:
            envelope = index / fade
        elif index > total - fade:
            envelope = max(total - index, 0) / fade
        value = int(
            gain * envelope * 32767.0 * math.sin(two_pi_f * index / sample_rate)
        )
        if value > 32767:
            value = 32767
        elif value < -32767:
            value = -32767
        for _ in range(channels):
            pcm.append(value)
    return pcm.tobytes()


def _pick_output_device(sounddevice, preferred: int | str | None) -> int | str | None:
    """Escolhe o device onde o som realmente sai.

    No setup deste projeto o audio util e o jack analogico
    ``bcm2835 Headphones`` (ALSA hw:3,0 / PortAudio index tipico 1),
    nao o Voice HAT I2S (sem caixa ligada).
    """
    if preferred is not None and preferred != "":
        return preferred

    env = os.environ.get("SPEAKER_DEVICE", "").strip()
    if env:
        return int(env) if env.isdigit() else env

    devices = sounddevice.query_devices()
    # Preferencias por nome (ordem importa).
    keywords = (
        "headphones",
        "bcm2835",
        "headphone",
        "analog",
    )
    for keyword in keywords:
        for index, device in enumerate(devices):
            if device.get("max_output_channels", 0) <= 0:
                continue
            name = str(device.get("name", "")).lower()
            if keyword in name:
                return index

    # Ultimo recurso: saida padrao do sistema.
    return None


class SpeakerBeep:
    """Toca um bip curto no jack/alto-falante configurado."""

    def __init__(
        self,
        frequency_hz: float = 880.0,
        duration: float = 0.18,
        gain: float = 0.45,
        device: int | str | None = None,
    ) -> None:
        try:
            import sounddevice as sounddevice
        except ImportError as error:
            raise SpeakerBeepError(
                "instale sounddevice com 'pip install -r requirements.txt'"
            ) from error

        self._sounddevice = sounddevice
        self.device = _pick_output_device(sounddevice, device)

        self.frequency_hz = float(os.environ.get("SPEAKER_BEEP_FREQ", frequency_hz))
        self.duration = float(os.environ.get("SPEAKER_BEEP_DURATION", duration))
        self.gain = float(os.environ.get("SPEAKER_BEEP_GAIN", gain))

        out = sounddevice.query_devices(self.device, kind="output")
        self.device_name = out["name"]
        self.sample_rate = int(out["default_samplerate"])
        # Headphones ALSA costuma reportar muitos canais; usar stereo.
        max_out = int(out["max_output_channels"])
        self.channels = 2 if max_out >= 2 else max(1, max_out)

    def beep(self, count: int = 1, gap: float = 0.08) -> None:
        pcm = _tone_pcm(
            self.frequency_hz,
            self.duration,
            self.sample_rate,
            self.channels,
            self.gain,
        )
        for index in range(count):
            with self._sounddevice.RawOutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=self.device,
            ) as stream:
                stream.write(pcm)
            if index + 1 < count:
                time.sleep(gap)

    def close(self) -> None:
        return
