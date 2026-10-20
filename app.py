"""Unified local and Vercel entrypoint."""
from backend.app.main import app
from backend.platform import config, main as platform_backend
