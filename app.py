"""Vercel entrypoint: API and frontend share one origin."""
from backend.app.main import app as backend_app
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

app = FastAPI(lifespan=backend_app.router.lifespan_context)
app.mount("/api", backend_app)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/index.html")
