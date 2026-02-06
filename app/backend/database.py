"""
Database connection and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.backend.config import Config
from app.backend.models import Base

# Create database engine
engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    echo=Config.SQLALCHEMY_ECHO,
    pool_pre_ping=True,  # Verify connections before using them
    pool_size=10,
    max_overflow=20
)

# Create session factory
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(engine)
    print("Database tables created successfully!")


def get_db_session():
    """Get a new database session"""
    return Session()


def close_db_session():
    """Close the current database session"""
    Session.remove()
