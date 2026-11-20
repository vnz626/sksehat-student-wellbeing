"""Alur chatbot SKSehat (dipakai web dan bot Telegram).

Setiap pesan:
1. Dibaca LLM menjadi JSON (jenis, tidur, air, olahraga, stres, pemicu, topik).
   Jika LLM gagal, dipakai cadangan regex supaya pencatatan tetap jalan.
2. JSON divalidasi: angka harus dalam rentang wajar, pemicu harus kategori yang diizinkan.
3. "catat" -> disimpan ke catatan hari ini + skor sentimen cerita; balasan dari template.
   "tanya"/"saran" -> backend menghitung jawabannya, LLM hanya menyusun kalimat.
   "ngobrol" -> balasan singkat dari LLM.
4. Pesan, balasan, dan jenis disimpan ke chat_history.
"""

import json
import logging
import re
from datetime import date, datetime, timedelta

from models import DEFAULT_USER_ID, CatatanHarian, ChatHistory, db
from services import insight, llm, prediksi
from services.sentimen import label_sentimen, skor_sentimen

log = logging.getLogger(__name__)

JENIS_VALID = {"catat", "tanya", "saran", "ngobrol"}
TOPIK_VALID = {"ringkasan", "hari_ini", "prediksi", "prakiraan", "lanjutan", "lainnya"}
TANYA_STRES = "Stresnya hari ini di angka berapa (1-10)?"
POLA_ANGKA_SAJA = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")  # pesan berisi angka saja, misalnya "8"
BATAS_PESAN = 1000  # karakter

# Rentang wajar (sama dengan validasi form Riwayat)
RENTANG = {
    "tidur": (0, 24, "jam"),
    "air": (0, 30, "gelas"),
    "olahraga": (0, 600, "menit"),
    "stres": (1, 10, ""),
}

POLA_KRISIS = re.compile(
    r"bunuh diri|ingin mati|pengen mati|pingin mati|mau mati aja|akhiri hidup|mengakhiri hidup|"
    r"self.?harm|menyakiti diri|nyakitin diri|melukai diri",
    re.IGNORECASE,
)
POLA_PRAKIRAAN = re.compile(r"minggu depan|besok|lusa|ke depan|prakiraan|hari apa", re.IGNORECASE)

BALASAN_KRISIS = (
    "Makasih udah mau cerita, itu berat dan kamu nggak harus menghadapinya sendirian. "
    "Tolong hubungi orang yang kamu percaya, layanan konseling kampus, atau layanan kesehatan jiwa "
    "Kemenkes di 119 ext 8 sekarang ya. Kalau kamu dalam bahaya, hubungi 112 atau IGD terdekat."
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def angka(x):
    """Format angka gaya Indonesia: 6.0 -> '6', 6.25 -> '6,3'."""
    if x is None:
        return "-"
    x = round(float(x), 1)
    return str(int(x)) if x.is_integer() else str(x).replace(".", ",")


def _ke_angka(nilai):
    if nilai is None or isinstance(nilai, bool):
        return None
    if isinstance(nilai, (int, float)):
        return float(nilai)
    teks = str(nilai).strip().replace(",", ".")
    try:
        return float(teks)
    except ValueError:
        return None


def catatan_hari_ini(user_id=DEFAULT_USER_ID, tanggal=None):
    return CatatanHarian.query.filter_by(user_id=user_id, tanggal=tanggal or date.today()).first()


KONTEKS_MAKS = timedelta(minutes=30)  # chat yang lebih lama dianggap percakapan lain


def chat_terakhir(user_id=DEFAULT_USER_ID):
    """Pesan dan balasan terakhir sebagai konteks percakapan, atau None jika tidak ada/sudah basi."""
    terakhir = (
        ChatHistory.query.filter_by(user_id=user_id)
        .order_by(ChatHistory.waktu.desc(), ChatHistory.id.desc())
        .first()
    )
    if terakhir is None or datetime.now() - terakhir.waktu > KONTEKS_MAKS:
        return None
    return terakhir


# ---------------------------------------------------------------------------
# 1. Ekstraksi (LLM + cadangan regex)
# ---------------------------------------------------------------------------

def ekstrak_llm(pesan, balasan_sebelumnya=None):
    """Ekstraksi lewat LLM; pesan bot sebelumnya ikut dikirim supaya jawaban singkat ("8") dipahami."""
    isi = f"Pesan: {pesan}"
    if balasan_sebelumnya:
        isi = f"Bot sebelumnya: {balasan_sebelumnya}\n" + isi
    data, _ = llm.chat_json(
        [{"role": "system", "content": llm.PROMPT_EKSTRAKSI}, {"role": "user", "content": isi}],
        temperature=0,
        max_tokens=400,
        timeout=8,
        reasoning_effort="low",
        max_retries=0,  # gagal cepat -> cadangan regex, supaya balasan tetap < 3 detik
    )
    return data


_KATA_OLAHRAGA = r"(?:olahraga|olah raga|jogging|joging|lari|gym|renang|sepeda|jalan kaki|senam|futsal|basket|badminton|bulutangkis|yoga|workout|push ?up)"
_PEMICU_REGEX = {
    "tugas": r"tugas|laporan|makalah|praktikum|deadline|skripsi|proyek|project",
    "ujian": r"ujian|\buts\b|\buas\b|kuis|quiz",
    "dosen": r"dosen|asdos|asisten dosen",
    "organisasi": r"organisasi|rapat|himpunan|\bukm\b|kepanitiaan|panitia|\bbem\b|proker",
    "keuangan": r"uang|duit|bayar|\bkos\b|ukt|bokek|tagihan",
    "keluarga": r"keluarga|orang ?tua|ortu|\bayah\b|\bibu\b|mama|papa|adik|kakak",
    "hubungan": r"pacar|gebetan|\bteman\b|temen|sahabat|putus",
    "kesehatan": r"sakit|demam|meriang|flu|pusing|maag|batuk|enak badan",
}


def ekstrak_regex(pesan):
    """Cadangan tanpa LLM: pola sederhana seperti 'tidur 7 jam', 'stres 6', 'minum 5 gelas'."""
    t = pesan.lower()
    hasil = {"jenis": None, "tidur": None, "air": None, "olahraga": None, "stres": None,
             "pemicu": [], "topik": None, "balasan": None}

    # "tidur jam 1 ... bangun jam 6" -> lama tidur dihitung dari selisih jam
    m = re.search(r"tidur\s+(?:jam|pukul)\s*(\d{1,2})(?:[.:](\d{2}))?(\s*malam)?.{0,40}?"
                  r"bangun\s+(?:jam|pukul)\s*(\d{1,2})(?:[.:](\d{2}))?", t)
    if m:
        jam_tidur = int(m.group(1)) + int(m.group(2) or 0) / 60
        if m.group(3) and 6 <= jam_tidur < 12:
            jam_tidur += 12  # "jam 10 malam" = 22.00
        jam_bangun = int(m.group(4)) + int(m.group(5) or 0) / 60
        hasil["tidur"] = round((jam_bangun - jam_tidur) % 24, 1)
    else:
        m = re.search(r"tidur\D{0,15}?(\d+(?:[.,]\d+)?)\s*jam", t) or re.search(r"(\d+(?:[.,]\d+)?)\s*jam\s*tidur", t)
        if m:
            hasil["tidur"] = m.group(1)
    m = re.search(r"(\d+)\s*gelas", t)
    if m:
        hasil["air"] = m.group(1)
    else:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*liter", t)
        if m:
            hasil["air"] = round(float(m.group(1).replace(",", ".")) * 4)
    if re.search(_KATA_OLAHRAGA, t):
        m = re.search(r"(\d+)\s*menit", t)
        if m:
            hasil["olahraga"] = m.group(1)
        else:
            m = re.search(_KATA_OLAHRAGA + r"\D{0,15}?(\d+(?:[.,]\d+)?)\s*jam", t)
            if m:
                hasil["olahraga"] = round(float(m.group(1).replace(",", ".")) * 60)
    m = re.search(r"stres\w*\D{0,12}?(\d+(?:[.,]\d+)?)", t)
    if m:
        hasil["stres"] = m.group(1)
    hasil["pemicu"] = [k for k, pola in _PEMICU_REGEX.items() if re.search(pola, t)]

    ada_angka = any(hasil[k] is not None for k in RENTANG)
    if re.search(r"saran|tips|rekomendasi|harus ngapain|enaknya ngapain", t):
        hasil["jenis"] = "saran"
    elif "?" in t or re.search(r"\b(gimana|bagaimana|berapa|kapan|apa kabar(?:ku)?|rata-rata|rata2)\b", t):
        hasil["jenis"] = "tanya"
        if re.search(r"\b(kalau|kalo|seandainya|andai)\b", t):
            hasil["topik"] = "prediksi"
        elif POLA_PRAKIRAAN.search(t):
            hasil["topik"] = "prakiraan"
        elif "hari ini" in t:
            hasil["topik"] = "hari_ini"
        elif re.search(r"minggu ini|seminggu|rata|akhir-akhir ini|belakangan", t):
            hasil["topik"] = "ringkasan"
        else:
            hasil["topik"] = "lainnya"
    elif ada_angka or hasil["pemicu"] or len(t.split()) >= 4:
        hasil["jenis"] = "catat"
    else:
        hasil["jenis"] = "ngobrol"
        if re.search(r"makasih|terima ?kasih|thanks|thx|suwun", t):
            hasil["balasan"] = "Sama-sama! Semangat terus, ya."
        else:
            hasil["balasan"] = "Hai! Ceritain aja harimu, misalnya \"tidur 7 jam, stres 5\"."
    return hasil


# ---------------------------------------------------------------------------
# 2. Validasi
# ---------------------------------------------------------------------------

def validasi_ekstraksi(hasil):
    """Merapikan JSON hasil ekstraksi. Mengembalikan (data_bersih, daftar_error).

    Angka di luar rentang tidak dipakai dan dilaporkan supaya bot bisa meminta ulang.
    """
    jenis = str(hasil.get("jenis") or "").strip().lower()
    data = {
        "jenis": jenis if jenis in JENIS_VALID else "ngobrol",
        "topik": None,
        "balasan": hasil.get("balasan") if isinstance(hasil.get("balasan"), str) else None,
    }
    topik = str(hasil.get("topik") or "").strip().lower()
    if data["jenis"] == "tanya":
        data["topik"] = topik if topik in TOPIK_VALID else "lainnya"
        # Pengaman: "prediksi" tanpa angka pengandaian tapi menyebut waktu ke depan = prakiraan
        if data["topik"] == "prediksi" and all(_ke_angka(hasil.get(k)) is None for k in ("tidur", "air", "olahraga")) \
                and POLA_PRAKIRAAN.search(str(hasil.get("_pesan", ""))):
            data["topik"] = "prakiraan"

    errors = []
    for kolom, (bawah, atas, satuan) in RENTANG.items():
        nilai = _ke_angka(hasil.get(kolom))
        if nilai is not None and not bawah <= nilai <= atas:
            if kolom == "stres":
                errors.append("Stres pakai skala 1-10 ya, coba kirim lagi angkanya.")
            else:
                errors.append(f"{kolom.capitalize()} {angka(nilai)} {satuan} kayaknya nggak mungkin, cek lagi ya.")
            nilai = None
        if nilai is not None and kolom in ("air", "olahraga", "stres"):
            nilai = int(round(nilai))  # kolom bilangan bulat; stres 6,5 dibulatkan
        data[kolom] = nilai

    pemicu = hasil.get("pemicu") or []
    if isinstance(pemicu, str):
        pemicu = [p.strip() for p in pemicu.split(",")]
    data["pemicu"] = list(dict.fromkeys(
        p.strip().lower() for p in pemicu if isinstance(p, str) and p.strip().lower() in llm.KATEGORI_PEMICU
    ))
    return data, errors


# ---------------------------------------------------------------------------
# 3a. Simpan catatan
# ---------------------------------------------------------------------------

def simpan_catatan(data, pesan, user_id=DEFAULT_USER_ID, tanggal=None):
    """Menyimpan hasil ekstraksi ke catatan hari ini (satu baris per tanggal).

    Tidur dan stres menimpa nilai lama, air dan olahraga dijumlahkan, cerita digabung,
    pemicu digabung tanpa duplikat, lalu sentimen dihitung ulang dari seluruh cerita.
    Mengembalikan (catatan, perubahan, errors).
    """
    tanggal = tanggal or date.today()
    catatan = catatan_hari_ini(user_id, tanggal)
    if catatan is None:
        catatan = CatatanHarian(user_id=user_id, tanggal=tanggal, air=0, olahraga=0)
        db.session.add(catatan)

    perubahan, errors = {}, []
    if data.get("tidur") is not None:
        catatan.tidur = round(data["tidur"], 1)
        perubahan["tidur"] = catatan.tidur
    if data.get("stres") is not None:
        catatan.stres = data["stres"]
        perubahan["stres"] = catatan.stres
    for kolom in ("air", "olahraga"):
        tambah = data.get(kolom)
        if not tambah:
            continue
        bawah, atas, satuan = RENTANG[kolom]
        total = (getattr(catatan, kolom) or 0) + tambah
        if total > atas:
            errors.append(f"Total {kolom} hari ini jadi {total} {satuan}, kebanyakan. Cek lagi ya.")
            continue
        setattr(catatan, kolom, total)
        perubahan[kolom] = {"tambah": tambah, "total": total}

    if data.get("pemicu"):
        lama = [p for p in (catatan.pemicu or "").split(",") if p]
        gabungan = list(dict.fromkeys(lama + data["pemicu"]))
        catatan.pemicu = ",".join(gabungan)
        perubahan["pemicu"] = data["pemicu"]

    # Cerita hari ini digabung jadi satu teks, sentimen dihitung dari keseluruhan
    catatan.cerita = f"{catatan.cerita} {pesan}".strip() if catatan.cerita else pesan
    catatan.sentimen = skor_sentimen(catatan.cerita)
    catatan.updated_at = datetime.now()
    db.session.commit()
    perubahan["sentimen"] = catatan.sentimen
    return catatan, perubahan, errors


def balasan_catat(catatan, perubahan, errors, pesan, empati=None, sudah_tanya_stres=False):
    """Balasan untuk pesan 'catat': kalimat empati dari LLM (jika ada) + konfirmasi data dari kode.

    Angka selalu ditulis oleh kode (bukan LLM) supaya pasti sama dengan yang tersimpan.
    Stres hanya ditanyakan jika belum dicatat dan belum ditanyakan di balasan sebelumnya.
    """
    bagian = [empati.strip()] if empati else []

    if "tidur" in perubahan:
        t = perubahan["tidur"]
        if t < 6:
            komentar = "itu kurang banget."
        elif t < 7:
            komentar = "agak kurang dari 7 jam."
        elif t <= 9:
            komentar = "pas, mantap."
        else:
            komentar = "lumayan panjang."
        bagian.append(f"Tidur {angka(t)} jam tercatat, {komentar}")

    tercatat = []
    if "air" in perubahan:
        tercatat.append(f"air {perubahan['air']['total']}/{insight.TARGET_AIR} gelas")
    if "olahraga" in perubahan:
        tercatat.append(f"olahraga {perubahan['olahraga']['total']} menit")
    if tercatat:
        teks = " dan ".join(tercatat)
        bagian.append(teks[0].upper() + teks[1:] + " hari ini sudah tercatat.")

    if "stres" in perubahan:
        nilai = perubahan["stres"]
        if nilai <= 3:
            bagian.append(f"Stres {nilai} tercatat, syukurlah hari ini cukup tenang.")
        else:
            # stres >= 7 sudah dikomentari oleh saran pertama ("Stresmu tinggi...")
            bagian.append(f"Stres {nilai} tercatat.")
        saran = insight.rekomendasi_hari_ini(catatan)
        if saran:
            bagian.append(saran[0])  # satu saran diselipkan setelah stres dicatat

    if not bagian:
        # Cerita tanpa angka dan tanpa kalimat empati dari LLM (misalnya mode regex)
        label = label_sentimen(skor_sentimen(pesan))
        if label == "negatif":
            bagian.append("Makasih udah cerita. Kedengarannya hari ini berat, ya.")
        elif label == "positif":
            bagian.append("Ikut senang dengernya! Ceritamu sudah kucatat.")
        else:
            bagian.append("Oke, ceritamu sudah kucatat.")

    bagian.extend(errors)
    if catatan.stres is None and "stres" not in perubahan and not sudah_tanya_stres:
        bagian.append(TANYA_STRES)
    return " ".join(bagian)


# ---------------------------------------------------------------------------
# 3b. Tanya & saran: backend menghitung, LLM menyusun kalimat
# ---------------------------------------------------------------------------

def _rata(baris, kolom):
    nilai = [getattr(c, kolom) for c in baris if getattr(c, kolom) is not None]
    return round(sum(nilai) / len(nilai), 1) if nilai else None


def fakta_ringkasan(user_id=DEFAULT_USER_ID):
    hari_ini = date.today()
    mulai = hari_ini - timedelta(days=6)
    minggu_ini = CatatanHarian.query.filter(
        CatatanHarian.user_id == user_id, CatatanHarian.tanggal >= mulai, CatatanHarian.tanggal <= hari_ini
    ).all()
    minggu_lalu = CatatanHarian.query.filter(
        CatatanHarian.user_id == user_id,
        CatatanHarian.tanggal >= mulai - timedelta(days=7),
        CatatanHarian.tanggal < mulai,
    ).all()
    if not minggu_ini:
        return {"data_cukup": False, "keterangan": "belum ada catatan dalam 7 hari terakhir"}, \
            "Belum ada catatan dalam 7 hari terakhir. Yuk mulai cerita soal harimu!"

    fakta = {
        "periode": "7 hari terakhir",
        "hari_tercatat": len(minggu_ini),
        "rata_tidur_jam": _rata(minggu_ini, "tidur"),
        "rata_air_gelas": _rata(minggu_ini, "air"),
        "rata_olahraga_menit": _rata(minggu_ini, "olahraga"),
        "rata_stres": _rata(minggu_ini, "stres"),
        "rata_stres_minggu_lalu": _rata(minggu_lalu, "stres"),
        "rata_tidur_minggu_lalu": _rata(minggu_lalu, "tidur"),
    }
    teks = (f"Dalam 7 hari terakhir ({fakta['hari_tercatat']} hari tercatat), rata-rata tidurmu "
            f"{angka(fakta['rata_tidur_jam'])} jam, air {angka(fakta['rata_air_gelas'])} gelas, olahraga "
            f"{angka(fakta['rata_olahraga_menit'])} menit, dan stres {angka(fakta['rata_stres'])}")
    if fakta["rata_stres"] is not None and fakta["rata_stres_minggu_lalu"] is not None:
        selisih = round(fakta["rata_stres"] - fakta["rata_stres_minggu_lalu"], 1)
        arah = "naik" if selisih > 0 else "turun" if selisih < 0 else "sama"
        fakta["perubahan_stres_dari_minggu_lalu"] = f"{arah} {angka(abs(selisih))}" if selisih else "sama"
        teks += f", {arah} {angka(abs(selisih))} dari minggu lalu" if selisih else ", sama seperti minggu lalu"
    return fakta, teks + "."


def fakta_hari_ini(user_id=DEFAULT_USER_ID):
    c = catatan_hari_ini(user_id)
    if c is None:
        return {"ada_catatan": False}, "Belum ada catatan hari ini. Ceritain harimu, nanti aku catat."
    fakta = {
        "ada_catatan": True,
        "tidur_jam": c.tidur, "air_gelas": c.air, "target_air_gelas": insight.TARGET_AIR,
        "olahraga_menit": c.olahraga, "stres": c.stres,
        "pemicu": c.pemicu.split(",") if c.pemicu else [],
        "belum_dicatat": [k for k in ("tidur", "stres") if getattr(c, k) is None],
    }
    teks = (f"Hari ini: tidur {angka(c.tidur)} jam, air {c.air}/{insight.TARGET_AIR} gelas, "
            f"olahraga {c.olahraga} menit, stres {angka(c.stres)}.")
    return fakta, teks


def fakta_prediksi(data, user_id=DEFAULT_USER_ID):
    hasil_latih = prediksi.latih_model_harian(user_id)
    if hasil_latih is None:
        return {"data_cukup": False, "minimal_hari": prediksi.MIN_HARI_REGRESI}, \
            f"Prediksi butuh minimal {prediksi.MIN_HARI_REGRESI} hari catatan lengkap. Lanjutkan mencatat ya!"
    if all(data.get(k) is None for k in prediksi.FITUR_HARIAN):
        return None, "Sebutin angkanya ya, misalnya \"kalau tidur 8 jam stresku berapa?\""

    biasa = prediksi.rata_rata_kebiasaan(user_id)
    masukan = {k: data[k] if data.get(k) is not None else biasa[k] for k in prediksi.FITUR_HARIAN}
    nilai = prediksi.prediksi_stres(**masukan, user_id=user_id, hasil_latih=hasil_latih)
    dasar = prediksi.prediksi_stres(**biasa, user_id=user_id, hasil_latih=hasil_latih)
    selisih = round(nilai - dasar, 1)
    arah = "turun" if selisih < 0 else "naik" if selisih > 0 else "tetap"
    perubahan = f"{arah} {angka(abs(selisih))} poin" if selisih else "tetap sama"
    fakta = {
        "pengandaian": {k: data[k] for k in prediksi.FITUR_HARIAN if data.get(k) is not None},
        "kebiasaanmu_7_hari_terakhir": biasa,
        "perkiraan_stres_kalau_begitu": nilai,
        "perkiraan_stres_kalau_kebiasaan_tetap": dasar,
        "perubahan": perubahan,
        "catatan": "perkiraan dari pola catatanmu sendiri, skala 1-10",
    }
    teks = f"Kalau begitu, stresmu diperkirakan sekitar {angka(nilai)}"
    teks += f", {perubahan} dibanding kebiasaanmu sekarang ({angka(dasar)})." if selisih else ", sama seperti kebiasaanmu sekarang."
    return fakta, teks


def _rapikan_angka(nilai):
    """7.0 -> 7 supaya LLM tidak menulis '7,0 gelas'."""
    if isinstance(nilai, float) and nilai.is_integer():
        return int(nilai)
    if isinstance(nilai, dict):
        return {k: _rapikan_angka(v) for k, v in nilai.items()}
    if isinstance(nilai, list):
        return [_rapikan_angka(v) for v in nilai]
    return nilai


def susun_kalimat(pesan, fakta, cadangan, sebelumnya=None):
    """LLM menyusun kalimat dari fakta hasil hitungan backend; cadangan dipakai jika LLM gagal.

    `sebelumnya` (ChatHistory terakhir) dikirim sebagai konteks supaya jawaban nyambung.
    """
    fakta = _rapikan_angka(fakta)
    isi = ""
    if sebelumnya is not None:
        isi += f"Percakapan sebelumnya:\nMahasiswa: {sebelumnya.pesan}\nSKSehat: {sebelumnya.balasan}\n\n"
    isi += (f"Pesan mahasiswa sekarang: {pesan}\n"
            f"Data dari sistem (JSON): {json.dumps(fakta, ensure_ascii=False, default=str, separators=(',', ':'))}")
    try:
        teks, _ = llm.chat(
            [
                {"role": "system", "content": llm.PROMPT_JAWAB},
                {"role": "user", "content": isi},
            ],
            temperature=0.4,
            max_tokens=300,
            timeout=8,
            reasoning_effort="low",
            max_retries=0,  # gagal cepat -> kalimat template
        )
        return " ".join(teks.split())  # rapikan spasi dan baris baru berlebih

    except llm.LLMError:
        return cadangan


def jawab_tanya(data, pesan, user_id=DEFAULT_USER_ID, pakai_llm=True, sebelumnya=None):
    topik = data.get("topik") or "lainnya"
    if topik == "lanjutan" and sebelumnya is not None:
        # "maksudnya?" -> jelaskan ulang jawaban sebelumnya dengan lebih sederhana
        fakta = {"jawaban_sebelumnya": sebelumnya.balasan,
                 "instruksi": "jelaskan ARTI jawaban sebelumnya dengan kata-kata lain yang lebih sederhana, "
                              "seperti menjelaskan ke teman; jangan mengulang kalimatnya, tanpa angka baru"}
        cadangan = "Maksudku: " + sebelumnya.balasan
        return susun_kalimat(pesan, fakta, cadangan, sebelumnya) if pakai_llm else cadangan
    if topik == "prakiraan":
        # Prakiraan Cuaca Mental dibuat di tahap prakiraan; sementara dijawab apa adanya
        return ("Prakiraan Cuaca Mental belum tersedia, nanti bakal muncul di Beranda. "
                "Sementara itu, cek deadline terdekatmu di halaman Deadline ya.")
    if topik == "prediksi":
        fakta, cadangan = fakta_prediksi(data, user_id)
        if fakta is None or not fakta.get("perkiraan_stres_kalau_begitu"):
            return cadangan
    elif topik == "hari_ini":
        fakta, cadangan = fakta_hari_ini(user_id)
    else:  # ringkasan dan lainnya: pakai ringkasan + kondisi hari ini sebagai konteks
        fakta, cadangan = fakta_ringkasan(user_id)
        if topik == "lainnya":
            fakta = {"ringkasan_7_hari": fakta, "hari_ini": fakta_hari_ini(user_id)[0]}
    return susun_kalimat(pesan, fakta, cadangan, sebelumnya) if pakai_llm else cadangan


def jawab_saran(pesan, user_id=DEFAULT_USER_ID, pakai_llm=True, sebelumnya=None):
    saran = insight.rekomendasi_hari_ini(catatan_hari_ini(user_id), user_id=user_id)
    cadangan = " ".join(saran)
    if not pakai_llm:
        return cadangan
    fakta = {"saran_dari_sistem": saran, "instruksi": "sampaikan semua saran ini dengan bahasa santai, jangan tambah saran lain"}
    return susun_kalimat(pesan, fakta, cadangan, sebelumnya)


# ---------------------------------------------------------------------------
# Alur utama
# ---------------------------------------------------------------------------

def simpan_riwayat(pesan, balasan, jenis, sumber, user_id=DEFAULT_USER_ID):
    db.session.add(ChatHistory(user_id=user_id, pesan=pesan, balasan=balasan, jenis=jenis, sumber=sumber))
    db.session.commit()


def proses_pesan(pesan, sumber="web", user_id=DEFAULT_USER_ID):
    """Memproses satu pesan dari web atau Telegram.

    Mengembalikan dict: {"balasan", "jenis", "tersimpan", "mode"}
    - tersimpan: perubahan catatan hari ini (None jika tidak ada yang dicatat)
    - mode: "llm", "regex" (cadangan saat LLM tidak tersedia), atau "aturan" (tanpa LLM:
      pesan krisis dan jawaban angka atas pertanyaan stres)
    """
    pesan = (pesan or "").strip()[:BATAS_PESAN]

    # Pesan krisis dijawab langsung dengan arahan bantuan, tanpa diproses LLM
    if POLA_KRISIS.search(pesan):
        simpan_riwayat(pesan, BALASAN_KRISIS, "ngobrol", sumber, user_id)
        return {"balasan": BALASAN_KRISIS, "jenis": "ngobrol", "tersimpan": None, "mode": "aturan"}

    sebelumnya = chat_terakhir(user_id)
    sudah_tanya_stres = sebelumnya is not None and TANYA_STRES in (sebelumnya.balasan or "")
    cadangan = ekstrak_regex(pesan)

    angka_saja = POLA_ANGKA_SAJA.match(pesan)
    if angka_saja and sudah_tanya_stres:
        # Jawaban "8" atas pertanyaan stres: langsung dicatat sebagai stres tanpa LLM
        mentah = {"jenis": "catat", "stres": angka_saja.group(1)}
        mode = "aturan"
    else:
        mentah, mode = None, None
    try:
        if mentah is None:
            mentah = ekstrak_llm(pesan, sebelumnya.balasan if sebelumnya else None)
            mode = "llm"
        # Pengaman: pengandaian tanpa angka dari LLM -> ambil angka pengandaian dari regex
        if str(mentah.get("topik")).lower() == "prediksi" and all(mentah.get(k) is None for k in prediksi.FITUR_HARIAN):
            for k in prediksi.FITUR_HARIAN:
                mentah[k] = cadangan[k]
    except llm.LLMError as e:
        log.warning("Ekstraksi LLM gagal, pakai regex: %s", e)
        mentah = cadangan
        mode = "regex"

    mentah["_pesan"] = pesan  # dipakai pengaman topik di validasi
    data, errors = validasi_ekstraksi(mentah)
    jenis = data["jenis"]
    pakai_llm = mode in ("llm", "aturan")
    ada_data = any(data.get(k) is not None for k in RENTANG) or bool(data["pemicu"])
    tersimpan = None

    if jenis == "catat" and not ada_data and errors:
        # Contoh: "stres 15" -> tidak ada yang valid untuk disimpan, minta ulang saja
        balasan = " ".join(errors)
        errors = []
    elif jenis == "catat" or (jenis == "saran" and ada_data):
        catatan, tersimpan, err_simpan = simpan_catatan(data, pesan, user_id)
        if jenis == "catat":
            # Kalimat empati hanya untuk pesan yang berisi cerita (ada pemicu, bernada positif/negatif,
            # atau tanpa angka). Laporan angka biasa ("minum 2 gelas") cukup dikonfirmasi, supaya LLM
            # tidak salah menilai jumlahnya.
            ada_angka = any(data.get(k) is not None for k in RENTANG)
            bercerita = bool(data["pemicu"]) or label_sentimen(skor_sentimen(pesan)) != "netral" or not ada_angka
            empati = data.get("balasan") if mode == "llm" and bercerita else None
            balasan = balasan_catat(catatan, tersimpan, errors + err_simpan, pesan, empati, sudah_tanya_stres)
        else:
            balasan = jawab_saran(pesan, user_id, pakai_llm, sebelumnya)
    elif jenis == "tanya":
        balasan = jawab_tanya(data, pesan, user_id, pakai_llm, sebelumnya)
    elif jenis == "saran":
        balasan = jawab_saran(pesan, user_id, pakai_llm, sebelumnya)
    else:
        balasan = data.get("balasan") or cadangan.get("balasan") or \
            "Aku di sini kok. Ceritain aja harimu, atau tanya soal kebiasaanmu ya."

    if errors and jenis != "catat":
        balasan = " ".join(errors) + " " + balasan

    simpan_riwayat(pesan, balasan, jenis, sumber, user_id)
    return {"balasan": balasan, "jenis": jenis, "tersimpan": tersimpan, "mode": mode}
