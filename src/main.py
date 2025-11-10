"""
Main FastAPI application entry point.
"""
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path

from src.api import routes
from src.logging_config import setup_logging

# --- Setup Logging ---
setup_logging()

# --- Setup App ---
app = FastAPI(
    title="Toxic Combo Scanner",
    description="API for detecting Segregation of Duties (SoD) violations.",
    version="0.1.0"
)

logger = logging.getLogger(__name__)

app.include_router(routes.router, prefix="/api/v1")

# --- Static Files Mount ---
static_dir = Path("src/ui")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# --- UI Route ---
@app.get("/")
async def serve_ui():
    """Serves the main index.html file."""
    index_path = static_dir / "index.html"
    if not index_path.exists():
        logger.error(f"CRITICAL: index.html not found at {index_path}")
        return "UI file not found. Please check server configuration."
    return FileResponse(index_path)

@app.get("/ui")
async def redirect_to_root():
    """Redirect from the old /ui path."""
    return RedirectResponse(url="/")