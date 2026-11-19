"""Seeder data dummy SKSehat.

Membuat:
- jadwal kuliah contoh (Senin-Jumat, 2 hari kuliah pagi),
- 6 deadline yang tersebar (4 sudah lewat, 2 akan datang),
- 60 hari catatan harian (sampai kemarin) dengan cerita dan pemicu.

Stres dibuat mengikuti pola dari dokumen rancangan:
    stres = 9 - 0,7*tidur - 0,02*olahraga + 0,2*jam_kuliah
            + 1*kuliah_pagi + 0,8*beban_deadline + noise
ditambah penalti kuadrat untuk tidur > 8 jam dan olahraga > 40 menit,
supaya Sweet Spot punya titik optimum yang diketahui (lihat OPTIMUM_*).

Jalankan:  python seed.py
PERHATIAN: semua catatan, jadwal, deadline, chat, dan wrapped milik
profil id=1 akan dihapus lalu diisi ulang. Profil tetap dipertahankan.
"""

import random
from datetime import date, datetime, time, timedelta

from app import app
from models import (
    DEFAULT_USER_ID,
    CatatanHarian,
    ChatHistory,
    Deadline,
    JadwalKuliah,
    Profil,
    Wrapped,
    db,
)

random.seed(42)  # supaya hasil seeder selalu sama

JUMLAH_HARI = 60
SEMESTER = "Ganjil 2026/2027"

# --- Parameter pola stres -------------------------------------------------
# Penalti kuadrat di atas batas ini membuat kurva stres melengkung.
BATAS_TIDUR, PENALTI_TIDUR = 8.0, 0.8
BATAS_OLAHRAGA, PENALTI_OLAHRAGA = 40, 0.001
# Titik optimum "asli" (turunan rumus stres = 0), dipakai untuk menguji Sweet Spot:
#   -0,7  + 2*0,8*(t - 8)    = 0  ->  t = 8 + 0,7/1,6
#   -0,02 + 2*0,001*(o - 40) = 0  ->  o = 40 + 0,02/0,002
OPTIMUM_TIDUR = BATAS_TIDUR + 0.7 / (2 * PENALTI_TIDUR)  # ~8,44 jam
OPTIMUM_OLAHRAGA = BATAS_OLAHRAGA + 0.02 / (2 * PENALTI_OLAHRAGA)  # 50 menit

# --- Jadwal kuliah contoh (hari: 0 = Senin) --------------------------------
JADWAL = [
    # Senin: 5 jam
    ("Basis Data", 0, "08:00", "10:30", "Lab 2"),
    ("Statistika", 0, "13:00", "15:30", "R. 301"),
    # Selasa: kuliah pagi
    ("Algoritma dan Struktur Data", 1, "07:00", "09:30", "R. 204"),
    ("Jaringan Komputer", 1, "10:00", "12:30", "Lab 1"),
    # Rabu: hari terpadat, 7 jam
    ("Pemrograman Web", 2, "08:00", "10:30", "Lab 3"),
    ("Kecerdasan Buatan", 2, "10:30", "13:00", "R. 305"),
    ("Bahasa Inggris", 2, "14:00", "16:00", "R. 102"),
    # Kamis: kuliah pagi
    ("Sistem Operasi", 3, "07:00", "09:30", "R. 204"),
    ("Pancasila", 3, "13:00", "14:40", "Aula"),
    # Jumat: ringan
    ("Rekayasa Perangkat Lunak", 4, "09:00", "11:30", "R. 303"),
]

# --- Deadline: (judul, selisih hari dari hari ini, bobot) ------------------
DEADLINE = [
    ("Laporan Praktikum Basis Data", -45, 2),
    ("Kuis Statistika", -31, 1),
    ("UTS Algoritma dan Struktur Data", -17, 3),
    ("Tugas Besar Pemrograman Web", -6, 3),
    ("Presentasi Kecerdasan Buatan", 3, 2),
    ("UAS Basis Data", 9, 3),
]

# --- Cerita contoh per suasana, beserta pemicu yang cocok -----------------
CERITA_BERAT = [
    ("Begadang ngerjain {deadline}, kepala pusing banget.", "tugas"),
    ("Panik belajar buat {deadline}, materinya banyak banget.", "ujian"),
    ("Revisian dari dosen numpuk, rasanya capek dan kesel.", "dosen"),
    ("Rapat organisasi sampai malam, tugas jadi keteteran.", "organisasi"),
    ("Uang bulanan menipis, jadi kepikiran terus.", "keuangan"),
    ("Lagi ada masalah di rumah, susah fokus kuliah.", "keluarga"),
    ("Habis berantem sama pacar, mood berantakan seharian.", "hubungan"),
    ("Badan meriang dan pusing, kuliah jadi nggak masuk.", "kesehatan"),
]
CERITA_SEDANG = [
    ("Kuliah padat seharian, lumayan capek tapi masih oke.", "tugas"),
    ("Ada tugas kelompok yang belum jelas pembagiannya.", "tugas"),
    ("Persiapan {deadline} mulai dicicil sedikit-sedikit.", "ujian"),
    ("Proker organisasi lagi sibuk, harus bagi waktu.", "organisasi"),
    ("Dosen ngasih tugas mendadak, agak keteteran.", "dosen"),
    ("Hari biasa aja, sedikit bosan di kelas.", "lainnya"),
]
CERITA_RINGAN = [
    "Hari ini santai, sempat nonton film bareng teman.",
    "Tugas sudah beres semua, rasanya lega banget.",
    "Pagi jogging, badan jadi seger seharian.",
    "Makan enak sama teman kos, senang banget.",
    "Tidur cukup dan kuliah lancar, hari yang menyenangkan.",
]


def ke_jam(teks):
    jam, menit = map(int, teks.split(":"))
    return time(jam, menit)


def beban_kuliah(hari_ke):
    """Jam kuliah dan kuliah_pagi untuk satu hari dalam seminggu (0 = Senin)."""
    sesi = [j for j in JADWAL if j[1] == hari_ke]
    jam_kuliah = 0.0
    kuliah_pagi = 0
    for _, _, mulai, selesai, _ in sesi:
        m, s = ke_jam(mulai), ke_jam(selesai)
        jam_kuliah += (s.hour * 60 + s.minute - m.hour * 60 - m.minute) / 60
        if m < time(8, 0):
            kuliah_pagi = 1
    return jam_kuliah, kuliah_pagi


def beban_deadline(tanggal, daftar_deadline):
    """Jumlah bobot deadline dibagi jarak harinya (deadline dalam 14 hari ke depan).

    Deadline di hari yang sama dihitung berjarak 1 hari supaya tidak dibagi nol.
    """
    total = 0.0
    for judul, tgl, bobot in daftar_deadline:
        jarak = (tgl - tanggal).days
        if 0 <= jarak <= 14:
            total += bobot / max(jarak, 1)
    return total


def deadline_terdekat(tanggal, daftar_deadline):
    akan_datang = [(tgl, judul) for judul, tgl, _ in daftar_deadline if tgl >= tanggal]
    return min(akan_datang)[1] if akan_datang else "tugas kuliah"


def batasi(nilai, bawah, atas):
    return max(bawah, min(atas, nilai))


def buat_catatan(tanggal, daftar_deadline):
    hari_ke = tanggal.weekday()
    jam_kuliah, kuliah_pagi = beban_kuliah(hari_ke)
    beban = beban_deadline(tanggal, daftar_deadline)
    akhir_pekan = hari_ke >= 5

    # Tidur: berkurang saat kuliah pagi dan deadline dekat, bertambah di akhir pekan
    tidur = random.gauss(7.0, 1.3) - 1.0 * kuliah_pagi - 0.4 * min(beban, 3)
    if akhir_pekan:
        tidur += 1.6  # "balas dendam" tidur, kadang sampai kebanyakan
    tidur = round(batasi(tidur, 3.5, 11.0) * 2) / 2  # kelipatan 0,5 jam

    # Olahraga: lebih sering di akhir pekan, jarang saat deadline dekat
    peluang_olahraga = 0.65 if akhir_pekan else 0.4
    if beban > 1.5:
        peluang_olahraga -= 0.25
    if random.random() < peluang_olahraga:
        olahraga = int(batasi(random.gauss(45, 28), 10, 120) // 5 * 5)
    else:
        olahraga = 0

    air = int(batasi(round(random.gauss(6.5, 2)), 1, 14))

    # Stres sesuai rumus dokumen + penalti kuadrat untuk titik optimum
    stres = (
        9
        - 0.7 * tidur
        - 0.02 * olahraga
        + 0.2 * jam_kuliah
        + 1 * kuliah_pagi
        + 0.8 * beban
        + PENALTI_TIDUR * max(0.0, tidur - BATAS_TIDUR) ** 2
        + PENALTI_OLAHRAGA * max(0, olahraga - BATAS_OLAHRAGA) ** 2
        + random.gauss(0, 0.8)
    )
    stres = int(batasi(round(stres), 1, 10))

    # Cerita dan pemicu dipilih sesuai tingkat stres
    nama_deadline = deadline_terdekat(tanggal, daftar_deadline)
    if stres >= 7:
        pilihan = random.sample(CERITA_BERAT, k=2 if stres >= 9 else 1)
        if beban > 1:  # deadline dekat: pastikan pemicu akademik ikut muncul
            pilihan[0] = random.choice(CERITA_BERAT[:2])
    elif stres >= 4:
        pilihan = [random.choice(CERITA_SEDANG)]
    else:
        pilihan = []

    if pilihan:
        cerita = " ".join(teks.format(deadline=nama_deadline) for teks, _ in pilihan)
        pemicu = ",".join(dict.fromkeys(p for _, p in pilihan))  # tanpa duplikat
    else:
        cerita = random.choice(CERITA_RINGAN)
        pemicu = None

    # Sentimen sementara (-1..1) diperkirakan dari stres;
    # dihitung ulang dengan model sentimen sungguhan di tahap 8.
    sentimen = round(batasi((5.5 - stres) / 4.5 + random.gauss(0, 0.15), -1, 1), 2)

    return CatatanHarian(
        user_id=DEFAULT_USER_ID,
        tanggal=tanggal,
        tidur=tidur,
        air=air,
        olahraga=olahraga,
        stres=stres,
        cerita=cerita,
        sentimen=sentimen,
        pemicu=pemicu,
        updated_at=datetime.combine(tanggal, time(21, 30)),
    )


def kosongkan_data():
    """Hapus data lama milik profil default (profil sendiri tidak dihapus)."""
    for model in (ChatHistory, Wrapped, CatatanHarian, Deadline, JadwalKuliah):
        model.query.filter_by(user_id=DEFAULT_USER_ID).delete()
    db.session.commit()


def seed():
    db.create_all()
    if db.session.get(Profil, DEFAULT_USER_ID) is None:
        db.session.add(Profil(id=DEFAULT_USER_ID))
        db.session.commit()

    kosongkan_data()
    hari_ini = date.today()

    # 1. Jadwal kuliah
    for matkul, hari, mulai, selesai, ruang in JADWAL:
        db.session.add(
            JadwalKuliah(
                user_id=DEFAULT_USER_ID,
                matkul=matkul,
                hari=hari,
                jam_mulai=ke_jam(mulai),
                jam_selesai=ke_jam(selesai),
                ruang=ruang,
                semester=SEMESTER,
            )
        )

    # 2. Deadline (yang sudah lewat ditandai selesai)
    daftar_deadline = []
    for judul, selisih, bobot in DEADLINE:
        tgl = hari_ini + timedelta(days=selisih)
        daftar_deadline.append((judul, tgl, bobot))
        db.session.add(
            Deadline(
                user_id=DEFAULT_USER_ID,
                judul=judul,
                tanggal=tgl,
                bobot=bobot,
                selesai=tgl < hari_ini,
            )
        )

    # 3. Catatan harian 60 hari, berakhir kemarin
    #    (beberapa hari sengaja dikosongkan/tidak lengkap supaya realistis)
    hari_bolong = set(random.sample(range(JUMLAH_HARI), 3))
    hari_tanpa_stres = set(random.sample(range(JUMLAH_HARI), 2)) - hari_bolong
    for i in range(JUMLAH_HARI):
        if i in hari_bolong:
            continue
        tanggal = hari_ini - timedelta(days=JUMLAH_HARI - i)
        catatan = buat_catatan(tanggal, daftar_deadline)
        if i in hari_tanpa_stres:
            catatan.stres = None
        db.session.add(catatan)

    db.session.commit()

    jumlah = CatatanHarian.query.filter_by(user_id=DEFAULT_USER_ID).count()
    print(f"Jadwal kuliah : {len(JADWAL)} sesi ({SEMESTER})")
    print(f"Deadline      : {len(DEADLINE)}")
    print(f"Catatan harian: {jumlah} hari (sampai {hari_ini - timedelta(days=1)})")
    print(f"Sweet Spot asli: tidur {OPTIMUM_TIDUR:.2f} jam, olahraga {OPTIMUM_OLAHRAGA:.0f} menit")


if __name__ == "__main__":
    with app.app_context():
        seed()
