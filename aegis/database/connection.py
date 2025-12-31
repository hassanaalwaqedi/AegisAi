"""
AegisAI - PostgreSQL Database Connection

Production-ready PostgreSQL connection with connection pooling and async support.
"""

import os
import logging
from typing import Optional, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
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
        bind=_engine
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
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")


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
