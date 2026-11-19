"""Route halaman Profil: nama, jam pesan bot, dan tautan Telegram."""

import secrets
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import DEFAULT_USER_ID, Profil, db

profil_bp = Blueprint("profil", __name__)


def ambil_profil():
    """Mengambil profil satu-satunya; dibuat otomatis jika belum ada."""
    profil = db.session.get(Profil, DEFAULT_USER_ID)
    if profil is None:
        profil = Profil(id=DEFAULT_USER_ID)
        db.session.add(profil)
        db.session.commit()
    return profil


def ambil_jam(form, nama, label):
    teks = (form.get(nama) or "").strip()
    try:
        return datetime.strptime(teks, "%H:%M").time()
    except ValueError:
        raise ValueError(f"{label} harus berformat JJ:MM, misalnya 21:00.")


@profil_bp.route("/profil", methods=["GET", "POST"])
def profil():
    data = ambil_profil()

    if request.method == "POST":
        nama = (request.form.get("nama") or "").strip()
        try:
            if not nama:
                raise ValueError("Nama wajib diisi.")
            if len(nama) > 100:
                raise ValueError("Nama maksimal 100 karakter.")
            jam_checkin = ambil_jam(request.form, "jam_checkin", "Jam check-in")
            jam_prakiraan = ambil_jam(request.form, "jam_prakiraan", "Jam prakiraan")
        except ValueError as e:
            flash(str(e), "error")
            return render_template("profil.html", profil=data, form=request.form), 400

        data.nama = nama
        data.jam_checkin = jam_checkin
        data.jam_prakiraan = jam_prakiraan
        db.session.commit()
        flash("Profil disimpan.", "sukses")
        return redirect(url_for("profil.profil"))

    form = {
        "nama": data.nama,
        "jam_checkin": data.jam_checkin.strftime("%H:%M"),
        "jam_prakiraan": data.jam_prakiraan.strftime("%H:%M"),
    }
    return render_template("profil.html", profil=data, form=form)


@profil_bp.route("/profil/tautkan", methods=["POST"])
def tautkan_telegram():
    """Membuat kode 6 digit yang dikirim user ke bot lewat /start <kode>."""
    data = ambil_profil()
    data.kode_tautan = f"{secrets.randbelow(10**6):06d}"
    db.session.commit()
    flash("Kode tautan dibuat. Kirim /start <kode> ke bot SKSehat.", "sukses")
    return redirect(url_for("profil.profil"))


@profil_bp.route("/profil/putuskan", methods=["POST"])
def putuskan_telegram():
    data = ambil_profil()
    data.telegram_chat_id = None
    data.kode_tautan = None
    db.session.commit()
    flash("Telegram tidak lagi tertaut.", "sukses")
    return redirect(url_for("profil.profil"))
