"""Dashboard web FastAPI: metricas, controles e start/stop do motor."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .app_state import AppState
from .player import Player, PlayerError
from .system_metrics import system_metrics
from .voice_engine import VoiceEngine
from .youtube_search import YouTubeSearchError, find_audio

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class PlayBody(BaseModel):
    query: str = Field(min_length=1)


def create_app(
    state: AppState,
    player: Player,
    engine: VoiceEngine,
    bridge: Any | None = None,
) -> FastAPI:
    app = FastAPI(title="AI Music Player Dashboard", docs_url=None, redoc_url=None)
    expected_token = os.environ.get("DASHBOARD_TOKEN", "").strip()

    def require_auth(
        request: Request,
        authorization: str | None = Header(default=None),
        token: str | None = Query(default=None),
    ) -> None:
        if not expected_token:
            client = request.client.host if request.client else ""
            if client in ("127.0.0.1", "::1"):
                return
            raise HTTPException(
                status_code=401,
                detail="Defina DASHBOARD_TOKEN no .env para acesso remoto (ngrok).",
            )
        provided = token
        if not provided and authorization:
            parts = authorization.split(" ", 1)
            provided = parts[1].strip() if len(parts) == 2 else authorization.strip()
        if provided != expected_token:
            raise HTTPException(status_code=401, detail="Token invalido.")

    @app.get("/", response_class=HTMLResponse)
    def index(_: None = Depends(require_auth)) -> HTMLResponse:
        html_path = TEMPLATES_DIR / "dashboard.html"
        html = html_path.read_text(encoding="utf-8")
        # Injeta token no JS para as chamadas fetch (query string).
        safe_token = expected_token.replace("\\", "\\\\").replace('"', '\\"')
        html = html.replace("__DASHBOARD_TOKEN__", safe_token)
        return HTMLResponse(html)

    @app.get("/live", response_class=HTMLResponse)
    def live(_: None = Depends(require_auth)) -> HTMLResponse:
        html = (TEMPLATES_DIR / "live.html").read_text(encoding="utf-8")
        safe_token = expected_token.replace("\\", "\\\\").replace('"', '\\"')
        return HTMLResponse(html.replace("__DASHBOARD_TOKEN__", safe_token))

    @app.get("/api/ubidots")
    def ubidots_values(_: None = Depends(require_auth)) -> JSONResponse:
        if bridge is None:
            return JSONResponse(
                {"sent": {}, "remote": {"enabled": False, "error": "bridge off", "variables": {}}}
            )
        return JSONResponse(
            {
                "device": bridge.device_label,
                "connected": bridge.connected,
                "sent": bridge.build_payload(),
                "remote": bridge.fetch_remote(),
            }
        )

    @app.get("/api/status")
    def status(_: None = Depends(require_auth)) -> JSONResponse:
        payload = state.snapshot()
        payload["system"] = system_metrics()
        payload["playback"] = player.playback_snapshot()
        payload["engine_running"] = engine.running or payload["engine_running"]
        return JSONResponse(payload)

    @app.post("/api/pause")
    def pause(_: None = Depends(require_auth)) -> dict[str, str]:
        try:
            player.set_pause(True)
        except PlayerError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        state.clear_current_track(paused=True)
        state.log("Pause via dashboard.")
        return {"ok": "paused"}

    @app.post("/api/resume")
    def resume(_: None = Depends(require_auth)) -> dict[str, str]:
        try:
            player.set_pause(False)
        except PlayerError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        state.set_status("playing")
        state.log("Resume via dashboard.")
        return {"ok": "resumed"}

    @app.post("/api/stop")
    def stop_music(_: None = Depends(require_auth)) -> dict[str, str]:
        try:
            player.stop()
        except PlayerError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        state.clear_current_track(stopped=True)
        state.log("Stop via dashboard.")
        return {"ok": "stopped"}

    @app.post("/api/play")
    def play(body: PlayBody, _: None = Depends(require_auth)) -> dict[str, str]:
        query = body.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="query vazia")
        try:
            audio = find_audio(query)
            player.play(audio.url)
        except (PlayerError, YouTubeSearchError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        state.record_web_play()
        state.set_playing(audio.title)
        state.log(f"Play via dashboard: {audio.title} (busca: {query})")
        return {"ok": "playing", "query": query, "title": audio.title}

    @app.post("/api/engine/start")
    def engine_start(_: None = Depends(require_auth)) -> dict[str, Any]:
        started = engine.start()
        return {"ok": True, "started": started, "running": engine.running}

    @app.post("/api/engine/stop")
    def engine_stop(_: None = Depends(require_auth)) -> dict[str, Any]:
        engine.stop(stop_audio=True)
        return {"ok": True, "running": engine.running}

    return app
