# app/backend/database.py

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from app.backend.config import Config
from app.backend.models import Base

engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    echo=Config.SQLALCHEMY_ECHO,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Session = scoped_session(session_factory)


def init_db():
    """
    Create any missing tables and run lightweight migrations for new columns.
    Called once on app startup — safe to run repeatedly (idempotent).
    """
    from sqlalchemy import text, inspect

    # 1. Create brand-new tables that don't exist yet (e.g. folders)
    Base.metadata.create_all(engine)

    # 2. Add missing columns to EXISTING tables via ALTER TABLE
    inspector = inspect(engine)

    if 'documents' in inspector.get_table_names():
        doc_cols = [c['name'] for c in inspector.get_columns('documents')]
        if 'folder_id' not in doc_cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE documents ADD COLUMN folder_id INTEGER "
                    "REFERENCES folders(id) ON DELETE SET NULL"
                ))
            print("  ✓ Added folder_id column to documents table")

    print("Database tables synced successfully!")


@contextmanager
def get_db_session():
    """
    Context manager used as `with get_db_session() as db:`
    """
    db = Session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def close_db_session():
    """
    Called from app.teardown_appcontext to remove scoped session.
    """
    Session.remove()
