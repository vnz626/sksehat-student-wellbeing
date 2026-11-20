"""Endpoint API JSON untuk JavaScript di halaman (/api/*).

Endpoint khusus bot (/api/bot/*) ditambahkan di tahap bot Telegram.
"""

from flask import Blueprint, jsonify, request

from services import chatbot
from services import jadwal as layanan_jadwal
from services.llm import LLMError

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/chat", methods=["POST"])
def chat():
    """Pesan chatbot web.

    Request : {"pesan": "semalem cuma tidur 4 jam"}
    Response: {"balasan": "...", "jenis": "catat", "tersimpan": {...}|null, "mode": "llm"|"regex"}
    """
    data = request.get_json(silent=True) or {}
    pesan = str(data.get("pesan") or "").strip()
    if not pesan:
        return jsonify({"error": "Pesannya masih kosong."}), 400
    if len(pesan) > chatbot.BATAS_PESAN:
        return jsonify({"error": f"Pesan terlalu panjang (maksimal {chatbot.BATAS_PESAN} karakter)."}), 400
    return jsonify(chatbot.proses_pesan(pesan, sumber="web"))


@api_bp.route("/jadwal/parse", methods=["POST"])
def jadwal_parse():
    """Teks KRS -> pratinjau jadwal (belum disimpan).

    Request : {"teks": "<teks KRS yang ditempel>"}
    Response: {"jadwal": [...], "errors": [...], "sumber": "groq"|"ollama"}
    """
    data = request.get_json(silent=True) or {}
    teks = str(data.get("teks") or "").strip()
    if not teks:
        return jsonify({"error": "Tempel teks KRS dulu."}), 400
    if len(teks) > layanan_jadwal.BATAS_TEKS_KRS:
        return jsonify({"error": f"Teks terlalu panjang (maksimal {layanan_jadwal.BATAS_TEKS_KRS} karakter)."}), 400

    try:
        sesi, errors, sumber = layanan_jadwal.parse_krs(teks)
    except LLMError:
        return jsonify({
            "error": "Asisten AI sedang tidak tersedia. Coba lagi nanti, atau impor dari file/input manual."
        }), 503

    return jsonify({
        "jadwal": [layanan_jadwal.sesi_ke_json(s) for s in sesi],
        "errors": errors,
        "sumber": sumber,
    })
