"""Insight dan rekomendasi.

Saat ini berisi rekomendasi harian berbasis aturan (dipakai chatbot).
Pemicu stres, Sweet Spot, dan Wrapped ditambahkan di tahap insight.
"""

from datetime import date, datetime, timedelta

from models import DEFAULT_USER_ID
from services import jadwal as layanan_jadwal

MAKS_SARAN = 3
TARGET_AIR = 8  # gelas
TARGET_OLAHRAGA = 30  # menit
DURASI_TIDUR_IDEAL = timedelta(hours=7, minutes=30)
PERSIAPAN_PAGI = timedelta(hours=1)  # bangun 1 jam sebelum kuliah pertama


def format_jam(t):
    return t.strftime("%H.%M")


def kuliah_pertama(tanggal, user_id=DEFAULT_USER_ID):
    """Jam mulai kuliah paling awal pada tanggal itu (semester aktif), atau None."""
    jadwal = layanan_jadwal.jadwal_semester(layanan_jadwal.semester_aktif(user_id), user_id)
    mulai = [j.jam_mulai for j in jadwal if j.hari == tanggal.weekday()]
    return min(mulai) if mulai else None


def saran_jadwal_besok(jam_kuliah_besok):
    """Saran jam tidur jika besok ada kuliah pagi (mulai sebelum 08.00)."""
    if jam_kuliah_besok is None or jam_kuliah_besok >= layanan_jadwal.BATAS_KULIAH_PAGI:
        return None
    bangun = datetime.combine(date.today(), jam_kuliah_besok) - PERSIAPAN_PAGI
    tidur = (bangun - DURASI_TIDUR_IDEAL).time()
    return f"Besok kuliah jam {format_jam(jam_kuliah_besok)}, usahakan tidur sebelum {format_jam(tidur)}."


def buat_rekomendasi(catatan_hari_ini, jam_kuliah_besok=None):
    """Maksimal 3 saran dari catatan hari ini (sesuai tabel aturan di rancangan) dan jadwal besok.

    `catatan_hari_ini` boleh None (belum ada catatan). Kolom yang kosong tidak dinilai.
    """
    saran = []
    besok = saran_jadwal_besok(jam_kuliah_besok)

    if catatan_hari_ini is None:
        saran.append("Belum ada catatan hari ini. Ceritain harimu dulu ya, biar saranku lebih pas.")
        if besok:
            saran.append(besok)
        return saran[:MAKS_SARAN]

    c = catatan_hari_ini
    # Urutan prioritas: stres tinggi, tidur, jadwal besok, air, olahraga
    if c.stres is not None and c.stres >= 7:
        saran.append("Stresmu tinggi. Ambil jeda, tarik napas, atau cerita ke teman.")
    if c.tidur is not None and c.tidur < 7:
        saran.append("Usahakan tidur 7-9 jam malam ini.")
    elif c.tidur is not None and c.tidur > 9:
        saran.append("Tidurmu sudah lebih dari cukup, coba bangun lebih pagi.")
    if besok:
        saran.append(besok)
    air = c.air or 0
    if air < TARGET_AIR:
        saran.append(f"Kurang {TARGET_AIR - air} gelas lagi untuk target hari ini.")
    if (c.olahraga or 0) < TARGET_OLAHRAGA:
        saran.append("Coba jalan kaki 15-30 menit hari ini.")

    if not saran:
        saran.append("Kerja bagus! Pertahankan kebiasaan hari ini.")
    return saran[:MAKS_SARAN]


def rekomendasi_hari_ini(catatan_hari_ini, tanggal=None, user_id=DEFAULT_USER_ID):
    """buat_rekomendasi() lengkap dengan jadwal kuliah besok."""
    tanggal = tanggal or date.today()
    return buat_rekomendasi(catatan_hari_ini, kuliah_pertama(tanggal + timedelta(days=1), user_id))
