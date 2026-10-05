"""Teste de feedback sonoro: alto-falante (padrao) ou GPIO piezo.

Uso:
  python -m scripts.test_buzzer                 # bip no alto-falante Voice HAT
  python -m scripts.test_buzzer --gpio          # GPIO Driver P2 (piezo)
  python -m scripts.test_buzzer --gpio --scan
"""

from __future__ import annotations

import argparse
import sys
import time


VOICEHAT_DRIVERS = {
    0: 4,
    1: 17,
    2: 27,
    3: 22,
}


def _beep_speaker(count: int, duration: float, freq: float, device: str | None) -> None:
    from src.speaker_beep import SpeakerBeep

    resolved = None
    if device is not None:
        resolved = int(device) if device.isdigit() else device
    beep = SpeakerBeep(frequency_hz=freq, duration=duration, device=resolved)
    print(f"Speaker device: {beep.device!r}")
    print(f"Speaker name:   {beep.device_name} ({beep.sample_rate} Hz, {beep.channels} ch)")
    print(f"Tocando bip x{count} ({freq:.0f} Hz, {duration:.2f}s)...")
    beep.beep(count=count)
    print("ok — se ouviu, e este o device certo para a wake word.")


def _beep_gpio(
    pin: int,
    duration: float,
    count: int,
    active_high: bool,
    mode: str,
    frequency_hz: int,
) -> None:
    from src.buzzer import Buzzer

    with Buzzer(
        pin=pin,
        active_high=active_high,
        mode=mode,
        frequency_hz=frequency_hz,
    ) as buzzer:
        print(
            f"GPIO {pin}: bip x{count} mode={mode} "
            f"freq={frequency_hz}Hz ({duration:.2f}s)..."
        )
        buzzer.beep(duration=duration, count=count)
        print(f"GPIO {pin}: comando enviado (piezo; nao sai no alto-falante)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Testa bip de feedback (speaker ou GPIO)"
    )
    parser.add_argument(
        "--gpio",
        action="store_true",
        help="usa piezo no GPIO em vez do alto-falante",
    )
    parser.add_argument("--pin", type=int, default=None)
    parser.add_argument("--driver", type=int, choices=sorted(VOICEHAT_DRIVERS))
    parser.add_argument("--duration", type=float, default=0.2)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--freq", type=float, default=880.0)
    parser.add_argument("--mode", choices=("tone", "active"), default="tone")
    parser.add_argument("--active-low", action="store_true")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--hold", type=float, default=0.0)
    parser.add_argument(
        "--device",
        default=None,
        help="indice PortAudio ou nome (padrao: bcm2835 Headphones)",
    )
    args = parser.parse_args()

    try:
        if not args.gpio:
            if args.scan or args.hold:
                print(
                    "Aviso: --scan/--hold sao so para --gpio. "
                    "Tocando bip no speaker.",
                    file=sys.stderr,
                )
            _beep_speaker(args.count, args.duration, args.freq, args.device)
            print(
                "Se nao ouvir: SPEAKER_DEVICE=1  "
                "(Headphones hw:3,0 — mesmo do speaker-test plughw:3,0)"
            )
            return 0

        active_high = not args.active_low
        gpio_freq = int(args.freq) if args.freq >= 100 else 2000

        if args.scan:
            print(f"Scan Drivers 0-3 (mode={args.mode}).")
            for driver, pin in VOICEHAT_DRIVERS.items():
                print(f"\n=== Driver {driver} (GPIO {pin}) ===")
                _beep_gpio(
                    pin, args.duration, 1, active_high, args.mode, gpio_freq
                )
                time.sleep(0.6)
            return 0

        if args.driver is not None:
            pin = VOICEHAT_DRIVERS[args.driver]
        elif args.pin is not None:
            pin = args.pin
        else:
            pin = 27

        if args.hold > 0:
            from src.buzzer import Buzzer

            with Buzzer(
                pin=pin,
                active_high=active_high,
                mode=args.mode,
                frequency_hz=gpio_freq,
            ) as buzzer:
                print(f"GPIO {pin}: ON {args.hold:.1f}s")
                buzzer.on()
                time.sleep(args.hold)
                buzzer.off()
            return 0

        _beep_gpio(
            pin, args.duration, args.count, active_high, args.mode, gpio_freq
        )
        return 0
    except Exception as error:  # noqa: BLE001
        print(f"ERRO: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
