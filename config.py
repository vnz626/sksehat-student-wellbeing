"""Konfigurasi aplikasi SKSehat.

Semua kunci rahasia dibaca dari file .env (lihat .env.example),
tidak pernah ditulis langsung di kode.
"""

import os
import secrets

from dotenv import load_dotenv

# Folder root project, dipakai untuk menentukan lokasi file database
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Muat variabel dari .env ke environment (jika file-nya ada)
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    # Kunci session Flask. Jika belum diisi di .env, dibuat acak per proses
    # supaya aplikasi tetap jalan saat development (session hilang saat restart).
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    # Database SQLite di root project: sksehat.db
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "sksehat.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Kunci layanan eksternal (boleh kosong sampai fiturnya dipakai)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    BOT_SECRET = os.getenv("BOT_SECRET", "")
