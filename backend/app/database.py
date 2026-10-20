"""Shared database, metadata and sessions for platform and judgement modules."""
from backend.platform.database import Base, SessionLocal, engine, get_db
