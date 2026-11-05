from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from . import config

connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=connect_args,
                       # Bound connections per warm Vercel worker. NullPool forces
                       # a fresh remote TCP/TLS connection on every camera request.
                       # User/site permissions are still queried on every request.
                       **({"pool_size": 2, "max_overflow": 1, "pool_timeout": 10,
                           "pool_recycle": 240, "pool_pre_ping": True}
                          if config.IS_VERCEL else {"pool_pre_ping": True}))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
