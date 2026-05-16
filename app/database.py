import os
import logging
from sqlmodel import SQLModel, create_engine, Session
from typing import Generator
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:12345@localhost:5432/math_app_db")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Production: echo=False, pool settings optimal
# Development: echo=True untuk debug SQL queries
engine = create_engine(
    DATABASE_URL,
    echo=DEBUG,
    pool_size=5,           # Jumlah koneksi di pool
    max_overflow=10,       # Koneksi tambahan saat pool penuh
    pool_pre_ping=True,    # Cek koneksi masih hidup sebelum dipakai
    pool_recycle=300,       # Recycle koneksi setiap 5 menit (cegah timeout)
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session