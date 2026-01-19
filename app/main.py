from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import create_db_and_tables
from app.routes import auth, soal, ujian # Import fungsi bikin tabel

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Mencoba koneksi ke Database...")
    try:
        create_db_and_tables() # <--- INI MOMEN KONEKSINYA!
        print("BERHASIL! Tabel sudah dibuat (jika belum ada).")
    except Exception as e:
        print(f"GAGAL KONEK: {e}")
    
    yield

    print("Server mati, koneksi diputus.")

app = FastAPI(lifespan=lifespan)

app.include_router(soal.router)
app.include_router(auth.router)
app.include_router(ujian.router)

@app.get("/")
def read_root():
    return {"msg": "Server Jalan, Database Aman!"}