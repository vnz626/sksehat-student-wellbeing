"""Model database SKSehat (SQLite lewat Flask-SQLAlchemy).

Versi ini untuk satu pengguna: tabel `profil` hanya berisi satu baris (id = 1).
Tabel lain tetap menyimpan `user_id` yang menunjuk ke `profil.id`,
supaya fitur login/multi-user mudah ditambahkan nanti.
"""

import sqlite3
from datetime import datetime, time

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _aktifkan_foreign_key_sqlite(dbapi_connection, connection_record):
    # SQLite mematikan pengecekan foreign key secara default, jadi diaktifkan di sini
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Id profil satu-satunya di mode pribadi
DEFAULT_USER_ID = 1


class Profil(db.Model):
    __tablename__ = "profil"

    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False, default="Mahasiswa")
    telegram_chat_id = db.Column(db.String(50))  # diisi setelah bot ditautkan
    kode_tautan = db.Column(db.String(6))  # kode sementara untuk /start <kode>
    jam_checkin = db.Column(db.Time, nullable=False, default=time(21, 0))
    jam_prakiraan = db.Column(db.Time, nullable=False, default=time(6, 30))

    def __repr__(self):
        return f"<Profil {self.id} {self.nama}>"


class CatatanHarian(db.Model):
    __tablename__ = "catatan_harian"
    # Satu user hanya punya satu baris per tanggal
    __table_args__ = (
        db.UniqueConstraint("user_id", "tanggal", name="uq_catatan_user_tanggal"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("profil.id"), nullable=False, index=True)
    tanggal = db.Column(db.Date, nullable=False)
    tidur = db.Column(db.Float)  # jam, boleh kosong
    air = db.Column(db.Integer, nullable=False, default=0)  # gelas, akumulatif
    olahraga = db.Column(db.Integer, nullable=False, default=0)  # menit, akumulatif
    stres = db.Column(db.Integer)  # skala 1-10, boleh kosong
    cerita = db.Column(db.Text)  # gabungan cerita hari itu
    sentimen = db.Column(db.Float)  # skor -1 sampai 1
    pemicu = db.Column(db.String(200))  # daftar pemicu, dipisah koma
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self):
        return f"<CatatanHarian {self.tanggal} stres={self.stres}>"


class ChatHistory(db.Model):
    __tablename__ = "chat_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("profil.id"), nullable=False, index=True)
    pesan = db.Column(db.Text, nullable=False)  # kalimat dari user
    balasan = db.Column(db.Text)  # balasan bot
    jenis = db.Column(db.String(20))  # catat, tanya, saran, atau ngobrol
    sumber = db.Column(db.String(10), nullable=False, default="web")  # web atau telegram
    waktu = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def __repr__(self):
        return f"<ChatHistory {self.id} {self.sumber}/{self.jenis}>"


class Deadline(db.Model):
    __tablename__ = "deadline"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("profil.id"), nullable=False, index=True)
    judul = db.Column(db.String(150), nullable=False)  # misalnya "UTS Basis Data"
    tanggal = db.Column(db.Date, nullable=False)
    bobot = db.Column(db.Integer, nullable=False, default=2)  # 1 ringan, 2 sedang, 3 berat
    selesai = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<Deadline {self.judul} {self.tanggal}>"


class JadwalKuliah(db.Model):
    __tablename__ = "jadwal_kuliah"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("profil.id"), nullable=False, index=True)
    matkul = db.Column(db.String(150), nullable=False)
    hari = db.Column(db.Integer, nullable=False)  # 0 = Senin sampai 5 = Sabtu
    jam_mulai = db.Column(db.Time, nullable=False)
    jam_selesai = db.Column(db.Time, nullable=False)
    ruang = db.Column(db.String(50))  # opsional
    semester = db.Column(db.String(20))  # misalnya "Ganjil 2026/2027"

    def __repr__(self):
        return f"<JadwalKuliah {self.matkul} hari={self.hari}>"


class Wrapped(db.Model):
    __tablename__ = "wrapped"
    # Satu rekap per minggu, supaya Wrapped minggu lalu tidak berubah
    __table_args__ = (
        db.UniqueConstraint("user_id", "minggu_mulai", name="uq_wrapped_user_minggu"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("profil.id"), nullable=False, index=True)
    minggu_mulai = db.Column(db.Date, nullable=False)  # Senin awal minggu
    statistik = db.Column(db.Text)  # JSON statistik minggu itu
    narasi = db.Column(db.Text)  # teks hasil LLM

    def __repr__(self):
        return f"<Wrapped {self.minggu_mulai}>"
