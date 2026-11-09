"""Entry point: dashboard FastAPI + motor de voz controlavel."""

from __future__ import annotations

import os
import threading

from dotenv import load_dotenv

from .app_state import AppState
from .dashboard import create_app
from .player import Player
from .ubidots_mqtt import UbidotsMqttBridge
from .voice_engine import VoiceEngine


def respond(message: str) -> None:
    print(f"AI Music Player: {message}", flush=True)


def run() -> None:
    load_dotenv()

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        respond(
            "Defina OPENAI_API_KEY no arquivo .env (veja .env.example) "
            "antes de iniciar."
        )
        return

    port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1").strip() or "127.0.0.1"
    autostart = os.environ.get("ENGINE_AUTOSTART", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

    state = AppState()
    player = Player()
    state.audio_device = player.audio_device
    engine = VoiceEngine(state, player, respond=respond)
    ubidots = UbidotsMqttBridge(state, player, engine=engine, respond=respond)
    app = create_app(state, player, engine, bridge=ubidots)

    try:
        import uvicorn
    except ImportError:
        respond(
            "Instale as dependencias do dashboard: "
            "pip install -r requirements.txt"
        )
        return

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    def _serve() -> None:
        server.run()

    thread = threading.Thread(target=_serve, name="dashboard", daemon=True)
    thread.start()

    token = os.environ.get("DASHBOARD_TOKEN", "").strip()
    respond(f"Dashboard em http://{host}:{port}/")
    if token:
        respond("Auth: use ?token=... ou Authorization Bearer (DASHBOARD_TOKEN).")
    else:
        respond(
            "DASHBOARD_TOKEN nao definido — dashboard so aceita localhost. "
            "Defina no .env antes de usar ngrok."
        )
    if autostart:
        engine.start()
        respond("Motor de voz: autostart ligado.")
    else:
        respond("Motor de voz parado. Use Start no dashboard ou ENGINE_AUTOSTART=1.")

    ubidots.start()

    try:
        thread.join()
    except KeyboardInterrupt:
        respond("Encerrando.")
    finally:
        ubidots.stop()
        engine.stop(stop_audio=True)
        server.should_exit = True


if __name__ == "__main__":
    run()
