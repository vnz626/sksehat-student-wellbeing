"""Route halaman utama: dashboard, chat, riwayat, jadwal, deadline, insight, wrapped.

Riwayat (catatan harian) dan Deadline sudah lengkap CRUD-nya.
Halaman lain masih HTML polos dan diisi fiturnya di tahap berikutnya.
"""

from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import DEFAULT_USER_ID, CatatanHarian, Deadline, JadwalKuliah, db

main_bp = Blueprint("main", __name__)

NAMA_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


class ValidasiError(ValueError):
    """Error validasi input form; pesannya ditampilkan ke user."""


# ---------------------------------------------------------------------------
# Helper validasi
# ---------------------------------------------------------------------------

def ambil_tanggal(form, nama, label):
    teks = (form.get(nama) or "").strip()
    if not teks:
        raise ValidasiError(f"{label} wajib diisi.")
    try:
        return datetime.strptime(teks, "%Y-%m-%d").date()
    except ValueError:
        raise ValidasiError(f"{label} tidak valid.")


def ambil_angka(form, nama, label, bawah, atas, bulat=False, wajib=False, default=None):
    """Membaca angka dari form dan memastikan berada di rentang [bawah, atas]."""
    teks = (form.get(nama) or "").strip().replace(",", ".")
    if teks == "":
        if wajib:
            raise ValidasiError(f"{label} wajib diisi.")
        return default
    try:
        nilai = float(teks)
    except ValueError:
        raise ValidasiError(f"{label} harus berupa angka.")
    if bulat:
        if not nilai.is_integer():
            raise ValidasiError(f"{label} harus bilangan bulat.")
        nilai = int(nilai)
    if not bawah <= nilai <= atas:
        raise ValidasiError(f"{label} harus di antara {bawah} dan {atas}.")
    return nilai


def validasi_catatan(form):
    """Validasi form catatan harian sesuai aturan dokumen."""
    return {
        "tanggal": ambil_tanggal(form, "tanggal", "Tanggal"),
        "tidur": ambil_angka(form, "tidur", "Tidur", 0, 24),
        "air": ambil_angka(form, "air", "Air", 0, 30, bulat=True, default=0),
        "olahraga": ambil_angka(form, "olahraga", "Olahraga", 0, 600, bulat=True, default=0),
        "stres": ambil_angka(form, "stres", "Stres", 1, 10, bulat=True),
    }


def validasi_deadline(form):
    judul = (form.get("judul") or "").strip()
    if not judul:
        raise ValidasiError("Judul wajib diisi.")
    if len(judul) > 150:
        raise ValidasiError("Judul maksimal 150 karakter.")
    return {
        "judul": judul,
        "tanggal": ambil_tanggal(form, "tanggal", "Tanggal"),
        "bobot": ambil_angka(form, "bobot", "Bobot", 1, 3, bulat=True, wajib=True),
    }


# ---------------------------------------------------------------------------
# Halaman
# ---------------------------------------------------------------------------

@main_bp.route("/")
def dashboard():
    hari_ini = CatatanHarian.query.filter_by(
        user_id=DEFAULT_USER_ID, tanggal=date.today()
    ).first()
    return render_template("dashboard.html", hari_ini=hari_ini, tanggal=date.today())


@main_bp.route("/chat")
def chat():
    return render_template("chat.html")


@main_bp.route("/jadwal", methods=["GET", "POST"])
def jadwal():
    # Impor dan edit jadwal dikerjakan di tahap 6-7; sekarang hanya menampilkan
    daftar = (
        JadwalKuliah.query.filter_by(user_id=DEFAULT_USER_ID)
        .order_by(JadwalKuliah.hari, JadwalKuliah.jam_mulai)
        .all()
    )
    return render_template("jadwal.html", daftar=daftar, nama_hari=NAMA_HARI)


@main_bp.route("/insight")
def insight():
    return render_template("insight.html")


@main_bp.route("/wrapped")
def wrapped():
    return render_template("wrapped.html")


# ---------------------------------------------------------------------------
# Riwayat catatan harian (CRUD)
# ---------------------------------------------------------------------------

def _catatan_atau_404(id):
    return CatatanHarian.query.filter_by(id=id, user_id=DEFAULT_USER_ID).first_or_404()


def _tanggal_sudah_dipakai(tanggal, kecuali_id=None):
    query = CatatanHarian.query.filter_by(user_id=DEFAULT_USER_ID, tanggal=tanggal)
    if kecuali_id is not None:
        query = query.filter(CatatanHarian.id != kecuali_id)
    return query.first() is not None


@main_bp.route("/riwayat")
def riwayat():
    daftar = (
        CatatanHarian.query.filter_by(user_id=DEFAULT_USER_ID)
        .order_by(CatatanHarian.tanggal.desc())
        .all()
    )
    return render_template("riwayat.html", daftar=daftar)


@main_bp.route("/riwayat/tambah", methods=["GET", "POST"])
def riwayat_tambah():
    if request.method == "POST":
        try:
            data = validasi_catatan(request.form)
            if _tanggal_sudah_dipakai(data["tanggal"]):
                raise ValidasiError("Catatan untuk tanggal itu sudah ada. Edit catatan yang lama saja.")
        except ValidasiError as e:
            flash(str(e), "error")
            return render_template("riwayat_form.html", form=request.form, catatan=None), 400

        db.session.add(CatatanHarian(user_id=DEFAULT_USER_ID, **data))
        db.session.commit()
        flash("Catatan tersimpan.", "sukses")
        return redirect(url_for("main.riwayat"))

    form = {"tanggal": date.today().isoformat()}
    return render_template("riwayat_form.html", form=form, catatan=None)


@main_bp.route("/riwayat/<int:id>/edit", methods=["GET", "POST"])
def riwayat_edit(id):
    catatan = _catatan_atau_404(id)
    if request.method == "POST":
        try:
            data = validasi_catatan(request.form)
            if _tanggal_sudah_dipakai(data["tanggal"], kecuali_id=catatan.id):
                raise ValidasiError("Sudah ada catatan lain di tanggal itu.")
        except ValidasiError as e:
            flash(str(e), "error")
            return render_template("riwayat_form.html", form=request.form, catatan=catatan), 400

        for kolom, nilai in data.items():
            setattr(catatan, kolom, nilai)
        db.session.commit()
        flash("Catatan diperbarui.", "sukses")
        return redirect(url_for("main.riwayat"))

    form = {
        "tanggal": catatan.tanggal.isoformat(),
        "tidur": "" if catatan.tidur is None else catatan.tidur,
        "air": catatan.air,
        "olahraga": catatan.olahraga,
        "stres": "" if catatan.stres is None else catatan.stres,
    }
    return render_template("riwayat_form.html", form=form, catatan=catatan)


@main_bp.route("/riwayat/<int:id>/hapus", methods=["POST"])
def riwayat_hapus(id):
    catatan = _catatan_atau_404(id)
    db.session.delete(catatan)
    db.session.commit()
    flash(f"Catatan {catatan.tanggal:%d-%m-%Y} dihapus.", "sukses")
    return redirect(url_for("main.riwayat"))


# ---------------------------------------------------------------------------
# Deadline (CRUD + tandai selesai)
# ---------------------------------------------------------------------------

def _deadline_atau_404(id):
    return Deadline.query.filter_by(id=id, user_id=DEFAULT_USER_ID).first_or_404()


@main_bp.route("/deadline", methods=["GET", "POST"])
def deadline():
    form = {"bobot": "2"}
    status = 200
    if request.method == "POST":  # tambah deadline baru
        try:
            data = validasi_deadline(request.form)
        except ValidasiError as e:
            flash(str(e), "error")
            form, status = request.form, 400
        else:
            db.session.add(Deadline(user_id=DEFAULT_USER_ID, **data))
            db.session.commit()
            flash("Deadline ditambahkan.", "sukses")
            return redirect(url_for("main.deadline"))

    # Yang belum selesai diurutkan dari yang terdekat, lalu yang sudah selesai
    aktif = (
        Deadline.query.filter_by(user_id=DEFAULT_USER_ID, selesai=False)
        .order_by(Deadline.tanggal)
        .all()
    )
    selesai = (
        Deadline.query.filter_by(user_id=DEFAULT_USER_ID, selesai=True)
        .order_by(Deadline.tanggal.desc())
        .all()
    )
    return (
        render_template("deadline.html", aktif=aktif, selesai=selesai, form=form, hari_ini=date.today()),
        status,
    )


@main_bp.route("/deadline/<int:id>/edit", methods=["GET", "POST"])
def deadline_edit(id):
    item = _deadline_atau_404(id)
    if request.method == "POST":
        try:
            data = validasi_deadline(request.form)
        except ValidasiError as e:
            flash(str(e), "error")
            return render_template("deadline_form.html", form=request.form, item=item), 400

        for kolom, nilai in data.items():
            setattr(item, kolom, nilai)
        db.session.commit()
        flash("Deadline diperbarui.", "sukses")
        return redirect(url_for("main.deadline"))

    form = {"judul": item.judul, "tanggal": item.tanggal.isoformat(), "bobot": str(item.bobot)}
    return render_template("deadline_form.html", form=form, item=item)


@main_bp.route("/deadline/<int:id>/selesai", methods=["POST"])
def deadline_selesai(id):
    item = _deadline_atau_404(id)
    item.selesai = not item.selesai  # bisa ditandai selesai atau dibatalkan
    db.session.commit()
    flash(f"'{item.judul}' " + ("ditandai selesai." if item.selesai else "dibuka lagi."), "sukses")
    return redirect(url_for("main.deadline"))


@main_bp.route("/deadline/<int:id>/hapus", methods=["POST"])
def deadline_hapus(id):
    item = _deadline_atau_404(id)
    db.session.delete(item)
    db.session.commit()
    flash(f"Deadline '{item.judul}' dihapus.", "sukses")
    return redirect(url_for("main.deadline"))
