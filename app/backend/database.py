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
    Base.metadata.create_all(engine)
    print("Database tables created successfully!")


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
