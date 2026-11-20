// Chatbot web: kirim pesan ke /api/chat lalu tampilkan balasannya di riwayat.
(function () {
  "use strict";

  const form = document.getElementById("form-chat");
  if (!form) return;

  const input = document.getElementById("input-chat");
  const tombol = document.getElementById("tombol-kirim");
  const riwayat = document.getElementById("riwayat-chat");

  // Menambah satu baris chat; textContent dipakai supaya teks tidak dibaca sebagai HTML
  function tambahPesan(pengirim, teks) {
    const kosong = document.getElementById("chat-kosong");
    if (kosong) kosong.remove();
    const p = document.createElement("p");
    const nama = document.createElement("strong");
    nama.textContent = pengirim;
    p.appendChild(nama);
    p.appendChild(document.createTextNode(": " + teks));
    riwayat.appendChild(p);
    p.scrollIntoView({ block: "end" });
    return p;
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const pesan = input.value.trim();
    if (!pesan) return;

    tambahPesan("Kamu", pesan);
    input.value = "";
    tombol.disabled = true;
    const menunggu = tambahPesan("SKSehat", "...");

    try {
      const respons = await fetch(form.dataset.url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pesan: pesan }),
      });
      const data = await respons.json();
      menunggu.lastChild.textContent = ": " + (respons.ok ? data.balasan : data.error || "Ada yang salah, coba lagi.");
    } catch (e) {
      menunggu.lastChild.textContent = ": Gagal menghubungi server. Coba lagi.";
    } finally {
      tombol.disabled = false;
      input.focus();
    }
  });
})();
