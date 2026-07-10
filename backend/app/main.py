from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.compliance_routes import router as compliance_router
from app.api.routes import router
from app.config import get_settings
from app.database import init_db

settings = get_settings()
settings.storage_path

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _resolve_frontend_dir() -> Path | None:
    """Find the static frontend directory in local and Docker layouts."""
    candidates = [
        Path("frontend"),
        Path(__file__).resolve().parents[1] / "frontend",
        Path(__file__).resolve().parents[2] / "frontend",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


app.include_router(router)
app.include_router(compliance_router)

frontend_dir = _resolve_frontend_dir()
if frontend_dir is not None:
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
