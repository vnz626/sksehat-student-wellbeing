"""Prediksi stres dengan regresi linear.

Isi saat ini (dipakai chatbot untuk pertanyaan "kalau tidur X jam, stresku berapa?"):
    stres = b0 + b1*tidur + b2*air + b3*olahraga

Evaluasi (R², MAE), insight koefisien, dan Prakiraan Cuaca Mental
ditambahkan di tahap regresi dan prakiraan.
"""

from datetime import date, timedelta

import pandas as pd
from sklearn.linear_model import LinearRegression

from models import DEFAULT_USER_ID, CatatanHarian

FITUR_HARIAN = ["tidur", "air", "olahraga"]
MIN_HARI_REGRESI = 10  # regresi hanya berjalan jika data cukup


def data_harian(user_id=DEFAULT_USER_ID):
    """DataFrame catatan yang bisa dipakai regresi (tidur dan stres terisi), urut tanggal."""
    baris = (
        CatatanHarian.query.filter(
            CatatanHarian.user_id == user_id,
            CatatanHarian.tidur.isnot(None),
            CatatanHarian.stres.isnot(None),
        )
        .order_by(CatatanHarian.tanggal)
        .all()
    )
    return pd.DataFrame(
        [{"tanggal": c.tanggal, "tidur": c.tidur, "air": c.air or 0,
          "olahraga": c.olahraga or 0, "stres": c.stres} for c in baris],
        columns=["tanggal", *FITUR_HARIAN, "stres"],
    )


def latih_model_harian(user_id=DEFAULT_USER_ID):
    """Melatih LinearRegression dari catatan user. None jika data kurang dari MIN_HARI_REGRESI."""
    df = data_harian(user_id)
    if len(df) < MIN_HARI_REGRESI:
        return None
    model = LinearRegression().fit(df[FITUR_HARIAN], df["stres"])
    return {"model": model, "jumlah_data": len(df)}


def batasi_stres(nilai):
    """Hasil prediksi dibatasi ke skala stres 1-10."""
    return round(min(10.0, max(1.0, float(nilai))), 1)


def prediksi_stres(tidur, air, olahraga, user_id=DEFAULT_USER_ID, hasil_latih=None):
    """Prediksi stres untuk kombinasi tidur (jam), air (gelas), olahraga (menit).

    Mengembalikan float 1-10, atau None jika data belum cukup.
    `hasil_latih` boleh diberikan supaya model tidak dilatih ulang.
    """
    hasil_latih = hasil_latih or latih_model_harian(user_id)
    if hasil_latih is None:
        return None
    x = pd.DataFrame([[tidur, air, olahraga]], columns=FITUR_HARIAN)
    return batasi_stres(hasil_latih["model"].predict(x)[0])


def rata_rata_kebiasaan(user_id=DEFAULT_USER_ID, hari=7):
    """Rata-rata tidur/air/olahraga dalam `hari` terakhir (dipakai sebagai nilai 'biasanya')."""
    df = data_harian(user_id)
    if df.empty:
        return None
    terbaru = df[df["tanggal"] >= date.today() - timedelta(days=hari - 1)]
    if terbaru.empty:
        terbaru = df.tail(hari)  # tidak ada data minggu ini: pakai catatan terakhir
    return {k: round(float(terbaru[k].mean()), 1) for k in FITUR_HARIAN}
