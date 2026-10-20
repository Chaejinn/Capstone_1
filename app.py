"""Vercel entrypoint: API and frontend share one origin."""
from importlib import import_module
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# The platform frontend requires auth/sites/users from the platform backend.
# backend.app is the separate, single-site judgement server.
platform_backend = import_module("backend(org).app.main")
backend_app = platform_backend.app
config = import_module("backend(org).app.config")
boat_router = import_module("backend.app.routers.boat").router
backend_app.include_router(boat_router)

judgement_app = None
if not config.IS_VERCEL:
    judgement_app = import_module("backend.app.main").app


@asynccontextmanager
async def lifespan(application):
    # Mounted applications do not receive startup/shutdown automatically.
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(backend_app.router.lifespan_context(backend_app))
        if judgement_app is not None:
            await stack.enter_async_context(judgement_app.router.lifespan_context(judgement_app))
        yield


app = FastAPI(lifespan=lifespan)
app.mount("/api", backend_app)
if judgement_app is not None:
    app.mount("/judgement", judgement_app)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/index.html")


if not config.IS_VERCEL:
    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "code"), name="frontend")
