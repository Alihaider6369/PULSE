import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from app.api.auth import router as auth_router
from app.api.live import router as live_router
from app.api.posture_events import router as posture_router
from app.api.sessions import router as sessions_router
from app.api.settings import router as settings_router
from app.core.config import settings

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="PULSE API",
    version="0.2.0",
    description="Ergonomic desk posture tracking and awareness system API",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Format validation errors into clear client-facing messages."""
    errors = exc.errors()
    for err in errors:
        loc = err.get("loc", ())
        msg = err.get("msg", "")
        if "email" in loc:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": "Enter a valid email address"},
            )
        if ("password" in loc or "new_password" in loc) and ("8" in msg or "length" in msg):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": "Password must be at least 8 characters long"},
            )
    msg = errors[0].get("msg", "Validation error") if errors else "Validation error"
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": msg},
    )


@app.exception_handler(OperationalError)
async def db_operational_exception_handler(request: Request, exc: OperationalError):
    """Handle database connection or operational failures gracefully without crashing."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database service is temporarily unavailable. Please try again shortly."},
    )



# CORS Middleware for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(posture_router)
app.include_router(settings_router)
app.include_router(live_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PULSE API", "version": "0.2.0"}


# Static Assets & Frontend Pages
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/favicon.ico")
def favicon():
    ico_file = Path(__file__).resolve().parents[2] / "desktop_app" / "resources" / "pulse.ico"
    if ico_file.exists():
        return FileResponse(ico_file)
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.get("/")
@app.get("/index")
@app.get("/index.html")
def dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/settings")
@app.get("/settings.html")
def settings_page():
    return FileResponse(FRONTEND_DIR / "settings.html")


@app.get("/history")
@app.get("/history.html")
def history_page():
    return FileResponse(FRONTEND_DIR / "history.html")


@app.get("/live")
@app.get("/live.html")
def live_page():
    return FileResponse(FRONTEND_DIR / "live.html")


@app.get("/reset-password")
@app.get("/reset-password.html")
def reset_password_page():
    reset_file = FRONTEND_DIR / "reset-password.html"
    if reset_file.exists():
        return FileResponse(reset_file)
    return FileResponse(FRONTEND_DIR / "index.html")