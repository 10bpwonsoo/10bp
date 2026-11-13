"""메모리 가격 공개 출처 — DRAMeXchange 홈 표·Silicon Analysts HBM 앵커 파서, 봉 1개 계열의 취급."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from marketpulse.adapters.alternative.live import AltLiveAdapter
from marketpulse.adapters.alternative.memory_sources import hbm_rows, parse_dramexchange_home, period_to_date
from marketpulse.config.registry import get_universe
from marketpulse.engines.alternative_data import build_alt_points
from marketpulse.engines.features import compute_feature
from marketpulse.models.common import DataQuality
from marketpulse.storage.sqlite_repo import SqliteSnapshotRepository

HOME = """
<html><body>
<div>DRAM Spot Price Last Update: Sep.29 2026 11:00 (GMT+8)</div>
<table>
<tr><th>Item</th><th>Daily High</th><th>Daily Low</th><th>Session High</th><th>Session Low</th><th>Session Average</th><th>Session Change</th><th>History</th></tr>
<tr><td>DDR5 16Gb (2Gx8) 4800/5600</td><td>69.50</td><td>43.50</td><td>69.50</td><td>43.50</td><td>57.833</td><td>0.00 %</td><td><a>chart</a></td></tr>
<tr><td>DDR4 8Gb (1Gx8) 3200</td><td>85.00</td><td>25.00</td><td>85.00</td><td>25.00</td><td>46.321</td><td>0.23 %</td><td></td></tr>
<tr><td>DDR4 8Gb (1Gx8) eTT</td><td>6.35</td><td>5.70</td><td>6.35</td><td>5.70</td><td>5.900</td><td>0.51 %</td><td></td></tr>
</table>
<div>Module Spot Price Last Update:Sep.28 2026 14:40 (GMT+8)</div>
<div>NAND Flash Spot Price Last Update: Sep.21 2026 13:00 (GMT+8)</div>
<table>
<tr><td>512Gb TLC</td><td>22.00</td><td>17.50</td><td>22.00</td><td>17.50</td><td>19.883</td><td>-1.00 %</td><td></td></tr>
<tr><td>256Gb TLC</td><td>20.00</td><td>16.00</td><td>20.00</td><td>16.00</td><td>17.885</td><td>6.41 %</td><td></td></tr>
</table>
<div>DXI</div><div>Sep.28, 18:00 (GMT+8)</div><div>1105299.00</div><div>5262.87 (0.48 %)</div>
</body></html>
"""


class TestDramExchangeParser:
    def test_reads_session_average_not_high_or_low(self):
        got = parse_dramexchange_home(HOME)
        assert got["DRAM_SPOT"]["value"] == pytest.approx(46.321) and got["DRAM_SPOT"]["change_pct"] == pytest.approx(0.23)
        assert got["DDR5_SPOT"]["value"] == pytest.approx(57.833)
        assert got["NAND_SPOT"]["value"] == pytest.approx(19.883) and got["NAND_SPOT"]["change_pct"] == pytest.approx(-1.0)
        assert got["DRAM_SPOT"]["session_date"] == date(2026, 9, 29)
        assert got["NAND_SPOT"]["session_date"] == date(2026, 9, 21)  # NAND 표는 주간 갱신 — 자기 시각을 쓴다
        assert got["DXI"]["value"] == pytest.approx(1105299.0) and got["DXI"]["change_pct"] == pytest.approx(0.48)
        assert got["DXI"]["session_date"] == date(2026, 9, 28)

    def test_missing_row_is_absent_not_zero(self):
        got = parse_dramexchange_home(HOME.replace("512Gb TLC", "1Tb TLC"))
        assert "NAND_SPOT" not in got and "DRAM_SPOT" in got

    def test_live_page_fixture_if_present(self):
        p = Path("/tmp/claude-0/-home-user-10bp/d1217ff9-9e47-595a-ade2-530a334c6aba/scratchpad/dramx.html")
        if not p.exists():
            pytest.skip("실제 페이지 사본 없음")
        got = parse_dramexchange_home(p.read_text(encoding="utf-8", errors="ignore"))
        assert set(got) >= {"DRAM_SPOT", "DDR5_SPOT", "NAND_SPOT", "DXI"}


class TestSiliconAnalystsHbm:
    def test_period_to_date_rules(self):
        assert period_to_date("Q1 2026", None) == date(2026, 3, 31)
        assert period_to_date("H2 2025", None) == date(2025, 12, 31)
        assert period_to_date("Nov 2025", None) == date(2025, 11, 30)
        assert period_to_date("Agreed Nov 2025, SK Hynix (CY2026 supply)", "Nov 5, 2025") == date(2025, 11, 5)
        assert period_to_date("2026 (≈+20% renewals)", "Jul 2026") == date(2026, 7, 28)
        assert period_to_date("2025", "carried seed") is None  # 날짜를 못 정하면 None — 짐작하지 않는다

    def test_hbm_rows_pick_series_and_keep_provenance(self):
        pts = [
            {"period_label": "H1 2025", "value_mid": 15.0, "value_low": 14, "value_high": 16, "series_key": "hbm3e-contract", "data_type": "Estimate", "confidence": "Medium", "source_name": "seed", "source_date": "carried seed"},
            {"period_label": "Q4 2025 (x)", "value_mid": 9.72, "series_key": "hbm3e-contract-stack", "source_date": "Nov 27, 2025"},
            {"period_label": "Agreed Nov 2025", "value_mid": 15.56, "series_key": "hbm4-contract", "data_type": "Estimate", "confidence": "Medium", "source_name": "서울경제", "source_date": "Nov 5, 2025"},
            {"period_label": "Nope", "value_mid": 1.0, "series_key": "hbm4-contract", "source_date": "whenever"},
        ]
        r3 = hbm_rows(pts, ["hbm3e-contract"])
        assert [(r["date"], r["close"]) for r in r3] == [("2025-06-30", 15.0)] and r3[0]["confidence"] == "Medium"
        r4 = hbm_rows(pts, ["hbm4-contract"])
        assert [(r["date"], r["close"], r["source"]) for r in r4] == [("2025-11-05", 15.56, "서울경제")]


class TestSingleBarSeries:
    def _csv(self, path: Path, rows: list[tuple[str, float]]) -> None:
        path.write_text("date,close,change_pct,source\n" + "".join(f"{d},{v},0.1,test\n" for d, v in rows), encoding="utf-8")

    def test_min_points_one_accepts_a_single_row_and_engine_says_why_z_is_missing(self, tmp_path):
        as_of = datetime(2026, 9, 29, 1, tzinfo=timezone.utc)
        (tmp_path / "alternative").mkdir()
        self._csv(tmp_path / "alternative" / "DRAM_SPOT.csv", [("2026-09-29", 46.321)])
        self._csv(tmp_path / "alternative" / "HBM3E_CONTRACT.csv", [("2025-06-30", 15.0), ("2025-12-31", 13.0), ("2026-07-28", 15.6)])
        uni = get_universe()
        alts = [x for x in uni.alternative if x.id in ("DRAM_SPOT", "HBM3E_CONTRACT")]
        assert all(a.min_points == 1 for a in alts) and next(a for a in alts if a.id == "HBM3E_CONTRACT").frequency == "quarterly"
        adapter = AltLiveAdapter(replay_dir=tmp_path, store=SqliteSnapshotRepository(":memory:"))
        adapter.politeness_sec = 0
        out = adapter.fetch_series([a.as_instrument() for a in alts], {a.id: a.sources for a in alts}, bars=100, as_of=as_of)
        assert set(out) == {"DRAM_SPOT", "HBM3E_CONTRACT"} and out["DRAM_SPOT"].meta.quality is DataQuality.OK
        ins_by_id = {a.id: a.as_instrument() for a in alts}
        feats = {k: compute_feature(ins_by_id[k], v, window=60) for k, v in out.items()}
        pts = {p.id: p for p in build_alt_points(alts, feats, out, {x.id: x for x in uni.stocks}, as_of)}
        d = pts["DRAM_SPOT"]
        assert d.quality == "PARTIAL" and d.value == pytest.approx(46.321) and d.z is None and d.observations == 1
        assert "봉 1/20" in d.note and "z 는 20봉이 차면" in d.note
        h = pts["HBM3E_CONTRACT"]
        assert h.frequency == "quarterly" and h.z is None and h.percentile is None and h.value == pytest.approx(15.6)
        assert "분기 추정치" in h.note and h.change_1d is not None  # 직전 발표 대비 변화는 있다

    def test_common_minimum_still_applies_to_daily_instruments(self, tmp_path):
        as_of = datetime(2026, 9, 29, 1, tzinfo=timezone.utc)
        (tmp_path / "alternative").mkdir()
        self._csv(tmp_path / "alternative" / "SUGAR.csv", [("2026-09-29", 18.5)])
        uni = get_universe()
        a = next(x for x in uni.alternative if x.id == "SUGAR")
        assert a.min_points is None
        adapter = AltLiveAdapter(replay_dir=tmp_path, store=None)
        adapter.politeness_sec = 0
        out = adapter.fetch_series([a.as_instrument()], {a.id: [s for s in a.sources if s.provider == "csv"]}, bars=100, as_of=as_of)
        assert "SUGAR" not in out
        assert any("최소 20개" in why for _, why in adapter.outcomes["SUGAR"].attempts)
