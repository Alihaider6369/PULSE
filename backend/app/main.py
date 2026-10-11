from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.posture_events import router as posture_router
from app.api.sessions import router as sessions_router
from app.api.settings import router as settings_router
from app.api.live import router as live_router

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="PULSE API", version="0.1.0")
app.include_router(sessions_router)
app.include_router(posture_router)
app.include_router(settings_router)
app.include_router(live_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PULSE API"}


app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/")
def dashboard():
    
    return FileResponse(FRONTEND_DIR / "index.html")
@app.get("/settings.html")
def settings_page():
    return FileResponse(FRONTEND_DIR / "settings.html")
@app.get("/history.html")
def history_page():
    return FileResponse(FRONTEND_DIR / "history.html")
@app.get("/live.html")
def live_page():
    return FileResponse(FRONTEND_DIR / "live.html")