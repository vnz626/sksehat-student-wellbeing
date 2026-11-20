// Impor teks KRS: kirim teks ke /api/jadwal/parse, tampilkan tabel pratinjau
// yang bisa diedit, lalu form dikirim ke /jadwal (aksi=krs) untuk disimpan.
(function () {
  "use strict";

  const NAMA_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"];

  const tombolParse = document.getElementById("tombol-parse-krs");
  if (!tombolParse) return;

  const teks = document.getElementById("teks-krs");
  const status = document.getElementById("status-krs");
  const form = document.getElementById("form-pratinjau-krs");
  const isiTabel = document.getElementById("isi-pratinjau-krs");
  const daftarError = document.getElementById("error-krs");

  // Membuat <input> untuk satu sel tabel pratinjau
  function buatInput(nama, nilai, tipe, ekstra) {
    const input = document.createElement("input");
    input.type = tipe || "text";
    input.name = nama;
    input.value = nilai == null ? "" : nilai;
    Object.assign(input, ekstra || {});
    return input;
  }

  function buatPilihanHari(hari) {
    const select = document.createElement("select");
    select.name = "hari";
    NAMA_HARI.forEach(function (nama, i) {
      const opsi = document.createElement("option");
      opsi.value = String(i);
      opsi.textContent = nama;
      opsi.selected = i === hari;
      select.appendChild(opsi);
    });
    return select;
  }

  function tambahBaris(sesi) {
    const tr = document.createElement("tr");
    const sel = [
      buatInput("matkul", sesi.matkul, "text", { required: true, maxLength: 150 }),
      buatPilihanHari(sesi.hari),
      buatInput("jam_mulai", sesi.jam_mulai, "time", { required: true }),
      buatInput("jam_selesai", sesi.jam_selesai, "time", { required: true }),
      buatInput("ruang", sesi.ruang, "text", { maxLength: 50 }),
    ];
    sel.forEach(function (elemen) {
      const td = document.createElement("td");
      td.appendChild(elemen);
      tr.appendChild(td);
    });

    // Tombol buang baris yang salah tangkap
    const tdAksi = document.createElement("td");
    const tombolBuang = document.createElement("button");
    tombolBuang.type = "button";
    tombolBuang.textContent = "Buang";
    tombolBuang.addEventListener("click", function () {
      tr.remove();
      if (!isiTabel.children.length) form.hidden = true;
    });
    tdAksi.appendChild(tombolBuang);
    tr.appendChild(tdAksi);

    isiTabel.appendChild(tr);
  }

  function tampilkanError(errors) {
    daftarError.replaceChildren();
    (errors || []).forEach(function (pesan) {
      const li = document.createElement("li");
      li.textContent = "Dilewati: " + pesan;
      daftarError.appendChild(li);
    });
  }

  tombolParse.addEventListener("click", async function () {
    const isi = teks.value.trim();
    if (!isi) {
      status.textContent = "Tempel teks KRS dulu.";
      return;
    }

    tombolParse.disabled = true;
    status.textContent = "Sedang membaca jadwal...";
    try {
      const respons = await fetch(tombolParse.dataset.url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ teks: isi }),
      });
      const data = await respons.json();
      if (!respons.ok) {
        status.textContent = data.error || "Gagal membaca jadwal.";
        return;
      }

      isiTabel.replaceChildren();
      data.jadwal.forEach(tambahBaris);
      tampilkanError(data.errors);

      if (data.jadwal.length) {
        form.hidden = false;
        status.textContent = data.jadwal.length + " jadwal terbaca. Cek dan perbaiki sebelum disimpan.";
      } else {
        form.hidden = !data.errors.length;
        status.textContent = "Tidak ada jadwal yang terbaca dari teks itu.";
      }
    } catch (e) {
      status.textContent = "Gagal menghubungi server. Coba lagi.";
    } finally {
      tombolParse.disabled = false;
    }
  });

  document.getElementById("tombol-batal-krs").addEventListener("click", function () {
    isiTabel.replaceChildren();
    daftarError.replaceChildren();
    form.hidden = true;
    status.textContent = "";
  });
})();
