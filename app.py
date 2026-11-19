"""Titik masuk aplikasi Flask SKSehat.

Jalankan dengan:  flask run
"""

from flask import Flask

from config import Config


def create_app(config_class=Config):
    """Membuat dan mengonfigurasi instance Flask (application factory)."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Blueprint (routes/profil.py, routes/main.py, routes/api.py)
    # didaftarkan di sini pada tahap-tahap berikutnya.

    @app.route("/")
    def index():
        # Halaman sementara untuk memastikan kerangka project berjalan
        return "<h1>SKSehat</h1><p>Asisten kesehatan untuk mahasiswa.</p>"

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
