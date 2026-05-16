import os
import logging
from sqlmodel import SQLModel, create_engine, Session
from typing import Generator
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# LAZY ENGINE: Jangan buat engine saat import,
# buat saat pertama kali dibutuhkan.
# Ini mencegah crash di server kalau DATABASE_URL belum di-set.
_engine = None


def get_engine():
    """Buat engine hanya saat pertama kali dipanggil."""
    global _engine
    if _engine is None:
        db_url = DATABASE_URL
        if not db_url:
            raise RuntimeError(
                "DATABASE_URL belum di-set! "
                "Cek file .env atau environment variable di cPanel."
            )
        _engine = create_engine(
            db_url,
            echo=DEBUG,
            pool_size=2,            # Shared hosting: pakai pool kecil!
            max_overflow=3,         # Maksimal 5 koneksi total (2+3)
            pool_pre_ping=True,
            pool_recycle=300,
        )
        logger.info("Database engine berhasil dibuat.")
    return _engine


def create_db_and_tables():
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session