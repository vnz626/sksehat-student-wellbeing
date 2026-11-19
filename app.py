"""Titik masuk aplikasi Flask SKSehat.

Jalankan dengan:  flask run
Buat database:    flask init-db   (tambahkan --drop untuk mengosongkan ulang)
"""

import click
from flask import Flask

from config import Config
from models import DEFAULT_USER_ID, Profil, db


def create_app(config_class=Config):
    """Membuat dan mengonfigurasi instance Flask (application factory)."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Hubungkan SQLAlchemy ke aplikasi
    db.init_app(app)

    # Blueprint (routes/profil.py, routes/main.py, routes/api.py)
    # didaftarkan di sini pada tahap-tahap berikutnya.

    @app.route("/")
    def index():
        # Halaman sementara untuk memastikan kerangka project berjalan
        return "<h1>SKSehat</h1><p>Asisten kesehatan untuk mahasiswa.</p>"

    register_commands(app)
    return app


def register_commands(app):
    """Mendaftarkan perintah CLI tambahan untuk `flask`."""

    @app.cli.command("init-db")
    @click.option("--drop", is_flag=True, help="Hapus semua tabel dan datanya sebelum dibuat ulang.")
    def init_db(drop):
        """Membuat semua tabel di sksehat.db dan profil default."""
        if drop:
            db.drop_all()
            click.echo("Semua tabel lama dihapus.")

        db.create_all()

        # Mode pribadi: pastikan profil satu-satunya (id = 1) sudah ada
        if db.session.get(Profil, DEFAULT_USER_ID) is None:
            db.session.add(Profil(id=DEFAULT_USER_ID))
            db.session.commit()
            click.echo("Profil default dibuat.")

        click.echo("Database siap: " + app.config["SQLALCHEMY_DATABASE_URI"])


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
