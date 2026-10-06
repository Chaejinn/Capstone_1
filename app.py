"""Vercel entrypoint: API and frontend share one origin."""
from backend.app.main import app as backend_app
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from backend.app import config

app = FastAPI(lifespan=backend_app.router.lifespan_context)
app.mount("/api", backend_app)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/index.html")


if not config.IS_VERCEL:
    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "code"), name="frontend")
