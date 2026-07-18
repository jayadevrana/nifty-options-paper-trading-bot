from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .engine import PaperTradingEngine


BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="NIFTY Paper Trader")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
engine = PaperTradingEngine()


@app.on_event("startup")
async def startup_event() -> None:
    await engine.start()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/state")
async def api_state() -> dict:
    return await engine.state()


@app.post("/api/control/start")
async def api_start() -> dict:
    return await engine.set_enabled(True)


@app.post("/api/control/stop")
async def api_stop() -> dict:
    return await engine.set_enabled(False)


@app.post("/api/control/preview")
async def api_preview() -> dict:
    return await engine.preview()
