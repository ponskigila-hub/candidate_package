"""SQLite via SQLAlchemy.

Why SQLite: ~2,000 rows is trivial for any datastore. SQLite needs zero setup
(no separate server/process), supports SQL filtering/search out of the box
(unlike an in-memory dict, which would mean hand-rolling query logic), and is
trivially swappable for Postgres later (same SQLAlchemy models, just change
the connection URL) if this ever needed to run multi-process.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./leadflow.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
