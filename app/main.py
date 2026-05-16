import os
import sys
import logging

# =========================================================
# FIX UNTUK CPANEL/PASSENGER UnicodeEncodeError:
# Jangan dihapus! Passenger default ke ASCII, sehingga 
# string yang ada karakter unik (seperti ²) akan crash.
# =========================================================
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# --- Logging Setup ---
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ============================================
# JANGAN PAKAI lifespan= di FastAPI!
# a2wsgi TIDAK mengirim event lifespan.startup,
# sehingga FastAPI hang menunggu startup selamanya.
# Kalau nanti perlu init DB, pakai @app.on_event("startup")
# ============================================
app = FastAPI(
    title="Fun AR Math API",
    description="Backend API untuk aplikasi Fun AR Math",
    version="1.0.0",
    docs_url="/docs" if DEBUG else "/docs",
    redoc_url="/redoc" if DEBUG else None,
)

# --- CORS Middleware ---
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
from app.routes import auth, soal, ujian
app.include_router(soal.router)
app.include_router(auth.router)
app.include_router(ujian.router)


@app.get("/")
def read_root():
    return {"msg": "Server Jalan, Database Aman!"}
    

@app.get("/init-db")
def init_database():
    from app.database import create_db_and_tables
    try:
        create_db_and_tables()
        return {"status": "sukses", "pesan": "Semua tabel berhasil dibuat di Neon DB!"}
    except Exception as e:
        return {"status": "gagal", "pesan": str(e)}

@app.on_event("startup")
def on_startup():
    from app.database import create_db_and_tables
    create_db_and_tables()
    logger.info("Database tables ready.")