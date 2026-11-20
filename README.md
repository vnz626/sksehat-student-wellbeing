<div align="center">

# SKSehat

**Asisten kesehatan untuk mahasiswa yang memprediksi stres sebelum terjadi.**

Web app Flask + bot Telegram yang membaca jadwal kuliah, deadline, dan kebiasaan harian,
lalu menyajikan prakiraan stres 7 hari ke depan layaknya prakiraan cuaca.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?logo=scikitlearn&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-database-003B57?logo=sqlite&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram&logoColor=white)

</div>

---

## Tentang

Jadwal padat, kuliah pagi, deadline, dan ujian sering datang bersamaan. Jam tidur berkurang, olahraga terlupakan, dan stres baru terasa setelah terlanjur berat. Aplikasi pencatat kebiasaan pada umumnya hanya merekam data yang sudah lewat dan tidak mengenal ritme akademik.

**SKSehat** melihat ke depan. Dengan menggabungkan beban akademik yang akan datang dan pola kebiasaan pribadi, SKSehat memperkirakan hari-hari berat sebelum terjadi, menjelaskan penyebabnya, dan memberi saran yang disesuaikan untuk setiap pengguna.

Nama SKSehat berasal dari **SKS** (Satuan Kredit Semester) dan **sehat**: beban kuliah boleh berat, kesehatan tetap terjaga.

## Fitur Utama

### ⛅ Prakiraan Cuaca Mental
Prakiraan stres 7 hari ke depan berbasis regresi linear personal. Model memadukan rata-rata tidur, olahraga, dan sentimen 3 hari terakhir dengan jam kuliah, kuliah pagi, dan beban deadline per tanggal. Setiap hari ditampilkan sebagai ☀️ Tenang, ⛅ Berawan, 🌧️ Hujan, atau ⛈️ Badai, lengkap dengan alasan utama dan simulasi *what-if* ("Kalau aku tidur 8 jam?").

### 💬 Pencatatan lewat Percakapan
Cukup bercerita dengan bahasa sehari-hari, misalnya *"semalem cuma tidur 4 jam, laporan numpuk"*. LLM mengekstrak tidur, air, olahraga, stres, dan pemicu menjadi data terstruktur, lalu backend memvalidasinya. Tersedia di web dan Telegram, dengan cadangan berbasis regex saat LLM tidak tersedia.

### 📅 Impor Jadwal Kuliah
Impor sekali per semester dari teks KRS/SIAKAD (diparsing LLM dengan pratinjau), file `.ics`, CSV/Excel, atau input manual. Jadwal diolah menjadi fitur beban harian: jam kuliah, jumlah mata kuliah, kuliah pagi, dan jeda terpanjang.

### 🔍 Insight Personal
- **Pemicu Stres:** kategori pemicu dari cerita harian beserta porsinya dan dampaknya terhadap stres.
- **Sweet Spot:** regresi kuadrat untuk menemukan jam tidur dan menit olahraga dengan stres terendah bagi masing-masing pengguna.
- **Pola Hari:** K-Means mengelompokkan hari menjadi *Hari Sehat*, *Kurang Istirahat*, dan *Kurang Aktif*.
- **Prediksi Stres Harian:** regresi linear berganda dengan R², MAE, interpretasi koefisien, dan simulator.

### 📊 Dashboard & Rekomendasi
Ringkasan hari ini, tren 7/30 hari, rata-rata stres per hari dalam seminggu, dan maksimal tiga rekomendasi harian berbasis aturan.

### 🎁 SKSehat Wrapped
Rekap mingguan naratif yang dapat diunduh sebagai gambar: total tidur, hari paling tenang dan paling berat, pemicu terbesar, serta perbandingan dengan minggu sebelumnya.

### 🤖 Bot Telegram
Mencatat, bertanya, dan menerima notifikasi tanpa membuka web: check-in malam, prakiraan pagi, peringatan dini saat ada hari ⛈️, pengingat H-3 dan H-1 deadline, serta Wrapped setiap Minggu.

## Cara Kerja

```
 Browser ──┐                         ┌── services/ (LLM, sentimen, clustering,
           ├──► Flask (routes) ──────┤             prediksi, insight, jadwal)
 Telegram ─┘    /api/bot/*           └── SQLite via SQLAlchemy
 (bot.py)       (token rahasia)                    │
                                                   └── Groq API (gpt-oss-20b)
```

- Web dan bot memakai backend serta modul layanan yang sama, sehingga hasilnya selalu konsisten.
- Bot berjalan sebagai proses terpisah dan berkomunikasi lewat endpoint `/api/bot/*` yang dilindungi token rahasia.
- **Semua angka analisis dihitung oleh model sendiri** (scikit-learn). LLM hanya dipakai untuk mengekstrak teks dan menyusun kalimat jawaban.
- Hasil analisis dihitung ulang dari data terbaru setiap kali dibutuhkan; hanya Wrapped yang disimpan agar rekap lama tidak berubah.

## Tech Stack

| Lapisan | Teknologi |
| --- | --- |
| Backend | Python 3, Flask, Flask-SQLAlchemy |
| Database | SQLite |
| Machine learning | scikit-learn (K-Means, LinearRegression), pandas, NumPy |
| Analisis sentimen | Leksikon InSet atau Naive Bayes bahasa Indonesia |
| LLM | Groq API, `openai/gpt-oss-20b` (OpenAI-compatible, dapat diganti via `GROQ_MODEL`); cadangan lokal Ollama + Llama 3.2 3B |
| Bot | python-telegram-bot + JobQueue |
| Frontend | Jinja2, Bootstrap 5, JavaScript (fetch) |
| Visualisasi | Chart.js |

## Memulai

### Prasyarat

- Python 3.10+
- API key [Groq](https://console.groq.com)
- Token bot Telegram dari [@BotFather](https://t.me/BotFather) *(opsional, untuk fitur bot)*
- [Ollama](https://ollama.com) dengan model `llama3.2:3b` *(opsional, cadangan LLM lokal)*

### Instalasi

```bash
git clone <url-repo> sksehat
cd sksehat

python -m venv venv
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
```

### Konfigurasi

Salin `.env.example` menjadi `.env`, lalu isi nilainya:

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

```env
# Kunci rahasia Flask untuk session dan form
SECRET_KEY=ganti-dengan-string-acak

# API key Groq untuk chatbot LLM
GROQ_API_KEY=isi-api-key-groq
# Opsional: ganti model Groq (default openai/gpt-oss-20b)
# GROQ_MODEL=openai/gpt-oss-20b

# Token bot Telegram dari @BotFather
BOT_TOKEN=isi-token-bot-telegram

# Token rahasia bersama antara bot dan Flask untuk endpoint /api/bot/*
BOT_SECRET=ganti-dengan-string-acak-lain
```

String acak dapat dibuat dengan:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> `.env` berisi kredensial dan tidak boleh di-commit.

### Menjalankan

```bash
flask init-db        # membuat tabel di sksehat.db
python seed.py       # opsional: jadwal contoh, 60 hari catatan, dan 6 deadline
flask run            # http://127.0.0.1:5000
```

Untuk mengaktifkan bot, jalankan di terminal terpisah selagi aplikasi web berjalan:

```bash
python bot/bot.py
```

Kemudian buka **Profil → Hubungkan Telegram** dan kirim `/start <kode>` ke bot. Setelah tertaut, bot hanya melayani `chat_id` tersebut.

> Analisis membutuhkan data yang cukup: clustering minimal 14 hari, regresi dan prakiraan minimal 10 hari, Sweet Spot minimal 21 hari. Jalankan `seed.py` untuk mencoba semua fitur secara langsung.

## Perintah Bot

| Perintah | Fungsi |
| --- | --- |
| `/start <kode>` | Menautkan bot ke aplikasi |
| `/catat` atau pesan bebas | Mencatat cerita harian |
| `/jadwal` | Jadwal kuliah hari ini dan besok |
| `/deadline <judul> <tgl> <bobot>` | Menambah deadline, contoh: `/deadline UTS Basis Data 25-11 3` |
| `/prakiraan` | Prakiraan Cuaca Mental 7 hari |
| `/ringkasan` | Ringkasan 7 hari terakhir |
| `/saran` | Rekomendasi hari ini |
| `/wrapped` | SKSehat Wrapped minggu ini |

## Struktur Project

```
sksehat/
├── app.py                 # inisialisasi Flask, register blueprint
├── config.py              # baca .env: SECRET_KEY, GROQ_API_KEY, BOT_TOKEN, BOT_SECRET
├── models.py              # Profil, CatatanHarian, JadwalKuliah, Deadline, ChatHistory, Wrapped
├── seed.py                # jadwal contoh + data dummy 60 hari + deadline
├── routes/
│   ├── profil.py          # profil, tautkan Telegram
│   ├── main.py            # dashboard, chat, riwayat, jadwal, deadline, insight, wrapped
│   └── api.py             # /api/* dan /api/bot/*
├── services/
│   ├── llm.py             # klien Groq (OpenAI-compatible), prompt ekstraksi
│   ├── chatbot.py         # alur pesan, validasi JSON, cadangan regex
│   ├── jadwal.py          # parsing KRS/.ics/CSV, hitung beban kuliah per tanggal
│   ├── sentimen.py        # skor sentimen cerita
│   ├── clustering.py      # K-Means + pelabelan cluster
│   ├── prediksi.py        # regresi harian + Prakiraan Cuaca Mental
│   └── insight.py         # pemicu, Sweet Spot, rekomendasi, Wrapped
├── bot/
│   └── bot.py             # python-telegram-bot: perintah + JobQueue
├── templates/             # base, dashboard, chat, riwayat, jadwal,
│                          # deadline, insight, wrapped, profil
├── static/
│   ├── css/style.css
│   └── js/ (dashboard.js, chat.js, jadwal.js, insight.js)
├── .env                   # kunci rahasia, tidak di-commit
└── requirements.txt       # flask, flask-sqlalchemy, scikit-learn, pandas, openai,
                           # python-telegram-bot[job-queue], icalendar, python-dotenv
```

## Referensi API

| Endpoint | Method | Deskripsi |
| --- | --- | --- |
| `/api/chat` | POST | Mengirim pesan ke chatbot web |
| `/api/jadwal/parse` | POST | Parsing teks KRS menjadi pratinjau jadwal |
| `/api/data?range=7\|30` | GET | Data ringkasan dan tren |
| `/api/prakiraan` | GET | Prakiraan 7 hari; parameter `tidur` opsional untuk *what-if* |
| `/api/analisis` | GET | Hasil clustering, koefisien regresi, R², MAE |
| `/api/insight` | GET | Statistik pemicu dan kurva Sweet Spot |
| `/api/bot/pesan` | POST | Pesan dari Telegram ke chatbot *(token bot)* |
| `/api/bot/deadline` | POST | Menambah deadline dari bot *(token bot)* |
| `/api/bot/ringkas/<jenis>` | GET | Jadwal, prakiraan, ringkasan, saran, atau Wrapped *(token bot)* |

## Catatan

- Versi ini berjalan dalam **mode pribadi** untuk satu pengguna, tanpa login. Skema database tetap menyimpan `user_id` sehingga dukungan multi-pengguna dapat ditambahkan.
- Antarmuka dan input menggunakan bahasa Indonesia; skala stres 1–10.

## Disclaimer

SKSehat **bukan alat diagnosis medis**. Prediksi dan saran hanya membantu mengenali pola kebiasaan pribadi. Jika stres terasa berat atau berkepanjangan, hubungi konselor kampus atau tenaga profesional.
