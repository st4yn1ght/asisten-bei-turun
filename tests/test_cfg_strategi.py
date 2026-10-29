"""T-CFG bagian strategi & skor (SPEC §22.1, §7, §12, §13.1, P4): setiap kunci benar-benar berpengaruh.

Untuk setiap kunci di `strategi.tp.*`, `strategi.tb.*`, `strategi.pj.*`, `strategi.acak.*`, `skor.*`, dan
`entry.gap_maks_atr`, uji berparameter mengubah nilainya dan memastikan keluaran fixture berubah DI TEMPAT
YANG SPEC TETAPKAN (mis. `strategi.tp.sma_panjang` mengubah pola lolos TP1; `penyangga_stop_atr` mengubah
stop dan tidak menyentuh harga_maks atau pola lolos TP1–TP5). Kunci yang hanya dipakai mesin exit (§15)
tidak dinilai di sini: `tp.stop_waktu_hari`, `tb.trailing_atr`, `tb.stop_waktu_hari`, `pj.sma_keluar`,
`pj.min_hari_tahan`, `pj.stop_waktu_hari`, `acak.stop_waktu_hari`. Penjaga cakupan memastikan setiap kunci
lain di model config punya kasus, sehingga kunci baru tidak lolos tanpa uji.

Keluaran yang dibandingkan TIDAK memuat teks uraian cek (yang ikut menyebut angka config, mis. "SMA150"),
melainkan "aspek" keputusan:

- `cek:<KODE>`  — status lolos aturan (TP1..TP6, TB1..TB6, PJ1..PJ3, ACAK, STOP, DATA);
- `sinyal`      — ada/tidaknya sinyal;
- `sinyal.<f>`  — field Sinyal bila sinyal ada di kedua sisi (harga_maks, stop, valid, target_r, …);
- `skor.<k>`    — komponen skor (k_sinyal, k_rs, k_likuid, k_stop, skor) untuk sinyal saham eligible;
- `daftar`      — strategi aktif dari `daftar_strategi`.

Dengan begitu kunci yang hanya muncul di label tetapi tidak dipakai dalam perhitungan tetap ketahuan.

Fixture: 8 saham sintetis berseed (random walk dengan rezim tren naik/turun bergantian, lonjakan volume
acak), 460 hari bursa (kalender Senin–Jumat `bantu_pasar.KAL`), dievaluasi pada setiap hari bursa kedua
HARI[256..458] (102 tanggal × 8 saham per strategi), ditambah IHSG sintetis (rata-rata return 8 saham dengan
drift turun) untuk TP6/TB6/PJ2. Semua kunci yang dinilai disematkan eksplisit ke nilai default SPEC §7 di config dasar,
sehingga uji tidak bergantung pada isi config rilis. Harga dibulatkan ke rupiah bulat
(`pasar.fraksi_harga.terverifikasi: false`; tidak ada tabel fraksi BEI di uji ini).
"""

from __future__ import annotations

import copy
import dataclasses
import math
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from asisten_bei_turun import skor as modul_skor
from asisten_bei_turun.aturan_bei import AturanBEI
from asisten_bei_turun.config import BobotSkor, Config, Skor, StrategiAcak, StrategiTB, StrategiPJ, StrategiTP
from asisten_bei_turun.data.tampilan import DataPasar
from asisten_bei_turun.strategi.dasar import daftar_strategi, hitung_sinyal
from asisten_bei_turun.universe import AturanUniverse, kode_eligible, nilai_eligibilitas
from bantu_pasar import HARI, KAL, bar, cfg_uji, data_saham

SEED = 20261017
N_BAR = 460
POS_EVALUASI = range(256, N_BAR, 2)  # sesudah min_bar_riwayat 250 → semua saham eligible
KODE = [f"CF{i:02d}" for i in range(8)]
AKHIR = HARI[N_BAR - 1].date()

# Nilai default SPEC §7 untuk setiap kunci yang dinilai (disematkan; tidak bergantung config rilis).
DASAR_STRATEGI = {
    "strategi.tp.aktif": True,
    "strategi.tp.sma_cepat": 20,
    "strategi.tp.sma_tren": 50,
    "strategi.tp.sma_panjang": 200,
    "strategi.tp.lookback_slope_sma_tren": 10,
    "strategi.tp.lookback_sentuh_sma_cepat": 4,
    "strategi.tp.maks_jarak_atas_sma_cepat_atr": 1.0,
    "strategi.tp.lookback_swing_low": 5,
    "strategi.tp.penyangga_stop_atr": 0.2,
    "strategi.tp.maks_jarak_stop_atr": 3.0,
    "strategi.tp.target_r": 2.0,
    "strategi.tp.rs_lookback": 60,
    "strategi.tp.min_unggul_ihsg_pct": 10.0,
    "strategi.tb.aktif": True,
    "strategi.tb.lookback_tertinggi": 20,
    "strategi.tb.lookback_volume": 20,
    "strategi.tb.min_rasio_volume": 1.5,
    "strategi.tb.min_posisi_close": 0.6,
    "strategi.tb.maks_lewat_level_atr": 1.0,
    "strategi.tb.sma_tren": 50,
    "strategi.tb.sma_panjang": 200,
    "strategi.tb.stop_atr": 2.0,
    "strategi.tb.rs_lookback": 60,
    "strategi.tb.min_unggul_ihsg_pct": 10.0,
    "strategi.pj.aktif": True,
    "strategi.pj.rsi_periode": 2,
    "strategi.pj.rsi_maks": 5,
    "strategi.pj.ihsg_rsi_maks": 20,
    "strategi.pj.maks_turun_harian_atr": 3.0,
    "strategi.pj.stop_atr": 2.5,
    "strategi.pj.sma_keluar": 5,
    "strategi.acak.peluang_sinyal_pct": 2.0,
    "strategi.acak.seed": 12345,
    "strategi.acak.stop_atr": 2.0,
    "strategi.acak.target_r": 2.0,
    "skor.bobot": {"sinyal": 40, "kekuatan_relatif": 30, "likuiditas": 15, "jarak_stop": 15},
    "skor.rs_lookback": 60,
    "skor.jarak_stop_ideal_pct": 3.0,
    "skor.jarak_stop_buruk_pct": 10.0,
    "entry.gap_maks_atr": 0.5,
}
DASAR_LAIN = {
    "indikator.atr_periode": 14,
    "likuiditas.periode_hari": 20,
    "likuiditas.nilai_transaksi_min_idr": 500_000_000,  # RataNilai fixture ±2 miliar → K_likuid ±0,6
    "likuiditas.maks_hari_volume_nol": 0,
    "universe.min_bar_riwayat": 250,
    "data.pengali_volume": 1,
    "data.validasi.lonjakan_mencurigakan_pct": 40,
    "kondisi_pasar.sma_pendek": 50,
    "kondisi_pasar.sma_panjang": 200,
    "kondisi_pasar.breadth_sma": 50,
    "pasar.fraksi_harga.terverifikasi": False,
}


def cfg_dasar(ubah: dict | None = None) -> Config:
    # deepcopy: `cfg_uji` menulis ke simpul dict yang diberikan (mis. "skor.bobot" lalu "skor.bobot.sinyal").
    return cfg_uji(copy.deepcopy({**DASAR_LAIN, **DASAR_STRATEGI, **(ubah or {})}))


# ---------------------------------------------------------------------------
# Fixture pasar sintetis (deterministik)
# ---------------------------------------------------------------------------


def _buat_saham(i: int) -> pd.DataFrame:
    rng = np.random.default_rng(SEED + i)
    # Rezim 40 bar: naik kuat / naik pelan / turun, urutan acak berseed → tren, pullback, dan breakout.
    drift = np.repeat(rng.choice([0.004, 0.0015, -0.003], size=N_BAR // 40 + 1, p=[0.4, 0.35, 0.25]), 40)[:N_BAR]
    log_r = drift + rng.normal(0.0, 0.016, N_BAR)
    close = (800.0 + 150.0 * i) * np.exp(np.cumsum(log_r))
    buka = np.concatenate([[close[0]], close[:-1]]) * np.exp(rng.normal(0.0, 0.006, N_BAR))
    high = np.maximum(buka, close) * (1.0 + np.abs(rng.normal(0.0, 0.009, N_BAR)))
    low = np.minimum(buka, close) * (1.0 - np.abs(rng.normal(0.0, 0.009, N_BAR)))
    volume = 2_000_000.0 * np.exp(rng.normal(0.0, 0.35, N_BAR))
    lonjak = rng.random(N_BAR) < 0.07
    volume[lonjak] *= rng.uniform(1.8, 4.0, int(lonjak.sum()))
    df = pd.DataFrame(
        {"open": buka, "high": high, "low": low, "close": close, "volume": np.round(volume)},
        index=pd.DatetimeIndex(HARI[:N_BAR], name="tanggal").as_unit("ns"),
    )
    df["sumber"] = "yfinance"
    return df


MENTAH = {k: _buat_saham(i) for i, k in enumerate(KODE)}


def _buat_ihsg() -> pd.DataFrame:
    """IHSG sintetis: rata-rata return log 8 saham dengan drift turun 0,1%/hari, sehingga saham yang kuat bisa unggul
    ≥ 10% (TP6/TB6) dan RSI(2) IHSG kerap rendah bersamaan dengan saham yang jatuh (PJ2)."""
    log_c = np.log(np.array([MENTAH[k]["close"].to_numpy() for k in KODE]))
    log_r = np.mean(np.diff(log_c, axis=1, prepend=log_c[:, :1]), axis=0)
    return bar(list(7000.0 * np.exp(np.cumsum(log_r - 0.001))), indeks=True)


IHSG_MENTAH = _buat_ihsg()
ATURAN = AturanUniverse(
    konteks="backtest", kandidat=tuple(KODE), anggota_pada=lambda k, d: True,
    exclude_pada=lambda k, d: None, sektor=lambda k: "S" + k,
)


def bangun_pasar(cfg: Config) -> DataPasar:
    ihsg = data_saham("IHSG", IHSG_MENTAH, cfg, AKHIR, indeks=True)
    return DataPasar({k: data_saham(k, df, cfg, AKHIR) for k, df in MENTAH.items()}, ihsg, KAL, cfg)


# ---------------------------------------------------------------------------
# Keluaran sebagai aspek
# ---------------------------------------------------------------------------

FIELD_SINYAL = ("harga_ref", "harga_maks", "stop", "atr", "faktor_split", "k_sinyal", "target_r", "rata_nilai",
                "fraksi_dipakai", "valid", "alasan_tidak_valid")
KOMPONEN_SKOR = ("k_sinyal", "k_rs", "k_likuid", "k_stop", "skor")


@dataclasses.dataclass
class Keluaran:
    daftar: list[str]  # kode strategi dari daftar_strategi(cfg) (run harian)
    cek: dict[tuple, dict[str, bool]]  # (tanggal, kode, strategi) → {kode aturan: lolos}
    sinyal: dict[tuple, object]  # (tanggal, kode, strategi) → Sinyal | None
    eligible: dict[date, list[str]]
    sinyal_eligible: dict[date, list]  # hitung_sinyal atas saham eligible (masukan skor)
    skor: dict[tuple, modul_skor.KomponenSkor]  # (tanggal, kode, strategi) → komponen


def jalankan(cfg: Config, strategi: set[str] | None = None, *, dengan_skor: bool = False,
             sinyal_dari: Keluaran | None = None) -> Keluaran:
    """Evaluasi `strategi` (None = TP, TB, PJ, ACAK) atas semua saham pada setiap tanggal uji; dengan
    `dengan_skor`, juga eligibilitas → `hitung_sinyal` → `skor.beri_skor`. `sinyal_dari`: pakai ulang
    eligibilitas & sinyal run lain dan hanya hitung ulang skor dengan `cfg` (kunci skor tidak dibaca
    strategi). Pasar selalu dibangun ulang dengan `cfg` (indikator mengikuti periode config)."""
    pasar = bangun_pasar(cfg)
    dipakai = [s for s in daftar_strategi(cfg, termasuk_acak=True) if strategi is None or s.kode in strategi]
    bei = AturanBEI(cfg)
    hasil = Keluaran([s.kode for s in daftar_strategi(cfg)], {}, {}, {}, {}, {})
    for p in POS_EVALUASI:
        d = HARI[p].date()
        dv = pasar.tampilan(d)
        if sinyal_dari is None:
            for k in KODE:
                for st in dipakai:
                    ev = st.evaluasi(dv, k, bei)
                    hasil.cek[(d, k, st.kode)] = {c.kode: c.lolos for c in ev.cek}
                    hasil.sinyal[(d, k, st.kode)] = ev.sinyal
            if not dengan_skor:
                continue
            eligible = kode_eligible(nilai_eligibilitas(dv, ATURAN))
            sinyal = hitung_sinyal(dv, eligible, dipakai, bei)
        else:
            eligible, sinyal = sinyal_dari.eligible[d], sinyal_dari.sinyal_eligible[d]
        hasil.eligible[d], hasil.sinyal_eligible[d] = eligible, sinyal
        for x in modul_skor.beri_skor(dv, sinyal, eligible):
            hasil.skor[(d, x.kode, x.strategi)] = x.komponen
    return hasil


def _beda(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return False
    return a != b


def aspek_berubah(a: Keluaran, b: Keluaran) -> set[str]:
    """Aspek keluaran yang berbeda antara dua run (hanya kunci yang ada di kedua run dibandingkan)."""
    hasil: set[str] = set()
    if a.daftar != b.daftar:
        hasil.add("daftar")
    for kunci in a.cek.keys() & b.cek.keys():
        ca, cb = a.cek[kunci], b.cek[kunci]
        hasil.update(f"cek:{k}" for k in ca.keys() | cb.keys() if ca.get(k) != cb.get(k))
    for kunci in a.sinyal.keys() & b.sinyal.keys():
        sa, sb = a.sinyal[kunci], b.sinyal[kunci]
        if (sa is None) != (sb is None):
            hasil.add("sinyal")
        elif sa is not None:
            hasil.update(f"sinyal.{f}" for f in FIELD_SINYAL if _beda(getattr(sa, f), getattr(sb, f)))
    if a.skor and b.skor:
        for kunci in a.skor.keys() & b.skor.keys():
            ka, kb = a.skor[kunci], b.skor[kunci]
            hasil.update(f"skor.{k}" for k in KOMPONEN_SKOR if _beda(getattr(ka, k), getattr(kb, k)))
        if a.skor.keys() != b.skor.keys():
            hasil.add("skor:himpunan")
    return hasil


@lru_cache(maxsize=1)
def keluaran_dasar() -> Keluaran:
    return jalankan(cfg_dasar(), dengan_skor=True)


def dasar_untuk(strategi: str) -> Keluaran:
    """Bagian run dasar milik satu strategi (tanpa skor)."""
    d = keluaran_dasar()

    def pilih(xs: dict) -> dict:
        return {k: v for k, v in xs.items() if k[2] == strategi}

    return Keluaran(d.daftar, pilih(d.cek), pilih(d.sinyal), {}, {}, {})


# ---------------------------------------------------------------------------
# Kunci strategi: aspek yang wajib berubah dan (bila relevan) satu-satunya yang boleh berubah
# ---------------------------------------------------------------------------

_STOP = {"sinyal.stop", "sinyal.valid", "sinyal.alasan_tidak_valid", "sinyal.fraksi_dipakai", "sinyal", "cek:STOP"}


@dataclasses.dataclass(frozen=True)
class Kasus:
    kunci: str
    nilai: object
    strategi: str
    harus: frozenset[str]  # aspek yang WAJIB berubah
    cek_boleh: frozenset[str] | None = None  # aturan yang boleh berubah status lolosnya (None = bebas)
    hanya: frozenset[str] | None = None  # bila diisi: aspek yang berubah wajib subset ini

    @property
    def id(self) -> str:
        return f"{self.kunci}={self.nilai}"


def K(kunci, nilai, strategi, harus, cek_boleh=None, hanya=None) -> Kasus:
    cek = None if cek_boleh is None else frozenset({*cek_boleh, "STOP"})
    return Kasus(kunci, nilai, strategi, frozenset(harus), cek, None if hanya is None else frozenset(hanya))


KASUS_STRATEGI = [
    # TP (§12.1)
    K("strategi.tp.sma_cepat", 15, "TP", {"cek:TP3", "cek:TP5", "sinyal.k_sinyal"}, {"TP3", "TP5"}),
    K("strategi.tp.sma_tren", 40, "TP", {"cek:TP1", "cek:TP2"}, {"TP1", "TP2"}),
    K("strategi.tp.sma_panjang", 150, "TP", {"cek:TP1"}, {"TP1"}),
    K("strategi.tp.lookback_slope_sma_tren", 3, "TP", {"cek:TP2"}, {"TP2"}),
    K("strategi.tp.lookback_sentuh_sma_cepat", 1, "TP", {"cek:TP3"}, {"TP3"}),
    K("strategi.tp.maks_jarak_atas_sma_cepat_atr", 0.5, "TP", {"cek:TP5"}, {"TP5"}),
    K("strategi.tp.lookback_swing_low", 10, "TP", {"sinyal.stop"}, set(), _STOP),
    K("strategi.tp.penyangga_stop_atr", 0.6, "TP", {"sinyal.stop"}, set(), _STOP),
    K("strategi.tp.maks_jarak_stop_atr", 2.0, "TP", {"sinyal.valid"}, set(),
      {"sinyal.valid", "sinyal.alasan_tidak_valid"}),
    K("strategi.tp.target_r", 3.0, "TP", {"sinyal.target_r"}, set(), {"sinyal.target_r"}),
    K("strategi.tp.rs_lookback", 20, "TP", {"cek:TP6"}, {"TP6"}),
    K("strategi.tp.min_unggul_ihsg_pct", 25.0, "TP", {"cek:TP6"}, {"TP6"}),
    # TB (§12.2)
    K("strategi.tb.lookback_tertinggi", 10, "TB", {"cek:TB1"}, {"TB1", "TB5"}),
    K("strategi.tb.lookback_volume", 5, "TB", {"cek:TB2", "sinyal.k_sinyal"}, {"TB2"}),
    K("strategi.tb.min_rasio_volume", 1.2, "TB", {"cek:TB2", "sinyal.k_sinyal"}, {"TB2"}),
    K("strategi.tb.min_posisi_close", 0.4, "TB", {"cek:TB4"}, {"TB4"}),
    K("strategi.tb.maks_lewat_level_atr", 0.3, "TB", {"cek:TB5"}, {"TB5"}),
    K("strategi.tb.sma_tren", 30, "TB", {"cek:TB3"}, {"TB3"}),
    K("strategi.tb.sma_panjang", 100, "TB", {"cek:TB3"}, {"TB3"}),
    K("strategi.tb.stop_atr", 1.0, "TB", {"sinyal.stop"}, set(), _STOP),
    K("strategi.tb.rs_lookback", 20, "TB", {"cek:TB6"}, {"TB6"}),
    K("strategi.tb.min_unggul_ihsg_pct", 25.0, "TB", {"cek:TB6"}, {"TB6"}),
    # PJ (§12.3)
    K("strategi.pj.rsi_periode", 3, "PJ", {"cek:PJ1", "cek:PJ2"}, {"PJ1", "PJ2"}),  # juga RSI IHSG
    K("strategi.pj.rsi_maks", 25, "PJ", {"cek:PJ1", "sinyal.k_sinyal"}, {"PJ1"}),
    K("strategi.pj.ihsg_rsi_maks", 40, "PJ", {"cek:PJ2"}, {"PJ2"}),
    K("strategi.pj.maks_turun_harian_atr", 0.5, "PJ", {"cek:PJ3"}, {"PJ3"}),
    K("strategi.pj.stop_atr", 1.5, "PJ", {"sinyal.stop"}, set(), _STOP),
    # ACAK (§12.4)
    K("strategi.acak.peluang_sinyal_pct", 10.0, "ACAK", {"cek:ACAK", "sinyal"}, {"ACAK"}),
    K("strategi.acak.seed", 54321, "ACAK", {"cek:ACAK", "sinyal"}, {"ACAK"}),
    K("strategi.acak.stop_atr", 1.0, "ACAK", {"sinyal.stop"}, set(), _STOP),
    K("strategi.acak.target_r", 3.0, "ACAK", {"sinyal.target_r"}, set(), {"sinyal.target_r"}),
]


def _nilai_dasar(kunci: str):
    simpul = cfg_dasar()
    for bagian in kunci.split("."):
        simpul = getattr(simpul, bagian)
    return simpul


def test_fixture_dasar_tidak_hampa():
    """Setiap strategi menghasilkan cukup sinyal (termasuk STOP_TERLALU_JAUH) dan semua saham eligible,
    sehingga perubahan level/skor bisa teramati."""
    d = keluaran_dasar()
    jumlah = {s: sum(1 for k, v in d.sinyal.items() if k[2] == s and v is not None) for s in ("TP", "TB", "PJ", "ACAK")}
    assert jumlah["TP"] >= 15 and jumlah["TB"] >= 5 and jumlah["PJ"] >= 20 and jumlah["ACAK"] >= 5, jumlah
    assert any(not v.valid for v in d.sinyal.values() if v is not None)
    assert all(len(v) == len(KODE) for v in d.eligible.values())
    assert len(d.skor) >= 50
    assert d.daftar == ["TP", "TB", "PJ"]


@pytest.mark.parametrize("kasus", KASUS_STRATEGI, ids=lambda k: k.id)
def test_kunci_strategi_mengubah_keluaran_di_tempat_yang_benar(kasus: Kasus):
    assert _nilai_dasar(kasus.kunci) != kasus.nilai  # nilai uji memang berbeda dari dasar
    dasar = dasar_untuk(kasus.strategi)
    ubah = jalankan(cfg_dasar({kasus.kunci: kasus.nilai}), {kasus.strategi})
    assert ubah.cek.keys() == dasar.cek.keys()
    berubah = aspek_berubah(dasar, ubah)
    assert kasus.harus <= berubah, f"{kasus.id}: tidak berpengaruh pada {sorted(kasus.harus - berubah)} (P4)"
    if kasus.cek_boleh is not None:
        cek_berubah = {a.removeprefix("cek:") for a in berubah if a.startswith("cek:")}
        assert cek_berubah <= kasus.cek_boleh, f"{kasus.id}: aturan lain ikut berubah {sorted(cek_berubah)}"
    if kasus.hanya is not None:
        assert berubah <= kasus.hanya, f"{kasus.id}: aspek tak terduga {sorted(berubah - kasus.hanya)}"


@pytest.mark.parametrize("kunci", ["strategi.tp.target_r", "strategi.acak.target_r"])
def test_target_r_diteruskan_ke_sinyal(kunci):
    """target_r 2,0 → 3,0: setiap sinyal strategi itu membawa 3,0; level harga tidak berubah."""
    strategi = kunci.split(".")[1].upper()
    ubah = jalankan(cfg_dasar({kunci: 3.0}), {strategi})
    sinyal = [s for s in ubah.sinyal.values() if s is not None]
    assert sinyal and all(s.target_r == 3.0 for s in sinyal)
    assert all(s.target_r == 2.0 for s in dasar_untuk(strategi).sinyal.values() if s is not None)


@pytest.mark.parametrize("kunci, kode", [("strategi.tp.aktif", "TP"), ("strategi.tb.aktif", "TB"),
                                         ("strategi.pj.aktif", "PJ")])
def test_kunci_aktif_mengeluarkan_strategi_dari_daftar_dan_sinyal(kunci, kode):
    cfg = cfg_dasar({kunci: False})
    assert [s.kode for s in daftar_strategi(cfg)] == [k for k in ("TP", "TB", "PJ") if k != kode]
    assert kode not in [s.kode for s in daftar_strategi(cfg, termasuk_acak=True)]
    dasar = keluaran_dasar()
    tanggal = sorted({k[0] for k, v in dasar.sinyal.items() if v is not None and k[2] == kode})
    assert tanggal  # dasar memang punya sinyal strategi ini
    pasar_ubah, pasar_dasar = bangun_pasar(cfg), bangun_pasar(cfg_dasar())
    for d in tanggal:
        baru = hitung_sinyal(pasar_ubah.tampilan(d), KODE, daftar_strategi(cfg))
        lama = hitung_sinyal(pasar_dasar.tampilan(d), KODE, daftar_strategi(cfg_dasar()))
        assert all(s.strategi != kode for s in baru)
        assert baru == [s for s in lama if s.strategi != kode]  # strategi lain tidak terpengaruh


# ---------------------------------------------------------------------------
# entry.gap_maks_atr
# ---------------------------------------------------------------------------


def test_gap_maks_atr_mengubah_harga_maks_dan_k_stop():
    """harga_maks = bulat_bawah(close + gap × ATR) (§4.1, rupiah bulat); stop, harga_ref, ATR tetap."""
    ubah = jalankan(cfg_dasar({"entry.gap_maks_atr": 0.2}), dengan_skor=True)
    dasar = keluaran_dasar()
    berubah = aspek_berubah(dasar, ubah)
    assert {"sinyal.harga_maks", "skor.k_stop", "skor.skor"} <= berubah, berubah
    assert not berubah & {"sinyal.stop", "sinyal.harga_ref", "sinyal.atr", "sinyal.k_sinyal", "skor.k_rs"}
    assert not any(a.startswith("cek:") and a != "cek:STOP" for a in berubah)
    n = 0
    for kunci, s in ubah.sinyal.items():
        lama = dasar.sinyal[kunci]
        if s is None or lama is None:
            continue
        n += 1
        # F(t) = 1 (tanpa split); harga_ref & atr adalah close & ATR (6 desimal).
        for sinyal, gap in ((s, Decimal("0.2")), (lama, Decimal("0.5"))):
            assert sinyal.harga_maks == (sinyal.harga_ref + gap * sinyal.atr).to_integral_value(ROUND_FLOOR)
        assert s.harga_maks < lama.harga_maks or s.atr * Decimal("0.3") < 1
    assert n >= 50


# ---------------------------------------------------------------------------
# skor.* (§13.1)
# ---------------------------------------------------------------------------

# Setiap bobot dinaikkan 10 dan pasangannya diturunkan 10 (jumlah tetap 100).
PASANGAN_BOBOT = [
    ("sinyal", "jarak_stop"),
    ("kekuatan_relatif", "likuiditas"),
    ("likuiditas", "sinyal"),
    ("jarak_stop", "kekuatan_relatif"),
]
_KOMPONEN_BOBOT = {"sinyal": "k_sinyal", "kekuatan_relatif": "k_rs", "likuiditas": "k_likuid", "jarak_stop": "k_stop"}


@pytest.mark.parametrize("naik, turun", PASANGAN_BOBOT, ids=[f"skor.bobot.{a}" for a, _ in PASANGAN_BOBOT])
def test_bobot_skor_berpengaruh_sesuai_rumus(naik, turun):
    """Δskor = 10 × (K_naik − K_turun) untuk setiap sinyal; komponen K tidak berubah. Bila bobot `naik`
    diabaikan kode, Δskor menjadi −10 × K_turun dan uji gagal (K_naik > 0 pada sinyal fixture)."""
    bobot = dict(DASAR_STRATEGI["skor.bobot"])
    bobot[naik] += 10
    bobot[turun] -= 10
    dasar = keluaran_dasar()
    ubah = jalankan(cfg_dasar({"skor.bobot": bobot}), sinyal_dari=dasar)
    assert aspek_berubah(dasar, ubah) == {"skor.skor"}
    k_naik, k_turun = _KOMPONEN_BOBOT[naik], _KOMPONEN_BOBOT[turun]
    beda_nol = 0
    for kunci, lama in dasar.skor.items():
        baru = ubah.skor[kunci]
        harapan = 10.0 * (getattr(lama, k_naik) - getattr(lama, k_turun))
        assert baru.skor - lama.skor == pytest.approx(harapan, abs=1e-9), kunci
        beda_nol += harapan != 0
    assert beda_nol >= 0.5 * len(dasar.skor)
    assert sum(1 for x in dasar.skor.values() if getattr(x, k_naik) > 0) >= 0.5 * len(dasar.skor)


def _k_rs_tangan(d: date, n: int) -> dict[str, float]:
    """K_rs dihitung tangan dari bar mentah: Ret(n) = close_t / close_{t−n} − 1 (semua bar valid),
    peringkat 1 = terendah, K_rs = (peringkat − 1)/(8 − 1)."""
    ret = {}
    for k, df in MENTAH.items():
        c = df["close"][df.index <= pd.Timestamp(d)]
        ret[k] = c.iloc[-1] / c.iloc[-1 - n] - 1
    urut = sorted(ret, key=ret.get)
    return {k: i / (len(urut) - 1) for i, k in enumerate(urut)}


def test_rs_lookback_mengubah_k_rs_sesuai_hitung_tangan():
    dasar = keluaran_dasar()
    ubah = jalankan(cfg_dasar({"skor.rs_lookback": 20}), sinyal_dari=dasar)
    berubah = aspek_berubah(dasar, ubah)
    assert "skor.k_rs" in berubah and berubah <= {"skor.k_rs", "skor.skor"}, berubah
    tanggal = sorted({k[0] for k in dasar.skor})
    peringkat_beda = 0
    for d in tanggal:
        t20, t60 = _k_rs_tangan(d, 20), _k_rs_tangan(d, 60)
        peringkat_beda += t20 != t60
        for (dd, kode, st), komp in ubah.skor.items():
            if dd == d:
                assert komp.k_rs == pytest.approx(t20[kode], abs=1e-12), (d, kode)
                assert dasar.skor[(dd, kode, st)].k_rs == pytest.approx(t60[kode], abs=1e-12), (d, kode)
    assert peringkat_beda >= 0.5 * len(tanggal)


@pytest.mark.parametrize("kunci, nilai", [("skor.jarak_stop_ideal_pct", 5.0), ("skor.jarak_stop_buruk_pct", 6.0)])
def test_jarak_stop_ideal_dan_buruk_mengubah_k_stop_sesuai_rumus(kunci, nilai):
    """K_stop = clip((buruk − jarak%)/(buruk − ideal), 0, 1), jarak% = (harga_maks − stop)/harga_maks × 100.
    Jarak stop sinyal fixture sebagian besar di antara ideal 3 dan buruk 10; yang di luarnya terpotong (clip) pada
    dasar. ideal 5 → sinyal berjarak ≤ 5% terpotong ke 1; buruk 6 → sinyal berjarak ≥ 6% terpotong ke 0, sehingga
    kedua sisi clip ikut teruji, bersama nilai di tengah rentang."""
    dasar = keluaran_dasar()
    ubah = jalankan(cfg_dasar({kunci: nilai}), sinyal_dari=dasar)
    berubah = aspek_berubah(dasar, ubah)
    assert "skor.k_stop" in berubah and berubah <= {"skor.k_stop", "skor.skor"}, berubah
    ideal = nilai if kunci.endswith("ideal_pct") else 3.0
    buruk = nilai if kunci.endswith("buruk_pct") else 10.0
    sinyal = {(d, s.kode, s.strategi): s for d, xs in dasar.sinyal_eligible.items() for s in xs}
    k_stop = []
    for kunci_s, komp in ubah.skor.items():
        jarak = sinyal[kunci_s].jarak_stop_pct
        harapan = min(max((buruk - jarak) / (buruk - ideal), 0.0), 1.0)
        assert komp.k_stop == pytest.approx(harapan, abs=1e-12), (kunci_s, jarak)
        dasar_harapan = min(max((10.0 - jarak) / 7.0, 0.0), 1.0)
        assert dasar.skor[kunci_s].k_stop == pytest.approx(dasar_harapan, abs=1e-12)
        k_stop.append(komp.k_stop)
    terpotong = 1.0 if kunci.endswith("ideal_pct") else 0.0
    assert k_stop.count(terpotong) >= 3, sorted(k_stop)
    assert sum(1 for k in k_stop if 0.0 < k < 1.0) >= 3, sorted(k_stop)


# ---------------------------------------------------------------------------
# Penjaga cakupan: setiap kunci strategi/skor punya kasus (kecuali kunci khusus exit)
# ---------------------------------------------------------------------------

KHUSUS_EXIT = {
    "strategi.tp.stop_waktu_hari",
    "strategi.tb.trailing_atr",
    "strategi.tb.stop_waktu_hari",
    "strategi.pj.sma_keluar",
    "strategi.pj.min_hari_tahan",
    "strategi.pj.stop_waktu_hari",
    "strategi.acak.stop_waktu_hari",
}


def _kunci_model() -> set[str]:
    kunci = set()
    for nama, model in (("tp", StrategiTP), ("tb", StrategiTB), ("pj", StrategiPJ), ("acak", StrategiAcak)):
        kunci |= {f"strategi.{nama}.{f}" for f in model.model_fields}
    kunci |= {f"skor.bobot.{f}" for f in BobotSkor.model_fields}
    kunci |= {f"skor.{f}" for f in Skor.model_fields if f != "bobot"}
    return kunci | {"entry.gap_maks_atr"}


def test_setiap_kunci_strategi_dan_skor_punya_kasus_t_cfg():
    model = _kunci_model()
    assert KHUSUS_EXIT <= model  # daftar pengecualian tidak usang
    tercakup = {k.kunci for k in KASUS_STRATEGI}
    tercakup |= {"strategi.tp.aktif", "strategi.tb.aktif", "strategi.pj.aktif", "entry.gap_maks_atr",
                 "skor.rs_lookback", "skor.jarak_stop_ideal_pct", "skor.jarak_stop_buruk_pct"}
    tercakup |= {f"skor.bobot.{a}" for a, _ in PASANGAN_BOBOT}
    assert tercakup == model - KHUSUS_EXIT, (sorted(model - KHUSUS_EXIT - tercakup), sorted(tercakup - model))
