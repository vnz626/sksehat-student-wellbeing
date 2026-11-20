"""Klien LLM SKSehat dan prompt ekstraksi.

Urutan penyedia:
1. Groq API (default openai/gpt-oss-20b), format OpenAI-compatible, butuh GROQ_API_KEY.
2. Cadangan lokal: Ollama (llama3.2:3b) di http://localhost:11434.

Model Llama 3.3 70B di rancangan awal sudah tidak tersedia di Groq, jadi diganti
gpt-oss-20b (paling cepat dan tetap akurat untuk ekstraksi). Model bisa diganti
lewat GROQ_MODEL di .env tanpa mengubah kode.

LLM hanya dipakai untuk mengubah teks menjadi data dan menyusun kalimat.
Semua angka analisis tetap dihitung oleh kode sendiri.
"""

import json
import logging
import os
import re

from flask import current_app, has_app_context
from openai import OpenAI

log = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL_DEFAULT = "openai/gpt-oss-20b"

# Model dan alamat bisa diatur lewat .env (opsional)
GROQ_MODEL = os.getenv("GROQ_MODEL") or GROQ_MODEL_DEFAULT
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


class LLMError(RuntimeError):
    """Semua penyedia LLM gagal atau jawabannya tidak bisa dipakai."""


def _groq_api_key():
    if has_app_context():
        return current_app.config.get("GROQ_API_KEY", "")
    return os.getenv("GROQ_API_KEY", "")


def _daftar_penyedia():
    """Penyedia yang dicoba berurutan: (nama, client, model)."""
    penyedia = []
    kunci = _groq_api_key()
    if kunci:
        penyedia.append(("groq", OpenAI(api_key=kunci, base_url=GROQ_BASE_URL, max_retries=1), GROQ_MODEL))
    # Ollama tidak butuh API key, tapi library openai tetap meminta isian
    penyedia.append(("ollama", OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL, max_retries=0), OLLAMA_MODEL))
    return penyedia


def chat(messages, json_mode=False, temperature=0.2, max_tokens=1024, timeout=20,
         reasoning_effort=None, max_retries=None):
    """Mengirim percakapan ke LLM dan mengembalikan (teks_jawaban, nama_penyedia).

    `messages` berformat OpenAI: [{"role": "system"|"user"|"assistant", "content": "..."}].
    `reasoning_effort` ("low"/"medium"/"high") hanya dikirim ke model gpt-oss di Groq;
    "low" membuat balasan chatbot jauh lebih cepat.
    `max_retries=0` membuat request gagal cepat (misalnya saat kena batas token per menit
    Groq), supaya chatbot langsung memakai cadangan alih-alih menunggu lama.
    Melempar LLMError jika semua penyedia gagal.
    """
    kesalahan = []
    for nama, client, model in _daftar_penyedia():
        if max_retries is not None and hasattr(client, "with_options"):
            client = client.with_options(max_retries=max_retries)
        try:
            argumen = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
            }
            if json_mode:
                argumen["response_format"] = {"type": "json_object"}
            if reasoning_effort and nama == "groq" and "gpt-oss" in model:
                argumen["reasoning_effort"] = reasoning_effort
            respons = client.chat.completions.create(**argumen)
            teks = (respons.choices[0].message.content or "").strip()
            if not teks:
                raise LLMError("jawaban kosong")
            return teks, nama
        except Exception as e:  # koneksi, kuota habis, key salah, dsb. -> coba penyedia berikutnya
            log.warning("LLM %s gagal: %s", nama, e)
            kesalahan.append(f"{nama}: {e.__class__.__name__}")
    raise LLMError("LLM tidak tersedia (" + "; ".join(kesalahan) + ")")


def ambil_json(teks):
    """Mengambil objek JSON dari jawaban LLM (membuang ```json ... ``` jika ada)."""
    bersih = re.sub(r"^```(?:json)?\s*|\s*```$", "", teks.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(bersih)
    except json.JSONDecodeError:
        # Kadang LLM menambahkan kalimat di luar JSON: ambil blok {...} terluar
        awal, akhir = bersih.find("{"), bersih.rfind("}")
        if awal != -1 and akhir > awal:
            try:
                return json.loads(bersih[awal : akhir + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError("jawaban LLM bukan JSON yang valid")


def chat_json(messages, **kwargs):
    """Seperti chat(), tetapi jawabannya langsung di-parse menjadi dict."""
    teks, penyedia = chat(messages, json_mode=True, **kwargs)
    data = ambil_json(teks)
    if not isinstance(data, dict):
        raise LLMError("jawaban LLM harus berupa objek JSON")
    return data, penyedia


# ---------------------------------------------------------------------------
# Prompt ekstraksi
# ---------------------------------------------------------------------------

PROMPT_KRS = """Kamu adalah pengurai jadwal kuliah. Pengguna menempelkan teks KRS atau jadwal dari SIAKAD
(bisa berupa tabel yang disalin, daftar, atau teks berantakan).

Ubah teks itu menjadi JSON dengan format PERSIS seperti ini:
{"jadwal": [{"matkul": "Basis Data", "hari": "Senin", "jam_mulai": "08:00", "jam_selesai": "10:30", "ruang": "Lab 2"}]}

Aturan:
- Satu objek untuk setiap pertemuan mingguan. Jika satu mata kuliah punya dua jadwal (misalnya teori dan praktikum), buat dua objek.
- "matkul": nama mata kuliah saja, tanpa kode, SKS, kelas, atau nama dosen.
- "hari": salah satu dari Senin, Selasa, Rabu, Kamis, Jumat, Sabtu, Minggu.
- "jam_mulai" dan "jam_selesai": format 24 jam HH:MM. Ubah 07.00 menjadi 07:00, dan 1 PM menjadi 13:00.
- Jika jam selesai tidak ada tetapi SKS ada, hitung jam selesai = jam mulai + SKS x 50 menit.
- "ruang": nama ruang jika ada, selain itu null.
- Abaikan baris yang bukan jadwal (judul tabel, total SKS, nama mahasiswa, dsb.).
- Jangan mengarang jadwal yang tidak ada di teks. Jika tidak ada jadwal sama sekali, kembalikan {"jadwal": []}.
- Balas hanya dengan JSON, tanpa penjelasan."""


KATEGORI_PEMICU = [
    "tugas", "ujian", "dosen", "organisasi", "keuangan", "keluarga", "hubungan", "kesehatan", "lainnya",
]

# Prompt dibuat ringkas: paket gratis Groq dibatasi token per menit,
# jadi makin pendek prompt, makin banyak pesan yang bisa diproses.
PROMPT_EKSTRAKSI = """Ubah pesan mahasiswa (bahasa Indonesia santai) menjadi JSON persis:
{"jenis":"catat","tidur":null,"air":null,"olahraga":null,"stres":null,"pemicu":[],"topik":null,"balasan":null}

jenis: catat = melaporkan kebiasaan/cerita harinya; tanya = bertanya tentang datanya sendiri;
saran = minta saran/tips; ngobrol = sapaan atau lainnya.
Angka diisi hanya jika disebut (jangan menebak): tidur = jam tidur semalam; air = gelas di pesan ini
(1 liter = 4 gelas); olahraga = menit (1 jam = 60); stres = angka yang ditulis, apa adanya walau di luar 1-10.
Untuk pengandaian ("kalau tidur 8 jam stresku berapa?") isi angka pengandaiannya.
pemicu = penyebab beban yang disebut jelas, hanya dari: tugas, ujian, dosen, organisasi, keuangan, keluarga,
hubungan, kesehatan, lainnya (laporan/praktikum = tugas; UTS/UAS/kuis = ujian; rapat/himpunan/UKM = organisasi;
uang/kos = keuangan; pacar/teman = hubungan; sakit = kesehatan).
topik (hanya tanya): ringkasan = minggu ini/rata-rata; hari_ini; prediksi = pengandaian;
prakiraan = hari berat ke depan/besok/minggu depan; lainnya.
balasan (hanya ngobrol): 1-2 kalimat hangat, tanpa diagnosis medis.

Contoh: "semalem begadang ngerjain laporan, cuma tidur 4 jam"
{"jenis":"catat","tidur":4,"air":null,"olahraga":null,"stres":null,"pemicu":["tugas"],"topik":null,"balasan":null}
Contoh: "kalau tidur 8 jam stresku berapa?"
{"jenis":"tanya","tidur":8,"air":null,"olahraga":null,"stres":null,"pemicu":[],"topik":"prediksi","balasan":null}
Contoh: "kapan aku paling stres minggu depan?"
{"jenis":"tanya","tidur":null,"air":null,"olahraga":null,"stres":null,"pemicu":[],"topik":"prakiraan","balasan":null}
Balas hanya JSON."""

PROMPT_JAWAB = """Kamu SKSehat, teman dan asisten kesehatan mahasiswa. Jawab pertanyaan mahasiswa HANYA dari data JSON sistem.
Aturan: bahasa Indonesia santai, hangat, dan pendek (1-3 kalimat), tanpa sapaan pembuka dan tanpa kata
bahasa Inggris (misalnya overall, keep it up). Pakai angka persis seperti di data (jangan dibulatkan,
dihitung ulang, atau ditambah); desimal pakai koma. Jika data berisi selisih atau perubahan, sebutkan juga.
Kata "rata" di data berarti rata-rata harian. Jika fitur belum tersedia atau data belum cukup, sampaikan dengan ramah.
Tanpa diagnosis medis, tanpa markdown."""
