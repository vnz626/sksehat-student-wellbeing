"""Layanan jadwal kuliah: parsing file jadwal, penyimpanan, dan beban kuliah per tanggal.

Sumber jadwal yang didukung di sini:
- CSV / Excel dengan kolom: matkul, hari, jam_mulai, jam_selesai, ruang
- file .ics (misalnya ekspor Google Calendar)
Parsing teks KRS lewat LLM ada di tahap 7.

Setiap parser mengembalikan (daftar_sesi, daftar_error). Satu sesi berupa dict:
    {"matkul": str, "hari": 0-5, "jam_mulai": time, "jam_selesai": time, "ruang": str|None}
"""

import io
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from models import DEFAULT_USER_ID, JadwalKuliah, db

NAMA_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

# Nama hari yang dikenali (Indonesia + Inggris, beberapa singkatan)
_HARI_KE_ANGKA = {
    "senin": 0, "sen": 0, "monday": 0, "mon": 0,
    "selasa": 1, "sel": 1, "tuesday": 1, "tue": 1,
    "rabu": 2, "rab": 2, "wednesday": 2, "wed": 2,
    "kamis": 3, "kam": 3, "thursday": 3, "thu": 3,
    "jumat": 4, "jum'at": 4, "jum": 4, "friday": 4, "fri": 4,
    "sabtu": 5, "sab": 5, "saturday": 5, "sat": 5,
}

BATAS_KULIAH_PAGI = time(8, 0)  # kuliah yang mulai sebelum jam ini dianggap kuliah pagi
KOLOM_WAJIB = ["matkul", "hari", "jam_mulai", "jam_selesai"]


# ---------------------------------------------------------------------------
# Normalisasi nilai
# ---------------------------------------------------------------------------

def baca_hari(nilai):
    """Mengubah 'Senin' / 'senin' / 0 menjadi angka 0-5. Error jika tidak dikenali."""
    if isinstance(nilai, (int, float)) and not isinstance(nilai, bool):
        if float(nilai).is_integer() and 0 <= int(nilai) <= 5:
            return int(nilai)
        if nilai == 6:
            raise ValueError("hari Minggu tidak didukung (hanya Senin-Sabtu)")
        raise ValueError(f"hari '{nilai}' harus 0 (Senin) sampai 5 (Sabtu)")
    teks = str(nilai).strip().lower()
    if teks.isdigit():
        return baca_hari(int(teks))
    if teks in ("minggu", "sunday", "sun", "min"):
        raise ValueError("hari Minggu tidak didukung (hanya Senin-Sabtu)")
    if teks not in _HARI_KE_ANGKA:
        raise ValueError(f"hari '{nilai}' tidak dikenali")
    return _HARI_KE_ANGKA[teks]


def baca_jam(nilai):
    """Mengubah '07:00', '07.00', '7:00', atau objek time/datetime menjadi time."""
    if isinstance(nilai, datetime):
        return nilai.time().replace(second=0, microsecond=0)
    if isinstance(nilai, time):
        return nilai.replace(second=0, microsecond=0)
    teks = str(nilai).strip()
    cocok = re.fullmatch(r"(\d{1,2})[:.](\d{2})(?:[:.]\d{2})?", teks)
    if not cocok:
        raise ValueError(f"jam '{nilai}' tidak valid, gunakan format 07:00")
    jam, menit = int(cocok.group(1)), int(cocok.group(2))
    if jam > 23 or menit > 59:
        raise ValueError(f"jam '{nilai}' tidak valid")
    return time(jam, menit)


def validasi_sesi(sesi):
    """Memastikan satu sesi lengkap dan masuk akal. Mengembalikan sesi yang sudah dirapikan."""
    for kolom in KOLOM_WAJIB:
        nilai = sesi.get(kolom)
        if nilai is None or (not isinstance(nilai, (time, datetime)) and pd.isna(nilai)) or str(nilai).strip() == "":
            raise ValueError(f"kolom {kolom} kosong")

    matkul = str(sesi.get("matkul")).strip()
    if not matkul:
        raise ValueError("nama mata kuliah kosong")
    if len(matkul) > 150:
        raise ValueError("nama mata kuliah maksimal 150 karakter")

    hari = baca_hari(sesi.get("hari"))
    jam_mulai = baca_jam(sesi.get("jam_mulai"))
    jam_selesai = baca_jam(sesi.get("jam_selesai"))
    if jam_mulai >= jam_selesai:
        raise ValueError("jam mulai harus sebelum jam selesai")

    ruang = sesi.get("ruang")
    ruang = None if ruang is None or pd.isna(ruang) else str(ruang).strip() or None
    if ruang and len(ruang) > 50:
        raise ValueError("ruang maksimal 50 karakter")

    return {"matkul": matkul, "hari": hari, "jam_mulai": jam_mulai,
            "jam_selesai": jam_selesai, "ruang": ruang}


# ---------------------------------------------------------------------------
# Parser file
# ---------------------------------------------------------------------------

def parse_tabel(isi_file, nama_file):
    """Membaca jadwal dari CSV atau Excel (.xlsx/.xls) dengan pandas."""
    nama = nama_file.lower()
    try:
        if nama.endswith(".csv"):
            # sep=None: pandas menebak pemisah (koma atau titik koma)
            df = pd.read_csv(io.BytesIO(isi_file), sep=None, engine="python", dtype=str)
        elif nama.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(isi_file))
        else:
            return [], ["Format file harus .csv, .xlsx, atau .ics."]
    except Exception as e:  # file rusak / bukan tabel
        return [], [f"File tidak bisa dibaca: {e}"]

    # Nama kolom dibuat seragam: huruf kecil, spasi jadi garis bawah
    df.columns = [str(k).strip().lower().replace(" ", "_") for k in df.columns]
    kurang = [k for k in KOLOM_WAJIB if k not in df.columns]
    if kurang:
        return [], ["Kolom wajib tidak ada: " + ", ".join(kurang)]

    sesi, errors = [], []
    for i, baris in df.iterrows():
        if all(pd.isna(baris.get(k)) for k in KOLOM_WAJIB):
            continue  # lewati baris kosong
        try:
            sesi.append(validasi_sesi({k: baris.get(k) for k in KOLOM_WAJIB + ["ruang"]}))
        except ValueError as e:
            errors.append(f"Baris {i + 2}: {e}")  # +2: header + index mulai 0
    return sesi, errors


def _zona_kalender(kalender):
    """Zona waktu kalender (X-WR-TIMEZONE), atau zona waktu komputer jika tidak ada."""
    nama = kalender.get("X-WR-TIMEZONE")
    if nama:
        try:
            return ZoneInfo(str(nama))
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone().tzinfo


def parse_ics(isi_file):
    """Membaca jadwal dari file .ics. Setiap event menjadi satu sesi mingguan."""
    from icalendar import Calendar

    try:
        kalender = Calendar.from_ical(isi_file)
    except Exception as e:
        return [], [f"File .ics tidak bisa dibaca: {e}"]

    zona = _zona_kalender(kalender)
    sesi, errors = [], []
    for event in kalender.walk("VEVENT"):
        judul = str(event.get("SUMMARY") or "").strip()
        mulai = event.decoded("DTSTART", None)
        selesai = event.decoded("DTEND", None)
        if not isinstance(mulai, datetime):
            continue  # event seharian (tanpa jam) bukan jadwal kuliah
        if not isinstance(selesai, datetime):
            durasi = event.decoded("DURATION", None)
            selesai = mulai + durasi if durasi else None
        if selesai is None:
            errors.append(f"Event '{judul}': tidak punya jam selesai")
            continue

        # Waktu UTC diubah ke zona kalender; waktu dengan TZID dipakai apa adanya
        if mulai.tzinfo is not None and mulai.utcoffset() == timedelta(0):
            mulai, selesai = mulai.astimezone(zona), selesai.astimezone(zona)

        try:
            sesi.append(validasi_sesi({
                "matkul": judul,
                "hari": mulai.weekday(),
                "jam_mulai": mulai.time(),
                "jam_selesai": selesai.time(),
                "ruang": str(event.get("LOCATION")) if event.get("LOCATION") else None,
            }))
        except ValueError as e:
            errors.append(f"Event '{judul or '(tanpa judul)'}': {e}")
    return sesi, errors


def parse_file(isi_file, nama_file):
    """Memilih parser sesuai ekstensi file."""
    if nama_file.lower().endswith(".ics"):
        return parse_ics(isi_file)
    return parse_tabel(isi_file, nama_file)


# ---------------------------------------------------------------------------
# Penyimpanan
# ---------------------------------------------------------------------------

def _kunci(matkul, hari, jam_mulai, jam_selesai):
    return (matkul.strip().lower(), hari, jam_mulai, jam_selesai)


def simpan_jadwal(daftar_sesi, semester=None, user_id=DEFAULT_USER_ID):
    """Menyimpan sesi ke database, melewati yang sudah ada di semester yang sama.

    Mengembalikan (jumlah_ditambah, jumlah_duplikat).
    """
    sudah_ada = {
        _kunci(j.matkul, j.hari, j.jam_mulai, j.jam_selesai)
        for j in JadwalKuliah.query.filter_by(user_id=user_id, semester=semester)
    }
    ditambah = duplikat = 0
    for s in daftar_sesi:
        kunci = _kunci(s["matkul"], s["hari"], s["jam_mulai"], s["jam_selesai"])
        if kunci in sudah_ada:
            duplikat += 1
            continue
        sudah_ada.add(kunci)  # juga mencegah duplikat di dalam file yang sama
        db.session.add(JadwalKuliah(user_id=user_id, semester=semester, **s))
        ditambah += 1
    db.session.commit()
    return ditambah, duplikat


def semester_aktif(user_id=DEFAULT_USER_ID):
    """Semester dari jadwal yang terakhir ditambahkan (None jika belum ada jadwal)."""
    terakhir = (
        JadwalKuliah.query.filter_by(user_id=user_id)
        .order_by(JadwalKuliah.id.desc())
        .first()
    )
    return terakhir.semester if terakhir else None


def daftar_semester(user_id=DEFAULT_USER_ID):
    hasil = (
        db.session.query(JadwalKuliah.semester)
        .filter_by(user_id=user_id)
        .distinct()
        .all()
    )
    return [s for (s,) in hasil]


def jadwal_semester(semester, user_id=DEFAULT_USER_ID):
    return (
        JadwalKuliah.query.filter_by(user_id=user_id, semester=semester)
        .order_by(JadwalKuliah.hari, JadwalKuliah.jam_mulai)
        .all()
    )


# ---------------------------------------------------------------------------
# Beban kuliah per tanggal
# ---------------------------------------------------------------------------

def _menit(t):
    return t.hour * 60 + t.minute


def hitung_beban_dari_sesi(sesi_hari_itu):
    """Menghitung fitur beban kuliah dari daftar sesi di satu hari.

    - jam_kuliah     : total jam kuliah (jam yang bertumpuk hanya dihitung sekali)
    - jumlah_matkul  : jumlah mata kuliah berbeda
    - kuliah_pagi    : 1 jika ada kuliah yang mulai sebelum 08.00
    - jeda_terpanjang: jeda terpanjang (jam) di antara dua sesi berurutan
    """
    if not sesi_hari_itu:
        return {"jam_kuliah": 0.0, "jumlah_matkul": 0, "kuliah_pagi": 0, "jeda_terpanjang": 0.0}

    rentang = sorted((_menit(s.jam_mulai), _menit(s.jam_selesai)) for s in sesi_hari_itu)

    # Gabungkan sesi yang bertumpuk supaya jam kuliah tidak terhitung dua kali
    gabungan = [list(rentang[0])]
    for mulai, selesai in rentang[1:]:
        if mulai <= gabungan[-1][1]:
            gabungan[-1][1] = max(gabungan[-1][1], selesai)
        else:
            gabungan.append([mulai, selesai])

    total_menit = sum(s - m for m, s in gabungan)
    jeda = [gabungan[i + 1][0] - gabungan[i][1] for i in range(len(gabungan) - 1)]

    return {
        "jam_kuliah": round(total_menit / 60, 2),
        "jumlah_matkul": len({s.matkul.strip().lower() for s in sesi_hari_itu}),
        "kuliah_pagi": int(any(s.jam_mulai < BATAS_KULIAH_PAGI for s in sesi_hari_itu)),
        "jeda_terpanjang": round(max(jeda, default=0) / 60, 2),
    }


def hitung_beban_kuliah(tanggal, user_id=DEFAULT_USER_ID, jadwal=None):
    """Fitur beban kuliah untuk satu tanggal, berdasarkan jadwal semester aktif.

    `jadwal` boleh diberikan (daftar JadwalKuliah) supaya tidak query berulang.
    """
    if jadwal is None:
        jadwal = jadwal_semester(semester_aktif(user_id), user_id)
    sesi = [j for j in jadwal if j.hari == tanggal.weekday()]
    return hitung_beban_dari_sesi(sesi)


def beban_kuliah_rentang(mulai, jumlah_hari, user_id=DEFAULT_USER_ID):
    """Beban kuliah untuk beberapa hari berturut-turut, mulai dari tanggal `mulai`."""
    jadwal = jadwal_semester(semester_aktif(user_id), user_id)
    hasil = []
    for i in range(jumlah_hari):
        tgl = mulai + timedelta(days=i)
        hasil.append({"tanggal": tgl, **hitung_beban_kuliah(tgl, user_id, jadwal)})
    return hasil
