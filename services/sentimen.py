"""Skor sentimen cerita harian berbahasa Indonesia (berbasis leksikon).

Cara kerja (mirip leksikon InSet: setiap kata punya bobot -5 sampai +5):
1. Teks dinormalisasi: huruf kecil, huruf berulang dirapikan ("capeeek" -> "capek"),
   kata gaul diseragamkan ("bgt" -> "banget", "seneng" -> "senang").
2. Frasa dua kata dicek dulu ("kurang tidur"), lalu kata tunggal.
3. Negasi ("gak", "tidak", ...) dalam 2 kata sebelumnya membalik bobot.
   Penguat ("banget", "sangat", ...) di sebelahnya memperbesar bobot 1,5x.
4. Total bobot dinormalisasi ke rentang -1..1 dengan total / sqrt(total^2 + 15).

Leksikon dibuat sendiri untuk cerita mahasiswa sehari-hari dan bisa ditambah kapan saja.
"""

import math
import re

# ---------------------------------------------------------------------------
# Leksikon
# ---------------------------------------------------------------------------

KATA_POSITIF = {
    # perasaan
    "senang": 3, "bahagia": 4, "gembira": 3, "happy": 3, "excited": 3, "lega": 3, "puas": 3,
    "tenang": 3, "damai": 3, "nyaman": 2, "rileks": 2, "santai": 2, "bangga": 3, "syukur": 3,
    "bersyukur": 3, "alhamdulillah": 2, "semangat": 3, "termotivasi": 3, "percaya": 1,
    "optimis": 3, "sayang": 2, "cinta": 3, "ketawa": 2, "tertawa": 2, "lucu": 2, "menyenangkan": 3,
    # keadaan
    "seru": 3, "asik": 2, "asyik": 2, "mantap": 3, "keren": 3, "bagus": 3, "baik": 2, "enak": 2,
    "nikmat": 2, "segar": 2, "fresh": 2, "sehat": 2, "bugar": 2, "fit": 2, "lancar": 3,
    "produktif": 3, "fokus": 2, "beres": 2, "kelar": 2, "selesai": 1, "berhasil": 3, "sukses": 3,
    "lulus": 3, "menang": 3, "aman": 2, "oke": 1, "ok": 1, "cukup": 1, "membantu": 2, "istirahat": 1,
    "libur": 2, "liburan": 2, "jalan-jalan": 2, "nonton": 1, "makan-makan": 2,
}

KATA_NEGATIF = {
    # perasaan
    "sedih": -3, "kecewa": -3, "kesal": -3, "marah": -3, "emosi": -2, "bete": -2, "galau": -2,
    "cemas": -3, "khawatir": -2, "takut": -2, "panik": -3, "gelisah": -3, "stres": -3,
    "depresi": -4, "frustasi": -3, "frustrasi": -3, "putus asa": -4, "nyesel": -2, "menyesal": -2,
    "malu": -2, "insecure": -2, "kesepian": -3, "sendirian": -1, "overthinking": -3,
    "burnout": -4, "hampa": -3, "bosan": -1, "malas": -1, "jenuh": -2, "kesel": -3, "sebel": -2,
    "nangis": -3, "menangis": -3, "down": -3, "hancur": -4, "benci": -3,
    # fisik
    "capek": -3, "lelah": -3, "letih": -3, "ngantuk": -1, "pusing": -3, "mumet": -3, "sakit": -3,
    "meriang": -2, "demam": -2, "flu": -2, "mual": -2, "lemas": -2, "drop": -2, "tepar": -3,
    "begadang": -2, "insomnia": -3,
    # keadaan / beban
    "numpuk": -2, "menumpuk": -2, "keteteran": -2, "kewalahan": -3, "berantakan": -2,
    "kacau": -3, "ribet": -2, "ruwet": -2, "susah": -2, "sulit": -2, "berat": -2, "parah": -2,
    "buruk": -3, "jelek": -2, "gagal": -3, "telat": -2, "terlambat": -2, "mepet": -2,
    "mendadak": -1, "revisi": -1, "remidi": -2, "remedial": -2, "berantem": -3, "bertengkar": -3,
    "ribut": -2, "masalah": -2, "tekanan": -2, "tertekan": -3, "dimarahin": -3, "dimarahi": -3,
    "ditolak": -2, "boros": -1, "bokek": -2, "kehilangan": -2, "kangen": -1,
}

# Frasa dua kata dicek lebih dulu daripada kata tunggal
FRASA = {
    "kurang tidur": -2, "susah tidur": -2, "gak tidur": -2, "belum tidur": -1,
    "tidur cukup": 2, "cukup tidur": 2, "tidur nyenyak": 3, "putus asa": -4,
    "tidak semangat": -3, "gak semangat": -3, "hari berat": -2, "nggak fokus": -2,
}

LEKSIKON = {**KATA_POSITIF, **KATA_NEGATIF}

NEGASI = {"tidak", "tak", "gak", "nggak", "enggak", "kagak", "bukan", "belum", "jangan", "kurang", "tanpa"}
PENGUAT_SESUDAH = {"banget", "sekali", "parah", "pol", "abis", "beneran"}  # "capek banget"
PENGUAT_SEBELUM = {"sangat", "amat", "terlalu", "super", "paling", "makin"}  # "sangat capek"
FAKTOR_PENGUAT = 1.5
FAKTOR_NEGASI = -0.8
ALPHA = 15  # makin besar, skor makin lambat mendekati -1 atau 1

# Normalisasi kata gaul / salah ketik umum
NORMALISASI = {
    "bgt": "banget", "bngt": "banget", "bet": "banget", "ga": "gak", "gk": "gak", "g": "gak",
    "ngga": "nggak", "engga": "enggak", "tdk": "tidak", "gausah": "gak usah",
    "seneng": "senang", "cape": "capek", "capai": "capek", "pusying": "pusing", "sedi": "sedih",
    "kzl": "kesal", "bt": "bete", "stress": "stres", "stresss": "stres", "males": "malas",
    "bosen": "bosan", "mantep": "mantap", "mantul": "mantap", "asek": "asik", "uda": "sudah",
    "udah": "sudah", "dah": "sudah", "sy": "saya", "aq": "aku", "ak": "aku",
}


# ---------------------------------------------------------------------------
# Perhitungan
# ---------------------------------------------------------------------------

def tokenisasi(teks):
    """Memecah teks menjadi kata yang sudah dinormalisasi."""
    teks = (teks or "").lower()
    teks = re.sub(r"(\w+)2\b", r"\1", teks)  # "senang2" -> "senang"
    teks = re.sub(r"([a-z])\1{2,}", r"\1", teks)  # "capeeek" -> "capek", "bangettt" -> "banget"
    kata = re.findall(r"[a-z]+(?:-[a-z]+)?", teks)
    hasil = []
    for k in kata:
        k = NORMALISASI.get(k, k)
        hasil.extend(k.split())  # "gak usah" jadi dua kata
    return hasil


def _bobot_token(kata):
    """Daftar (posisi, bobot) untuk kata/frasa yang ada di leksikon."""
    hasil = []
    i = 0
    while i < len(kata):
        if i + 1 < len(kata) and f"{kata[i]} {kata[i + 1]}" in FRASA:
            hasil.append((i, FRASA[f"{kata[i]} {kata[i + 1]}"], 2))
            i += 2
            continue
        if kata[i] in LEKSIKON:
            hasil.append((i, LEKSIKON[kata[i]], 1))
        i += 1
    return hasil


def skor_sentimen(teks):
    """Skor sentimen -1 (sangat negatif) sampai 1 (sangat positif); None jika teks kosong."""
    kata = tokenisasi(teks)
    if not kata:
        return None

    total = 0.0
    for posisi, bobot, panjang in _bobot_token(kata):
        nilai = float(bobot)
        akhir = posisi + panjang

        # Negasi dalam 2 kata sebelumnya (frasa yang sudah mengandung negasi tidak dibalik lagi)
        sebelum = kata[max(0, posisi - 2) : posisi]
        if panjang == 1 and any(k in NEGASI for k in sebelum):
            nilai *= FAKTOR_NEGASI

        # Penguat tepat sebelum atau sesudah kata
        if (posisi > 0 and kata[posisi - 1] in PENGUAT_SEBELUM) or (
            akhir < len(kata) and kata[akhir] in PENGUAT_SESUDAH and kata[akhir] not in LEKSIKON
        ):
            nilai *= FAKTOR_PENGUAT

        total += nilai

    if total == 0:
        return 0.0
    return round(total / math.sqrt(total * total + ALPHA), 3)


def label_sentimen(skor):
    """Label teks untuk skor: positif, netral, atau negatif."""
    if skor is None:
        return None
    if skor > 0.05:
        return "positif"
    if skor < -0.05:
        return "negatif"
    return "netral"
