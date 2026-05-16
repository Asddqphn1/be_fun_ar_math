"""
Passenger WSGI Entry Point untuk cPanel.

cPanel menggunakan Phusion Passenger untuk menjalankan Python app.
File ini WAJIB ada di root project dan WAJIB bernama 'passenger_wsgi.py'.

Passenger akan mencari variabel 'application' di file ini.
"""
import os
import sys

# Tambahkan path project ke sys.path agar module bisa diimport
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Jika pakai virtualenv, aktifkan
VENV_PATH = os.path.join(CURRENT_DIR, "venv", "lib", "python3.11", "site-packages")
if os.path.exists(VENV_PATH):
    sys.path.insert(0, VENV_PATH)

# Load environment variables dari .env
from dotenv import load_dotenv
load_dotenv(os.path.join(CURRENT_DIR, ".env"))

# Import FastAPI app
from app.main import app

# Passenger membutuhkan variabel bernama 'application'
# FastAPI sudah ASGI-compatible, jadi bisa langsung diassign
application = app
