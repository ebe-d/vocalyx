from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables in the database."""
    # Import models here to ensure they are registered with Base before create_all
    try:
        import backend.models  # noqa: F401
    except ImportError:
        import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Safe column migration for existing SQLite databases
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE contacts ADD COLUMN preferred_language VARCHAR DEFAULT 'en-US'"))
            conn.commit()
        except Exception:
            pass  # Column already exists
