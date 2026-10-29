# asisten-bei-turun

> **BUKAN SARAN INVESTASI.** Program pribadi yang membuat laporan otomatis dari aturan mekanis dan data publik yang
> bisa salah, terlambat, atau tidak lengkap. Hasil backtest dan paper trading tidak menjamin hasil di masa depan.
> Seluruh keputusan dan risiko transaksi menjadi tanggung jawab Anda.

Pasangan [asisten-bei](https://github.com/st4yn1ght/asisten-bei) untuk **masa IHSG tren turun**. asisten-bei hanya
merekomendasikan beli saat pasar naik atau netral, dan berstatus JANGAN BELI saat IHSG tren turun atau breadth lemah.
asisten-bei-turun justru hanya aktif pada keadaan itu. Setiap sore setelah bursa tutup, program menjawab:

1. **Kondisi pasar:** BOLEH BELI, HATI-HATI, atau JANGAN BELI (dengan strategi tren turun), beserta alasannya.
2. **Kandidat beli:** saham yang layak dibeli, dengan rencana lengkap (harga limit maksimal, stop loss, target, lot).
3. **Posisi yang Anda pegang dari alat ini:** tahan atau jual, dan di level berapa order otomatis stop/target dipasang.

Program **tidak** terhubung ke broker dan tidak pernah mengirim order. Kodenya salinan asisten-bei (commit `d849620`)
yang disesuaikan; spesifikasi lengkap ada di `SPEC.md`, panduan mengisi berkas di `contoh/PANDUAN_ISI.md`.

---

## Daftar isi

1. [Cara kerja: status pasar dan strategi](#1-cara-kerja-status-pasar-dan-strategi)
2. [Konsekuensi modal terpisah dan risiko 1%](#2-konsekuensi-modal-terpisah-dan-risiko-1)
3. [Instalasi](#3-instalasi)
4. [Berkas yang Anda isi sendiri](#4-berkas-yang-anda-isi-sendiri)
5. [Telegram](#5-telegram)
6. [Penjadwalan otomatis](#6-penjadwalan-otomatis)
7. [Rutinitas harian](#7-rutinitas-harian)
8. [Perintah dan berkas .bat](#8-perintah-dan-berkas-bat)
9. [Kode keluar dan masalah umum](#9-kode-keluar-dan-masalah-umum)
10. [Uji cepat dengan data nyata](#10-uji-cepat-dengan-data-nyata)
11. [Glosarium](#11-glosarium)

---

## 1. Cara kerja: status pasar dan strategi

Status pasar alat ini kebalikan asisten-bei (SPEC §10):

| Keadaan pasar | asisten-bei | asisten-bei-turun |
|---|---|---|
| IHSG tren turun: close < SMA200 **dan** SMA50 < SMA200 | JANGAN BELI | **BOLEH BELI** |
| Breadth lemah (< 30% saham di atas SMA50), IHSG belum tren turun | JANGAN BELI | **HATI-HATI** (risiko × 0,5, maks 1 entry baru per hari) |
| Selain itu (pasar naik atau netral) | BOLEH BELI / HATI-HATI | **JANGAN BELI** (pakai asisten-bei) |
| Data tidak lengkap | JANGAN BELI | JANGAN BELI |

Strategi (SPEC §12), semuanya membeli dengan order limit di `harga_maks` pada pembukaan hari bursa berikutnya:

| Strategi | Kapan beli | Stop loss | Cara keluar |
|---|---|---|---|
| **TP** — saham tangguh: pullback | Saham tetap dalam tren naiknya sendiri (close > SMA50 > SMA200), **unggul dari IHSG ≥ 10%** dalam 60 hari bursa, sempat turun menyentuh SMA20, lalu memantul | Titik terendah 5 hari − 0,2 ATR | Target 2R, atau stop waktu (close hari ke-10, jual hari ke-11) |
| **TB** — saham tangguh: breakout | Close menembus harga tertinggi 20 hari dengan volume ≥ 1,5 × rata-rata, tren naik sendiri, **unggul dari IHSG ≥ 10%** | Close − 2 ATR | Trailing stop 3 ATR dari harga tertinggi sejak beli (perbarui setiap sore) |
| **PJ** — pantulan jenuh jual | RSI(2) saham < 5 **dan** RSI(2) IHSG < 20 (seluruh pasar jatuh), bukan jatuh ekstrem dalam sehari | Close − 2,5 ATR | Jual setelah close > SMA5 (mulai hari pertama), paling lama 5 hari |

PJ tidak mensyaratkan tren naik saham, jadi saham yang sedang jatuh bisa terus jatuh; karena itu stop dan stop
waktunya ketat. Setiap strategi baru boleh merekomendasikan beli setelah **lolos gerbang backtest**; sebelum itu
sinyalnya hanya dicatat sebagai bayangan (`BAYANGAN_GERBANG`). Pilihan `acak` di `backtest --strategi` adalah
pembanding acak untuk menguji mesin backtest, bukan strategi sungguhan.

---

## 2. Konsekuensi modal terpisah dan risiko 1%

Ringkasan SPEC §3. Alat ini memakai **modal terpisah** yang Anda sisihkan dari kas: risiko 1% ekuitas alat ini per
transaksi (setengahnya saat HATI-HATI), maksimal 2 posisi, 1 posisi per sektor, dan alokasi per posisi = ekuitas ÷ 2.
Fee beli 0,15%, fee jual 0,25%, dan slippage 0,10% sudah dihitung. Lot dihitung dari `harga_maks`, dan jarak stop
`d` diukur dari `harga_maks`.

**Harga maksimal agar risiko 1 lot ≤ 1% ekuitas** (saat HATI-HATI: setengahnya):

| Jarak stop `d` (dari harga_maks) | Ekuitas Rp 1 juta | Ekuitas Rp 2 juta | Ekuitas Rp 3 juta |
|---|---|---|---|
| 3% | ≈ Rp 2.870 | ≈ Rp 5.730 | ≈ Rp 8.600 |
| 5% | ≈ Rp 1.820 | ≈ Rp 3.650 | ≈ Rp 5.470 |
| 8% | ≈ Rp 1.180 | ≈ Rp 2.360 | ≈ Rp 3.540 |
| 10% | ≈ Rp 960 | ≈ Rp 1.910 | ≈ Rp 2.870 |
| 12% | ≈ Rp 800 | ≈ Rp 1.610 | ≈ Rp 2.410 |

Akibatnya:

- Pasar turun biasanya lebih bergejolak (ATR lebih besar), sehingga jarak stop lebih lebar dan harga yang terjangkau
  lebih rendah daripada di asisten-bei. Jarak stop tipikal pada ATR 4% dari harga: TB ≈ 9,8%, PJ ≈ 11,8%.
- Dengan modal kecil, banyak kandidat akan `TIDAK_TERJANGKAU`. Wajar bila berhari-hari tidak ada rekomendasi beli.
  Saat HATI-HATI, hampir semua kandidat tidak terjangkau.
- Saham di atas ≈ ekuitas ÷ 200 per lembar (≈ Rp 14.980 pada ekuitas Rp 3 juta) tidak bisa dibeli walau 1 lot.
- Bila kedua posisi kena stop pada hari yang sama, kerugiannya ± 2% ekuitas alat ini, atau lebih bila harga gap di
  bawah stop. Bila asisten-bei juga memegang posisi, risiko akun Anda adalah jumlah keduanya.
- Hari tren turun jauh lebih sedikit daripada hari biasa, sehingga backtest menghasilkan sedikit transaksi. Syarat
  gerbang "≥ 30 transaksi di holdout" bisa tidak tercapai, dan strategi itu tetap bayangan. Gerbang sengaja tidak
  dilonggarkan untuk alat ini.
- Ringkasan backtest juga menampilkan kinerja subset transaksi yang terjangkau modal Anda. Jika subset ini lemah,
  laporan harian memberi peringatan.

---

## 3. Instalasi

Windows 10/11. Pasang di **folder terpisah** dari asisten-bei (mis. `C:\asisten-bei-turun` di samping
`C:\asisten-bei`); kedua alat punya `.venv`, cache, jurnal, dan laporan sendiri. Ikuti berurutan; setiap langkah memakai
klik ganda pada berkas di folder `scripts\`.

1. **Python 3.12 atau 3.13 (64-bit)** dari python.org, dengan **"Add python.exe to PATH"** dan **"py launcher"**
   dicentang. Bila sudah terpasang untuk asisten-bei, lewati langkah ini.
2. **Ekstrak folder `asisten-bei-turun`** ke jalur sederhana. **Jangan** di dalam OneDrive atau Dropbox:
   sinkronisasi bisa mengunci `data\jurnal.sqlite` dan cache.
3. **Klik ganda `scripts\pasang.bat`.** Skrip membuat `.venv` khusus folder ini lalu memasang semua paket (beberapa
   menit; perlu internet). Bila muncul "Python 3.12 atau 3.13 tidak ditemukan", ulangi langkah 1.
4. **Salin isian dari asisten-bei dan isi modal alat ini** — lihat [bagian 4](#4-berkas-yang-anda-isi-sendiri).
5. **Klik ganda `scripts\cek.bat`** dan perbaiki setiap baris ERROR. Baca juga setiap PERINGATAN dan item
   "BELUM DIVERIFIKASI".
6. **Klik ganda `scripts\unduh.bat`.** Unduhan pertama (riwayat sejak 2013) bisa lama. Periksa ringkasannya.
7. **Klik ganda `scripts\backtest.bat`**, lalu buka `ringkasan.html` di folder run terbaru
   `output\backtest\<YYYYMMDD-HHMMSS>_<kode>\`. Perhatikan apakah TP, TB, dan PJ lolos gerbang.
8. **Siapkan Telegram** ([bagian 5](#5-telegram)), lalu klik ganda `scripts\uji_telegram.bat`.
9. **Klik ganda `scripts\harian.bat`** sekali secara manual dan baca `output\laporan\<tanggal>\laporan.html`.
10. **Daftarkan jadwal** dengan klik ganda `scripts\daftar_jadwal.bat` ([bagian 6](#6-penjadwalan-otomatis)).

Setiap jendela `.bat` manual menampilkan kode keluar ([bagian 9](#9-kode-keluar-dan-masalah-umum)) dan menunggu
Anda menekan tombol sebelum menutup.

Untuk pengembang (Linux/macOS):

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e . --no-deps
.venv/bin/python -m pytest -q
```

---

## 4. Berkas yang Anda isi sendiri

**Memindahkan isian dari asisten-bei.** Isian pasar sama dengan asisten-bei, jadi cukup disalin dari folder
asisten-bei Anda:

- berkas `input\universe.csv`, `breadth_universe.csv`, `universe_history.csv`, `exclude.csv`, `holidays.csv`, dan
  `anomali_ok.csv` (yang ada saja);
- dari `config.yaml`: bagian `pasar` (jadwal sesi, fraksi harga, ARA/ARB), `biaya`, serta
  `data.pengali_volume` dan `data.pengali_volume_terverifikasi`. **Jangan** menyalin seluruh `config.yaml`, karena
  bagian `risiko`, `jadwal`, dan `strategi` alat ini berbeda;
- berkas `.env` (Telegram; boleh memakai bot yang sama).

**Yang tidak disalin (modal terpisah):** buat `input\akun.yaml` berisi kas yang Anda sisihkan untuk alat ini
(contoh: `contoh\input\akun.yaml`), biarkan `input\portfolio.csv` hanya berisi baris judul, dan setel
`akun.modal_awal_idr` di `config.yaml` ke jumlah yang sama (dipakai backtest `realistis` dan jurnal kertas). Jangan
memasukkan posisi asisten-bei ke sini. Kode strategi di `portfolio.csv` alat ini: `TP`, `TB`, `PJ`, atau `MANUAL`.

Format setiap berkas ada di **`contoh/PANDUAN_ISI.md`**. Edit CSV dengan **Notepad**, bukan Excel; angka tanpa
pemisah ribuan (`2850`, bukan `2.850`); tanggal `YYYY-MM-DD`.

**Daftar cek (SPEC §24):**

| # | Item | Di mana | Sumber |
|---|---|---|---|
| 1 | Konstituen universe (mis. LQ45 terbaru) + sektor | `input\universe.csv` | Salin dari asisten-bei |
| 2 | Daftar saham breadth (100–200 saham likuid) | `input\breadth_universe.csv` | Salin dari asisten-bei |
| 3 | Riwayat konstituen (opsional) | `input\universe_history.csv` | Salin dari asisten-bei |
| 4 | Saham suspensi / notasi khusus / papan pemantauan khusus | `input\exclude.csv` | Salin; perbarui di kedua alat setiap ada pengumuman |
| 5 | Kalender libur tahun berjalan **dan** tahun berikutnya | `input\holidays.csv` | Salin; perbarui di kedua alat |
| 6 | Jadwal sesi (jam penutupan, pra-pembukaan) | `config.yaml → pasar.jadwal_sesi` | Salin dari asisten-bei |
| 7 | Tabel fraksi harga + tanggal berlaku | `config.yaml → pasar.fraksi_harga` | Salin dari asisten-bei |
| 8 | Batas ARA/ARB, harga acuan, tanggal berlaku | `config.yaml → pasar.auto_reject` | Salin dari asisten-bei |
| 9 | Fee beli/jual, biaya minimum, pembulatan fee | `config.yaml → biaya` | Salin dari asisten-bei |
| 10 | Satuan volume (`pengali_volume_terverifikasi`) | `config.yaml → data` | Salin dari asisten-bei |
| 11 | Fitur order broker | `contoh\cek_fitur_broker.md` | Sama dengan asisten-bei |
| 12 | Saldo kas dan posisi **alat ini** | `input\akun.yaml`, `input\portfolio.csv` | Kas yang Anda sisihkan; posisi dari rekomendasi alat ini |
| 13 | Token & chat ID Telegram | `.env` | Salin dari asisten-bei ([bagian 5](#5-telegram)) |
| 14 | `holdout_mulai` | `config.yaml → backtest` | Tetapkan sekali sebelum backtest pertama, lalu jangan diubah |

Item 6–8 sengaja kosong saat rilis. **Jangan mengisinya dari ingatan** — salin dari asisten-bei, yang sumbernya
idx.co.id. Selama `terverifikasi: false`, harga dibulatkan ke rupiah bulat dan setiap laporan meminta Anda membulatkan
sendiri ke fraksi valid (limit beli dan target ke **bawah**, stop ke **atas**).

Akibat beberapa isian:

- **`input\holidays.csv`** harus berisi tahun berjalan dan tahun berikutnya; tanpa itu `cek` dan setiap laporan
  memberi peringatan. Tanggal Sabtu/Minggu tidak perlu ditulis.
- **`input\akun.yaml`** yang `diperbarui`-nya lebih tua dari 5 hari bursa memicu peringatan "akun basi".
- Mengubah aturan di `config.yaml` atau berkas universe/breadth/holidays/anomali membuat strategi berstatus
  `BAYANGAN_GERBANG` sampai `backtest.bat` dijalankan ulang; hasil backtest juga kedaluwarsa setelah 90 hari.

---

## 5. Telegram

Bila asisten-bei sudah terhubung ke Telegram, salin saja berkas `.env`-nya ke folder ini; pesan alat ini berjudul
**"Asisten BEI Turun"**, jadi mudah dibedakan. Bila belum:

1. Di aplikasi Telegram, buka **@BotFather**, kirim `/newbot`, ikuti langkahnya, lalu salin **token** yang diberikan.
2. Kirim pesan apa pun (mis. "halo") ke bot baru Anda.
3. Salin `.env.example` menjadi berkas bernama tepat **`.env`** di folder utama, lalu isi `TELEGRAM_BOT_TOKEN`.
   Di Notepad pilih *Simpan sebagai jenis: Semua berkas* agar namanya `.env`, **bukan** `.env.txt` (`cek` mendeteksi
   kesalahan ini). Jangan bagikan berkas ini.
4. Buka Command Prompt di folder proyek dan jalankan `scripts\uji_telegram.bat --cari-chat-id`. Salin angka chat ID
   yang dicetak ke `TELEGRAM_CHAT_ID` di `.env`.
5. Klik ganda `scripts\uji_telegram.bat`. Pesan uji harus muncul (kode 0). Kode 3 berarti `.env` belum disiapkan;
   kode 4 berarti pengiriman gagal.

Setiap pesan diakhiri "BUKAN SARAN INVESTASI." `laporan.html` dilampirkan bila ukurannya ≤
`notifikasi.telegram.maks_lampiran_mb`. Untuk mematikan pengiriman, setel `notifikasi.telegram.aktif: false`. Token
tidak pernah tercetak di log, layar, laporan, atau pesan (diganti `***`).

---

## 6. Penjadwalan otomatis

Klik ganda **`scripts\daftar_jadwal.bat`**. Skrip ini membuat (atau menimpa) tugas Task Scheduler
**"Asisten BEI Turun Harian"**, terpisah dari tugas "Asisten BEI Harian" milik asisten-bei:

- Senin–Jumat pada `jadwal.jam_run` (default **20:00 WIB**, setelah asisten-bei pukul 19:30, agar kedua alat tidak
  mengunduh dari Yahoo bersamaan). Jam ini dikonversi ke jam lokal Windows dan dicetak.
- Bila PC mati atau tidur pada jam itu, tugas dijalankan **susulan** saat PC menyala, dan laporan tetap memakai
  tanggal data yang benar. Tugas hanya berjalan saat Anda login; kata sandi tidak disimpan.
- Keluaran setiap run terjadwal tercatat di `output\log\terjadwal.log`. Jangan tutup jendela hitam yang muncul.

**Opsional — bangunkan PC:** buka *Task Scheduler* → klik kanan **Asisten BEI Turun Harian** → *Properties* → tab
**Conditions** → centang **"Wake the computer to run this task"** → OK. Menjalankan `daftar_jadwal.bat` lagi menimpa
tugas itu, sehingga pengaturan manual ini perlu diulang.

Mode terjadwal (`harian --jadwal`): bila tanggal data itu sudah tercatat `LENGKAP`, program keluar dengan "tidak ada
data baru". Kegagalan (kode 1, 2, 3, 5, 6) dikabarkan lewat Telegram.

---

## 7. Rutinitas harian

| Kapan | Yang dilakukan |
|---|---|
| Malam (setelah laporan ± 20:00) | Baca ringkasan aksi kedua alat. Saat IHSG tren turun, rekomendasi beli datang dari alat ini; saat pasar naik, dari asisten-bei. |
| Pagi `t+1`, sebelum pra-pembukaan | Pasang order **BELI limit di harga_maks** sesuai laporan. Pasang order JUAL untuk saran "JUAL di pembukaan" dengan cara yang membuat order terisi di harga pembukaan. |
| Segera setelah pembukaan | Cek setiap order beli. Tidak terisi → **tarik**. Terisi sebagian → tarik sisanya. Terisi → **pasang order otomatis stop (dan target untuk TP) hari itu juga**. Bila harga isi ≤ stop → jual segera. |
| Setelah ada transaksi | Perbarui `input\portfolio.csv` dan `input\akun.yaml` **milik alat yang memberi rekomendasi** (contoh di bawah). |
| Setiap sore, posisi TB | Perbarui level order otomatis stop (trailing) sesuai laporan. |

**Contoh dengan angka fiktif:**

- **Beli terisi:** 1 lot `AAAA` di 2.010, strategi TP, stop 1.888.
  - Tambah baris di `portfolio.csv` alat ini: `AAAA,2026-10-16,2010,1,TP,1888,,,,`
  - Kurangi kas di `akun.yaml` alat ini sebesar 2.010 × 100 × 1,0015 = **201.301,50**, lalu ubah `diperbarui`.
  - Target = 2.010 + 2 × (2.010 − 1.888) = **2.254**.
- **Jual 1 lot di 2.254:**
  - Hapus baris dari `portfolio.csv`.
  - Tambah kas sebesar 225.400 × (1 − 0,0025) = **224.836,50**.

Bila broker membulatkan fee berbeda, pakai angka dari trade confirmation. Kedua alat berbagi satu rekening broker,
tetapi masing-masing hanya melihat kas dan posisi di berkasnya sendiri: pastikan jumlah kas kedua `akun.yaml` tidak
melebihi kas rekening Anda.

Saran per posisi di laporan: **TAHAN**, **JUAL di pembukaan**, **CEK ORDER** (order otomatis seharusnya sudah terisi
hari ini), **INFO** (posisi `MANUAL`), atau **TIDAK DAPAT DIEVALUASI**. Status pasar yang kembali naik (JANGAN BELI)
tidak memaksa penjualan: posisi keluar menurut aturan strateginya masing-masing.

---

## 8. Perintah dan berkas .bat

| Berkas | Perintah | Fungsi |
|---|---|---|
| `pasang.bat` | — | Membuat `.venv` dan memasang dependensi |
| `cek.bat` | `cek [--silang KODE TANGGAL]` | Validasi config + semua input (hanya membaca) |
| `unduh.bat` | `unduh [--penuh] [--simbol K1,K2]` | Memperbarui cache harga |
| `backtest.bat` | `backtest [--strategi tp,tb,pj,acak] [--mode edge,realistis]` | Backtest dan gerbang |
| `harian.bat` | `harian [--offline] [--tanggal D] [--tanpa-notifikasi] [--catat] [--catat-ulang]` | Laporan harian (+ Telegram) |
| `harian_terjadwal.bat` | `harian --jadwal` | Dipanggil Task Scheduler |
| `jurnal.bat` | `jurnal [--ekspor] [--rekonsiliasi]` | Ringkasan jurnal kertas (paper trading), ekspor CSV, rekonsiliasi |
| `uji_telegram.bat` | `uji-telegram [--cari-chat-id]` | Pesan uji / mencari chat ID |
| `uji.bat` | `pytest -q` | Semua uji otomatis |
| `daftar_jadwal.bat` | — | Mendaftarkan tugas Task Scheduler |

Opsi bisa ditambahkan lewat Command Prompt di folder proyek, mis. `scripts\harian.bat --tanggal 2026-10-15`. Laporan
harian ada di `output\laporan\<tanggal>\`; log ada di `output\log\`.

---

## 9. Kode keluar dan masalah umum

| Kode | Arti |
|---|---|
| 0 | OK, termasuk "tidak ada data baru" dan `cek` yang hanya berisi peringatan |
| 1 | Error tak terduga (rincian di `output\log\`), atau pemeriksaan akuntansi backtest gagal |
| 2 | Data belum tersedia, atau tidak lengkap karena IHSG; backtest tanpa data |
| 3 | Config atau berkas input tidak valid (jalankan `cek.bat`); untuk `uji-telegram`: `.env` belum disiapkan |
| 4 | Laporan dibuat, tetapi notifikasi Telegram gagal; juga pesan uji `uji-telegram` yang gagal terkirim |
| 5 | Proses lain sedang berjalan |
| 6 | Jurnal gagal (terkunci/rusak); laporan tetap dibuat dan dikirim |

Bila beberapa kondisi terjadi bersamaan, kode yang dipakai mengikuti prioritas 3 > 1 > 5 > 2 > 6 > 4 > 0.

| Situasi | Yang terjadi / yang Anda lakukan |
|---|---|
| Laporan selalu JANGAN BELI | Wajar saat pasar tidak sedang turun: alat ini hanya aktif saat IHSG tren turun atau breadth lemah. Pakai asisten-bei. |
| Semua strategi `BAYANGAN_GERBANG` | Jalankan `backtest.bat`. Bila tetap tidak lolos (mis. transaksi holdout < 30), strategi itu memang belum terbukti; sinyalnya tetap tercatat di jurnal kertas. |
| Internet putus, Yahoo membatasi | Data hari itu belum tersedia → kode 2, tanpa rekomendasi. Coba lagi nanti. |
| "mungkin hari libur yang belum ada di holidays.csv" | Tambahkan tanggal libur itu ke `input\holidays.csv` di kedua alat. |
| `jurnal.sqlite` terkunci | Tutup aplikasi yang membukanya; jangan letakkan proyek di OneDrive/Dropbox. |
| Run terjadwal tidak menghasilkan laporan | Baca `output\log\terjadwal.log`; bila `.venv` rusak, jalankan `pasang.bat` lagi. |

---

## 10. Uji cepat dengan data nyata

Setelah instalasi dan setiap upgrade dependensi (SPEC §22.3):

1. `cek.bat` → tidak ada ERROR. Setiap item "BELUM DIVERIFIKASI" sudah Anda putuskan.
2. `unduh.bat` → periksa `output\kualitas\<waktu>_unduh.csv`. Jumlah simbol OK mendekati total.
3. **Cek silang:** jalankan `scripts\cek.bat --silang KODE TANGGAL` untuk 3 saham tanpa split, lalu bandingkan dengan
   ringkasan perdagangan resmi. Bila satuan volume sudah diverifikasi di asisten-bei, hasilnya harus sama.
4. `backtest.bat` → ringkasan terbuka. ACAK tidak tampak menguntungkan. Perhatikan jumlah hari dan transaksi pada
   periode tren turun.
5. **Hitung tangan** satu transaksi dari `transaksi_tp_edge.csv` (harga entry = min(open hari berikutnya × 1,001,
   harga_maks)).
6. `harian.bat` → baca laporan dan hitung ulang sizing satu kandidat dengan kalkulator (rumus SPEC §14.1).
7. `uji_telegram.bat` → pesan diterima.
8. Daftarkan jadwal. Pada hari bursa berikutnya ± 20:00, laporan dan pesan Telegram harus muncul.

Sebelum memakai uang sungguhan (anjuran, tidak ditegakkan program): jalankan jurnal kertas **minimal 3 bulan atau
30 transaksi tertutup** (mana yang lebih lama). Karena alat ini hanya aktif saat pasar turun, masa ini bisa lebih
lama daripada di asisten-bei.

---

## 11. Glosarium

| Istilah | Penjelasan singkat |
|---|---|
| R | Kerugian yang direncanakan bila stop tersentuh. +2R berarti untung dua kali risiko awal; −1R berarti rugi sebesar rencana. |
| ATR | Rata-rata rentang gerak harian saham. Dipakai untuk menentukan jarak stop. |
| SMA20/50/200 | Rata-rata harga penutupan 20/50/200 hari bursa terakhir. |
| RSI(2) | Indikator jenuh jual/beli jangka sangat pendek (0–100). Nilai di bawah 10 berarti sangat jenuh jual. |
| Breadth | Persentase saham dalam daftar breadth yang harganya di atas SMA50. Menggambarkan seberapa luas pasar naik. |
| Drawdown | Penurunan dari nilai puncak ekuitas ke titik terendah setelahnya. |
| CAGR | Pertumbuhan tahunan rata-rata yang dimajemukkan. |
| Win rate | Persentase transaksi yang untung setelah fee. |
| Profit factor (PF) | Total untung ÷ total rugi. Di atas 1 berarti untung bersih. PF_R menghitungnya dalam satuan R. |
| Ekspektansi | Rata-rata hasil per transaksi, dalam Rupiah atau R. |
| In-sample / holdout | Periode yang dipakai untuk menilai aturan, dan periode terakhir yang disimpan untuk pengujian akhir. |
| Slippage | Selisih antara harga yang diharapkan dan harga eksekusi sebenarnya. |
| Fraksi harga | Kelipatan harga yang diizinkan bursa. Nilainya Anda isi sendiri dari aturan resmi. |
| ARA/ARB | Batas atas/bawah perubahan harga harian. Nilainya Anda isi sendiri dari aturan resmi. |
| Gerbang | Syarat backtest yang harus dipenuhi sebelum strategi boleh menghasilkan rekomendasi beli. |
| Bayangan | Sinyal yang dicatat untuk evaluasi tetapi tidak direkomendasikan (strategi belum lolos gerbang atau pasar JANGAN BELI). |
| Jurnal kertas | Simulasi transaksi tanpa uang sungguhan (paper trading), memakai aturan yang sama dengan backtest. |
| Stop waktu | Jual bila posisi belum keluar setelah N hari bursa. |
| Trailing stop | Stop yang naik mengikuti harga dan tidak pernah turun. |
| Unggul IHSG | Seberapa jauh perubahan harga saham lebih baik daripada IHSG dalam periode yang sama. +10% berarti saham 10% lebih kuat daripada IHSG. |
| Jenuh jual | Harga turun tajam beberapa hari berturut-turut (RSI(2) sangat rendah). PJ membeli dengan harapan ada pantulan singkat; pantulan itu tidak dijamin. |

---

> **BUKAN SARAN INVESTASI.** Laporan ini dibuat otomatis oleh program pribadi berdasarkan aturan mekanis dan data
> publik yang bisa salah, terlambat, atau tidak lengkap. Hasil backtest dan paper trading tidak menjamin hasil di
> masa depan. Seluruh keputusan dan risiko transaksi menjadi tanggung jawab pengguna.
