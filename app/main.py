import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_db_and_tables
from app.routes import auth, soal, ujian

load_dotenv()

# --- Logging Setup ---
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEBUG = os.getenv("DEBUG", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Mencoba koneksi ke Database...")
    try:
        create_db_and_tables()
        logger.info("BERHASIL! Tabel sudah dibuat (jika belum ada).")
    except Exception as e:
        logger.error(f"GAGAL KONEK DATABASE: {e}")

    yield

    logger.info("Server mati, koneksi diputus.")


app = FastAPI(
    lifespan=lifespan,
    title="Fun AR Math API",
    description="Backend API untuk aplikasi Fun AR Math",
    version="1.0.0",
    # Matikan docs di production (opsional, bisa dihapus kalau mau tetap aktif)
    docs_url="/docs" if DEBUG else "/docs",
    redoc_url="/redoc" if DEBUG else None,
)

# --- CORS Middleware ---
# Untuk Flutter mobile app, kita perlu allow all origins
# Karena request dari app bukan dari browser domain tertentu
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "*")
if allowed_origins_str == "*":
    origins = ["*"]
else:
    origins = [o.strip() for o in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register Routers ---
app.include_router(soal.router)
app.include_router(auth.router)
app.include_router(ujian.router)


@app.get("/")
def read_root():
    return {"msg": "Server Jalan, Database Aman!"}