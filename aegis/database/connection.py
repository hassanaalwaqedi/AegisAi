"""
AegisAI - PostgreSQL Database Connection

Production-ready PostgreSQL connection with connection pooling and async support.
"""

import os
import logging
from typing import Optional, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# SQLAlchemy Base for all models
Base = declarative_base()

# Global engine and session factory
_engine = None
_SessionLocal = None


def get_database_url() -> str:
    """Get database URL from environment or use default."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://aegis:aegis_secret@localhost:5432/aegisai"
    )


def init_engine(database_url: str = None):
    """Initialize the database engine with connection pooling."""
    global _engine, _SessionLocal
    
    if _engine is not None:
        return _engine
    
    url = database_url or get_database_url()
    
    _engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=os.getenv("AEGIS_DEBUG", "false").lower() == "true",
    )
    
    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=_engine,
        # Service methods may safely return newly-created ORM projections after
        # their transaction completes, without issuing a second database read.
        expire_on_commit=False,
    )
    
    logger.info("Database engine initialized")
    return _engine


def get_engine():
    """Get the current database engine, initializing if needed."""
    if _engine is None:
        init_engine()
    return _engine


def get_session() -> Generator[Session, None, None]:
    """Get a database session (dependency injection pattern)."""
    if _SessionLocal is None:
        init_engine()
    
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database sessions."""
    if _SessionLocal is None:
        init_engine()
    
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_tables():
    """Create all tables from models."""
    # Importing the model module registers every mapped table on this
    # connection module's shared SQLAlchemy Base before create_all runs.
    from . import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _upgrade_legacy_event_schema(engine)
    logger.info("Database tables created")


def _upgrade_legacy_event_schema(engine) -> None:
    """Add event evidence fields absent from pre-Phase-4 PostgreSQL installs.

    ``create_all`` intentionally does not modify tables that already exist.
    That left long-lived Aegis installations with an older ``events`` table,
    while the intelligence context now reads the newer evidence columns.  The
    small compatibility upgrade below is deliberately additive: it leaves all
    existing rows untouched and makes only nullable columns available.  Proper
    structural migrations should supersede this bridge when Alembic is added.
    """
    if engine.dialect.name != "postgresql":
        return

    event_table = Base.metadata.tables.get("events")
    if event_table is None:
        return

    inspector = inspect(engine)
    if "events" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("events")}
    missing_columns = [
        column
        for column in event_table.columns
        if not column.primary_key and column.name not in existing_columns
    ]
    if not missing_columns:
        return

    # Names come from the mapped model rather than external input.  Retaining
    # the explicit quoting protects reserved physical names such as metadata.
    with engine.begin() as connection:
        for column in missing_columns:
            sql_type = column.type.compile(dialect=engine.dialect)
            connection.execute(
                text(
                    f'ALTER TABLE "events" ADD COLUMN IF NOT EXISTS '
                    f'"{column.name}" {sql_type}'
                )
            )

    logger.warning(
        "Upgraded legacy events schema with missing evidence columns: %s",
        ", ".join(column.name for column in missing_columns),
    )


def check_connection() -> bool:
    """Check if database connection is working."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
