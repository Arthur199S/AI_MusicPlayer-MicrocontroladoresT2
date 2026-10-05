"""Medidor rapido do microfone + teste opcional de wake word (Vosk).

Uso:
  source .venv/bin/activate
  python -m scripts.test_mic          # so niveis (10 s)
  python -m scripts.test_mic --vosk   # niveis + texto parcial do Vosk
  python -m scripts.test_mic --seconds 20 --stereo
"""

from __future__ import annotations

import argparse
import array
import json
import os
import queue
import sys
import time


def _peak(samples: array.array) -> int:
    return max((abs(s) for s in samples), default=0)


def _bar(peak: int, width: int = 40) -> str:
    # int16 max ~32767
    filled = min(width, int(peak / 32767 * width))
    return "#" * filled + "-" * (width - filled)


def main() -> int:
    parser = argparse.ArgumentParser(description="Testa captura do microfone")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument(
        "--stereo",
        action="store_true",
        help="abre 2 canais e mostra peak L/R (VoiceHAT)",
    )
    parser.add_argument(
        "--vosk",
        action="store_true",
        help="mostra texto parcial do Vosk (precisa do modelo)",
    )
    parser.add_argument("--gain", type=float, default=12.0)
    args = parser.parse_args()

    try:
        import sounddevice as sd
    except ImportError:
        print("Instale dependencias: pip install -r requirements.txt", file=sys.stderr)
        return 1

    device = sd.query_devices(kind="input")
    print(f"Dispositivo: {device['name']}")
    print(
        f"Rate padrao: {int(device['default_samplerate'])} Hz | "
        f"canais max in: {device['max_input_channels']}"
    )

    channels = 2 if args.stereo else 1
    if channels > device["max_input_channels"]:
        print("Dispositivo nao tem canais suficientes; usando mono.")
        channels = 1

    rate = int(device["default_samplerate"])
    audio_q: queue.Queue[bytes] = queue.Queue()

    def callback(indata, frames, t, status) -> None:
        del frames, t
        if status:
            print(f"status: {status}", file=sys.stderr)
        audio_q.put(bytes(indata))

    recognizer = None
    downsample = 1
    if args.vosk:
        model_path = os.environ.get(
            "VOSK_MODEL_PATH", "models/vosk-model-small-pt-0.3"
        )
        from vosk import KaldiRecognizer, Model

        from src.command_parser import contains_wake_word

        model = Model(model_path)
        vosk_rate = 16_000
        if rate % vosk_rate != 0:
            print(f"Rate {rate} nao e multipla de 16000; sem Vosk.")
        else:
            downsample = rate // vosk_rate
            recognizer = KaldiRecognizer(model, vosk_rate)
            print(f"Vosk ativo (downsample x{downsample}). Fale a wake word.")

    print()
    print("Fale perto do mic. Ctrl+C para sair.")
    print("peak |0=silencio ... 32767=estouro|")
    print()

    started = time.monotonic()
    max_peak = 0
    wake_hits = 0

    with sd.RawInputStream(
        samplerate=rate,
        blocksize=max(rate // 4, 1024),
        dtype="int16",
        channels=channels,
        callback=callback,
    ):
        while time.monotonic() - started < args.seconds:
            try:
                data = audio_q.get(timeout=0.5)
            except queue.Empty:
                continue

            samples = array.array("h")
            samples.frombytes(data)

            if channels == 2:
                left = array.array("h", samples[0::2])
                right = array.array("h", samples[1::2])
                pl, pr = _peak(left), _peak(right)
                peak = max(pl, pr)
                line = (
                    f"L[{_bar(pl)}] {pl:5d}  "
                    f"R[{_bar(pr)}] {pr:5d}"
                )
                mono_for_vosk = left
            else:
                peak = _peak(samples)
                line = f"M[{_bar(peak)}] {peak:5d}"
                mono_for_vosk = samples

            max_peak = max(max_peak, peak)
            print(f"\r{line}   max={max_peak:5d}", end="", flush=True)

            if recognizer is not None:
                # aplica ganho + downsample como no app
                amplified = array.array("h")
                for sample in mono_for_vosk:
                    value = int(sample * args.gain)
                    if value > 32767:
                        value = 32767
                    elif value < -32768:
                        value = -32768
                    amplified.append(value)
                if downsample > 1:
                    amplified = array.array("h", amplified[::downsample])
                pcm = amplified.tobytes()
                if recognizer.AcceptWaveform(pcm):
                    text = json.loads(recognizer.Result()).get("text", "")
                else:
                    text = json.loads(recognizer.PartialResult()).get(
                        "partial", ""
                    )
                if text:
                    mark = " << WAKE" if contains_wake_word(text) else ""
                    if mark:
                        wake_hits += 1
                    print(f"\n  vosk: {text!r}{mark}")

    print()
    print()
    print("--- resultado ---")
    print(f"peak maximo: {max_peak}")
    if max_peak < 200:
        print(
            "SINAL QUASE ZERO: mic sem captura util, cabo/HAT, "
            "ou canal errado. Tente --stereo."
        )
        return 2
    if max_peak < 1500:
        print(
            "Sinal fraco: fale mais perto ou suba ganho. "
            "Wake word pode falhar."
        )
        return 3
    print("Sinal OK (ha energia no mic).")
    if args.vosk:
        if wake_hits:
            print(f"Wake word detectada {wake_hits}x pelo Vosk.")
        else:
            print(
                "Vosk nao detectou wake word nesta janela. "
                "Tente 'assistente' / 'jarvis' bem claro."
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrompido.")
        raise SystemExit(130)
