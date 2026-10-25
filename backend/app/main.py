"""Unified platform: authentication, camera, judgement and boat APIs."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.platform import config as platform_config, main as platform
from backend.platform.routers import auth, users, sites, settings, contacts, audit
from backend.platform.routers import camera, events as platform_events, ai_bridge as platform_ai, ws as platform_ws
from backend.platform.routers import camera_analysis
from backend.platform.routers import test_signals, test_control, test_push
from .database import Base, SessionLocal, engine
from .routers import ai_bridge, boat, calibration, config_router, events, judgement, mission, status, ws
from .services import config_service


@asynccontextmanager
async def lifespan(application):
    # Both model sets register with the same Base before platform schema creation.
    async with platform.lifespan(application):
        if not platform_config.IS_VERCEL:
            with platform.SessionLocal() as db:
                config_service.get_active_config(db)
        try:
            yield
        finally:
            from backend.platform.test_automation import automation
            await automation.stop()
            if not platform_config.IS_VERCEL:
                from .dispatch.guidance_controller import guidance_controller
                from .dispatch.dispatch_manager import dispatch_manager
                import asyncio
                task = guidance_controller._task
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                dispatch_manager.clear_active()


app = FastAPI(title="Drown Guardian 통합 서버", version="1.1.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")

for router in (auth.router, users.router, sites.router, settings.router, contacts.router,
               audit.router, platform_events.router, platform_ai.router, boat.router, camera_analysis.router,
               test_signals.router, test_control.router, test_push.router):
    app.include_router(router, prefix="/api")
app.add_api_route("/api/maintenance/reset", platform.reset, methods=["POST"], tags=["maintenance"])
if platform_config.CAMERA_ENABLED:
    app.include_router(camera.router, prefix="/api")
if not platform_config.IS_VERCEL:
    app.include_router(platform_ws.router, prefix="/api")
    for router in (status.router, config_router.router, calibration.router, events.router,
                   mission.router, judgement.router, ai_bridge.router, ws.router):
        app.include_router(router)


@app.get("/api/health")
def health():
    return {**platform.health(), "judgement_enabled": not platform_config.IS_VERCEL}


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/index.html")


if not platform_config.IS_VERCEL:
    @app.middleware('http')
    async def disable_local_page_cache(request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith(('/api/', '/ws')):
            response.headers['Cache-Control'] = 'no-store, max-age=0'
        return response

    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "code"), name="frontend")
