"""
AegisAI - Database Connection Management
SQLAlchemy Engine and Session Factory

Supports:
- SQLite (default): sqlite:///data/aegis.db
- PostgreSQL: postgresql://user:pass@host:port/db
"""

import os
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# Configure module logger
logger = logging.getLogger(__name__)

# SQLAlchemy declarative base
Base = declarative_base()

# Global engine and session factory
_engine = None
_SessionFactory = None


def get_database_url() -> str:
    """
    Get database URL from environment or use default SQLite.
    
    Returns:
        Database connection URL
    """
    url = os.environ.get("DATABASE_URL")
    
    if url:
        logger.info(f"Using database from DATABASE_URL")
        return url
    
    # Default to SQLite in data directory
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    sqlite_path = data_dir / "aegis.db"
    default_url = f"sqlite:///{sqlite_path}"
    
    logger.info(f"Using default SQLite database: {sqlite_path}")
    return default_url


def get_engine(url: Optional[str] = None):
    """
    Get or create the database engine.
    
    Args:
        url: Optional database URL override
        
    Returns:
        SQLAlchemy Engine
    """
    global _engine
    
    if _engine is None:
        db_url = url or get_database_url()
        
        # Configure engine based on database type
        if db_url.startswith("sqlite"):
            _engine = create_engine(
                db_url,
                echo=False,
                connect_args={"check_same_thread": False}  # SQLite threading
            )
        else:
            _engine = create_engine(
                db_url,
                echo=False,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True  # Verify connections
            )
        
        logger.info(f"Database engine created")
    
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _SessionFactory
    
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    
    return _SessionFactory


def init_db(url: Optional[str] = None) -> None:
    """
    Initialize the database (create tables).
    
    Args:
        url: Optional database URL override
    """
    engine = get_engine(url)
    
    # Import models to register with Base
    from aegis.db import models  # noqa: F401
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    logger.info("Database initialized - tables created")


def drop_db() -> None:
    """Drop all database tables. USE WITH CAUTION."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    logger.warning("Database tables dropped")


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Get a database session with automatic cleanup.
    
    Usage:
        with get_session() as session:
            repo = EventRepository(session)
            events = repo.get_recent()
    
    Yields:
        SQLAlchemy Session
    """
    factory = get_session_factory()
    session = factory()
    
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_db() -> None:
    """Close database connections and reset globals."""
    global _engine, _SessionFactory
    
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionFactory = None
        logger.info("Database connections closed")
