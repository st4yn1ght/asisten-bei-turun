"""PJ — Pantulan jenuh jual (SPEC §12.3; `K_sinyal` PJ §13.1).

Syarat sinyal pada close `t` (= `dv.as_of`); semua aturan selalu dievaluasi dan dicantumkan, juga
sesudah satu aturan gagal, dengan nilai aktual di uraiannya. Angka default ada di `strategi.pj` (P4):

| # | Aturan (kunci `strategi.pj.*`) |
|---|---|
| PJ1 | `RSI(rsi_periode)_t < rsi_maks` (saham jenuh jual) |
| PJ2 | `RSI(rsi_periode)` IHSG pada `t` `< ihsg_rsi_maks` (penurunan terjadi di seluruh pasar) |
| PJ3 | `close_{t−1} − close_t ≤ maks_turun_harian_atr × ATR_t` (bukan jatuh ekstrem dalam sehari) |

`close_{t−1}` = close bar valid sebelumnya (`dv.sebelum(kode, "close", 1)`, §4.1), bukan hari kalender
sebelumnya. PJ3 adalah batas penurunan dalam satuan ATR (setara `(close_{t−1} − close_t)/ATR_t ≤ batas`),
sehingga ATR ≤ 0 atau NaN membuatnya tidak terpenuhi (§9). IHSG tanpa bar pada `t` membuat PJ2 tidak
terpenuhi. Nilai NaN (riwayat kurang) membuat aturan yang memakainya tidak terpenuhi. PJ tidak mensyaratkan
tren naik saham.

Stop awal (ruang tersesuaikan) = `close_t − stop_atr × ATR_t`; `harga_maks`, konversi nominal `× F(t)`,
dan pembulatan (harga_maks ke bawah, stop ke atas) dikerjakan `Strategi._bangun_sinyal`. Stop ≤ 0
(saham sangat volatil berharga rendah) tidak dapat dipakai → cek "STOP" gagal, tanpa sinyal. Tidak ada
target tetap (`target_r = None`).

`K_sinyal` PJ = `clip((rsi_maks − RSI)/rsi_maks, 0, 1)`.

Exit PJ (`sma_keluar`, `min_hari_tahan`, `stop_waktu_hari`) ditangani mesin exit (§15), bukan di sini.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..indikator import k_rsi
from .dasar import CekAturan, EvaluasiStrategi, Strategi, a, atr_sah, nilai_baris

if TYPE_CHECKING:  # pragma: no cover
    from ..aturan_bei import AturanBEI
    from ..data.tampilan import DataView


def _ada(*nilai: float) -> bool:
    """Semua nilai tersedia (bukan NaN)."""
    return not any(math.isnan(x) for x in nilai)


def _clip01(x: float) -> float:
    return min(max(x, 0.0), 1.0)


class Oversold(Strategi):
    """PJ — pantulan jenuh jual saat IHSG juga jenuh jual (SPEC §12.3)."""

    kode = "PJ"

    def evaluasi(self, dv: "DataView", kode: str, bei: "AturanBEI") -> EvaluasiStrategi:
        p = self.cfg.strategi.pj
        baris = dv.baris(kode)
        if baris is None:
            return self.tanpa_sinyal(
                kode, [CekAturan("DATA", f"tidak ada bar valid pada {dv.as_of.isoformat()}", False)]
            )

        n_rsi = p.rsi_periode
        rsi_maks = float(p.rsi_maks)
        ihsg_rsi_maks = float(p.ihsg_rsi_maks)
        maks_turun = float(p.maks_turun_harian_atr)
        close = nilai_baris(baris, "close")
        atr = nilai_baris(baris, "atr")
        rsi = nilai_baris(baris, k_rsi(n_rsi))
        rsi_ihsg = nilai_baris(dv.ihsg_baris(), k_rsi(n_rsi)) if dv.ihsg() is not None else math.nan
        close_kemarin = dv.sebelum(kode, "close", 1)

        cek: list[CekAturan] = []

        # PJ1 — saham jenuh jual: RSI di bawah batas.
        cek.append(
            CekAturan(
                "PJ1",
                f"RSI({n_rsi}) {a(rsi)} < {a(rsi_maks)}",
                _ada(rsi) and rsi < rsi_maks,
            )
        )

        # PJ2 — IHSG juga jenuh jual (penurunan di seluruh pasar).
        cek.append(
            CekAturan(
                "PJ2",
                f"RSI({n_rsi}) IHSG {a(rsi_ihsg)} < {a(ihsg_rsi_maks)}",
                _ada(rsi_ihsg) and rsi_ihsg < ihsg_rsi_maks,
            )
        )

        # PJ3 — penurunan hari ini bukan jatuh ekstrem (dalam satuan ATR).
        dasar_pj3 = f"close kemarin {a(close_kemarin)} − close {a(close)}"
        if not atr_sah(atr):
            cek.append(
                CekAturan(
                    "PJ3",
                    f"{dasar_pj3} ≤ {a(maks_turun)} × ATR {a(atr)}: ATR tidak sah (≤ 0 atau tidak tersedia)",
                    False,
                )
            )
        else:
            turun = close_kemarin - close
            batas = maks_turun * atr
            cek.append(
                CekAturan(
                    "PJ3",
                    f"{dasar_pj3} = {a(turun)} ≤ {a(maks_turun)} × ATR {a(atr)} = {a(batas)}",
                    _ada(turun) and turun <= batas,
                )
            )

        if not all(c.lolos for c in cek):
            return self.tanpa_sinyal(kode, cek)

        # Stop awal di ruang tersesuaikan; konversi nominal & pembulatan di `_bangun_sinyal`.
        stop_atr = float(p.stop_atr)
        stop_adj = close - stop_atr * atr
        if not stop_adj > 0:
            cek.append(
                CekAturan(
                    "STOP",
                    f"stop = close {a(close)} − {a(stop_atr)} × ATR {a(atr)} = {a(stop_adj)} "
                    "tidak dapat dipakai (≤ 0)",
                    False,
                )
            )
            return self.tanpa_sinyal(kode, cek)

        return self._bangun_sinyal(
            dv,
            kode,
            cek,
            close=close,
            atr=atr,
            stop_tersesuaikan=stop_adj,
            k_sinyal=_clip01((rsi_maks - rsi) / rsi_maks),
            target_r=None,
            rata_nilai=nilai_baris(baris, "rata_nilai"),
        )
