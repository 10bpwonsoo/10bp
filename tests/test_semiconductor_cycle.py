"""반도체 사이클 탭 (2026-10-23) — 엔진 · 수출 나우캐스트 · MARKET READ 검증 · history · archive · API."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from marketpulse.ai import semi_read
from marketpulse.engines.semiconductor_cycle import (build_semiconductor_cycle, classify_news, export_nowcast, load_config, load_exports, momentum_score,
                                                     window_ref, Obs)

PKG = Path(__file__).resolve().parent.parent / "marketpulse"
CAP = PKG / "data" / "captures" / "2026-10-23-backfill"
AS_OF = datetime(2026, 10, 22, 22, 30, tzinfo=timezone.utc)
SPOT_FIELDS = ["updated_at", "close", "change_pct", "high", "low", "item", "collected_at", "source"]
CON_FIELDS = ["updated_at", "avg", "high", "low", "avg_change_pct", "item", "collected_at", "source"]


def _write(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


@pytest.fixture
def data(tmp_path):
    """DDR4 16Gb 현물 30일 · 계약가 1행 · DDR5 현물 · NAND 현물(계약 없음)."""
    d = tmp_path / "semi"
    t0 = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
    _write(d / "spot" / "DDR4_16G_SPOT.csv", SPOT_FIELDS, [{"updated_at": (t0 + timedelta(days=i)).isoformat(), "close": 60 + i, "item": "DDR4"} for i in range(31)])
    _write(d / "spot" / "DDR5_16G_SPOT.csv", SPOT_FIELDS, [{"updated_at": (t0 + timedelta(days=i)).isoformat(), "close": 50 + 0.2 * i} for i in range(31)])
    _write(d / "spot" / "NAND_512G_TLC_WAFER.csv", SPOT_FIELDS, [{"updated_at": (t0 + timedelta(days=7 * i)).isoformat(), "close": 20 - 0.3 * i} for i in range(5)])
    _write(d / "contract" / "DDR4_16G_CONTRACT.csv", CON_FIELDS, [{"updated_at": "2026-09-30T18:00:00+08:00", "avg": 50, "avg_change_pct": 4.0, "item": "DDR4 16Gb 2Gx8"}])
    _write(d / "contract" / "DDR5_8GB_SODIMM_CONTRACT.csv", CON_FIELDS, [{"updated_at": "2026-09-30T18:00:00+08:00", "avg": 160, "avg_change_pct": 2.0, "item": "DDR5 8GB SO-DIMM"}])
    (d / "exports.json").write_text(json.dumps({"releases": [], "working_days": {}}), encoding="utf-8")
    return d


def _build(data, as_of=AS_OF, **kw):
    return build_semiconductor_cycle(as_of=as_of, data_dir=data, replay_dir=data / "none", **kw)


class TestPremium:
    def test_spot_premium_formula_and_anchor(self, data):
        out = _build(data)
        p = next(x for x in out["spot_premium"] if x["spot"] == "DDR4_16G_SPOT")
        assert p["available"] and p["comparability"] == "HIGH" and not p["proxy"]
        assert p["current"] == pytest.approx((90 / 50 - 1) * 100, abs=0.01)  # 마지막 현물 90 / 계약 50
        assert p["contract_anchor"] == "2026-09-30" and p["contract_anchor_label"] == "Sep-2026"
        assert p["state"] == "STRONG_PREMIUM"

    def test_premium_uses_only_contract_published_before_each_spot(self, data):
        out = _build(data)
        s = next(x for x in out["spot_premium"] if x["spot"] == "DDR4_16G_SPOT")["series"]
        assert all(r["anchor"] <= r["t"][:10] for r in s)
        assert s[0]["t"][:10] >= "2026-09-30"  # 계약가 공개 전 현물은 premium 을 만들지 않는다

    def test_low_comparability_is_proxy_with_low_weight(self, data):
        p = next(x for x in _build(data)["spot_premium"] if x["spot"] == "DDR5_16G_SPOT")
        assert p["proxy"] and p["comparability"] == "LOW" and p["weight"] < 1
        assert p["contract_equiv"] == pytest.approx(40.0)  # 모듈 160 ÷ 4칩

    def test_no_comparable_contract_is_not_computed(self, data):
        p = next(x for x in _build(data)["spot_premium"] if x["spot"] == "NAND_512G_TLC_WAFER")
        assert p["available"] is False and "current" not in p

    def test_zscore_needs_min_observations(self, data):
        p = next(x for x in _build(data)["spot_premium"] if x["spot"] == "DDR4_16G_SPOT")
        assert p["observations"] >= 20 and p["zscore"] is not None
        q = next(x for x in _build(data, as_of=datetime(2026, 10, 10, tzinfo=timezone.utc))["spot_premium"] if x["spot"] == "DDR4_16G_SPOT")
        assert q["observations"] < 20 and q["zscore"] is None and q["percentile_1y"] is None


class TestMissingAndPit:
    def test_missing_product_is_none_not_zero(self, data):
        out = _build(data)
        p = next(x for x in out["memory_prices"] if x["id"] == "DDR4_8G_SPOT")
        assert p["available"] is False and p["current"] is None and p["momentum"] is None

    def test_future_rows_are_cut(self, data):
        early = datetime(2026, 9, 25, 0, 0, tzinfo=timezone.utc)
        out = _build(data, as_of=early)
        p = next(x for x in out["memory_prices"] if x["id"] == "DDR4_16G_SPOT")
        assert p["observations"] == 3 and p["current"] == 62
        assert all(not x.get("available") for x in out["spot_premium"])  # 9/30 계약가는 아직 공개 전

    def test_eps_is_no_data(self, data):
        out = _build(data)
        assert next(c for c in out["regime"]["components"] if c["key"] == "eps_revision")["score"] is None
        assert next(c for c in out["regime"]["chips"] if c["key"] == "eps")["value"] == "NO DATA"


class TestMomentum:
    def test_window_needs_reference_inside_tolerance(self):
        t = datetime(2026, 10, 1, tzinfo=timezone.utc)
        obs = [Obs(t - timedelta(days=20), 1.0, {}), Obs(t, 2.0, {})]
        assert window_ref(obs, 7, 3) is None and window_ref(obs, 30, 7) is None

    def test_since_first_only_when_no_window(self):
        s, basis = momentum_score({"since_first": 7.5, "since_first_days": 10}, load_config()["momentum"])
        assert basis == "SINCE_FIRST" and s == pytest.approx(50.0)
        s, basis = momentum_score({"1W": 5.0, "since_first": -50, "since_first_days": 10}, load_config()["momentum"])
        assert basis == "WINDOWS" and s == 100.0

    def test_breadth_needs_min_products(self, data, tmp_path):
        out = _build(data)
        assert out["breadth"]["state"] in ("BROAD", "SELECTIVE", "NARROW", "WEAK")
        one = tmp_path / "one"
        (one / "spot").mkdir(parents=True)
        (one / "spot" / "DDR4_16G_SPOT.csv").write_text((data / "spot" / "DDR4_16G_SPOT.csv").read_text())
        (one / "exports.json").write_text('{"releases": []}')
        assert _build(one)["breadth"]["state"] == "NO DATA"

    def test_insufficient_evidence_does_not_pick_a_regime(self, tmp_path):
        d = tmp_path / "empty"; d.mkdir()
        out = build_semiconductor_cycle(as_of=AS_OF, data_dir=d, replay_dir=d)
        assert out["regime"]["state"] in ("NO DATA", "INSUFFICIENT_DATA")


class TestExportNowcast:
    def test_october_nowcast_from_published_releases(self):
        cfg = load_config()
        ex = export_nowcast(load_exports(AS_OF), AS_OF, cfg, memory_state=20.0)
        assert ex["latest_scope"] == "1-20" and ex["month"] == "2026-10"
        n = ex["nowcast"]
        assert n["low"] <= n["mid"] <= n["high"]
        assert n["mid"] == pytest.approx(552.7, abs=0.5)
        assert ex["latest_daily_avg_yoy"] == pytest.approx(160.5, abs=0.1)  # 조업일 차이를 걷어낸 YoY
        assert ex["revision_pp"] is not None and ex["previous"]["basis"].startswith("1~10일")
        assert [p["label"] for p in ex["progress"]] == ["1~10D", "1~20D", "Full Month Nowcast", "Actual"]
        assert ex["progress"][-1]["available"] is False  # 확정치는 아직 없다
        assert "정성" in ex["price_vs_volume"]

    def test_releases_after_as_of_are_not_used(self):
        t = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
        ex = export_nowcast(load_exports(t), t, load_config(), memory_state=None)
        assert ex["latest_scope"] == "1-10" and ex["revision_pp"] is None


class TestNews:
    def test_keyword_category_and_sector_fallback(self):
        cfg = load_config()
        ev = [{"id": "a", "event": "SK하이닉스, HBM4 증설", "themes": ["semiconductor"], "sentiment": 30, "impact_score": 50, "timestamp": "2026-10-22T01:00:00Z"},
              {"id": "b", "event": "코스피 급락…삼전닉스 하락", "themes": ["semiconductor"], "sentiment": -40, "impact_score": 70, "timestamp": "2026-10-22T02:00:00Z"},
              {"id": "c", "event": "유가 급등", "themes": ["oil"], "sentiment": -10, "impact_score": 90, "timestamp": "2026-10-22T03:00:00Z"}]
        out = classify_news(ev, cfg)
        assert [n["id"] for n in out] == ["a", "b"]  # 업황 분류가 시장 반응(SECTOR)보다 먼저 · 무관 기사 제외
        assert "HBM" in out[0]["categories"] and "CAPACITY" in out[0]["categories"]
        assert out[1]["category"] == "SECTOR" and out[0]["why"] and out[0]["transmission"]


class TestMarketRead:
    @pytest.fixture
    def cyc(self, data):
        return _build(data)

    def test_rule_fallback_without_llm(self, cyc):
        mr = cyc["market_read"]
        assert mr["source"] == "rule" and mr["read"] == mr["rule_read"] and mr["read"]
        for w in ("확률", "매수", "매도", "전망"):
            assert w not in mr["read"]

    def test_validator_rejects_invented_numbers_and_forbidden_words(self, cyc):
        ctx = semi_read.build_context(cyc); cfg = load_config()["read"]
        bad = semi_read.normalize_output({"read": "DDR4 현물은 계약가보다 12345% 높다. 매수 확률이 높다.", "themes": ["premium"], "data_caveat": ""})
        problems = semi_read.check_output(bad, ctx, cfg)
        assert any("컨텍스트에 없는 숫자" in p for p in problems) and any("확률" in p or "매수" in p for p in problems)

    def test_session_read_must_pass_same_validation(self, data):
        bad = {"read": "한 문장뿐이다.", "themes": ["premium"], "data_caveat": ""}
        mr = _build(data, session_read=bad)["market_read"]
        assert mr["source"] == "rule" and any("세션 생성본 검증 실패" in w for w in mr["warnings"])

    def test_disabled_client_falls_back(self, data):
        class Off:
            enabled = False
        assert _build(data, client=Off())["market_read"]["source"] == "rule"

    def test_session_read_for_1023_capture_passes(self):
        doc = json.loads((CAP / "semiconductor_cycle.json").read_text(encoding="utf-8"))
        assert doc["market_read"]["generator"] == "session" and doc["market_read"]["status"] == "ok"


class TestHistory:
    def test_past_snapshot_is_locked_and_not_recomputed(self, data, tmp_path):
        from marketpulse.history import DailySnapshotManager, JsonDirStore
        from marketpulse.history.semi import TAB, sync_semiconductor
        m = DailySnapshotManager(JsonDirStore(tmp_path / "h"))
        cyc = _build(data)
        h = sync_semiconductor(m, cyc, series_by_id={}, as_of=AS_OF)
        assert h.points and h.points[-1].date.isoformat() == "2026-10-22"
        first = m.get_snapshot(TAB, h.points[-1].date)
        assert first.is_locked  # 07:30 KST 저장 = 그 UTC 날짜 마감 후 → RECORDED · LOCKED
        later = dict(cyc); later["regime"] = {**cyc["regime"], "state": "DEEP_DOWNTURN", "composite": -90.0}
        sync_semiconductor(m, later, series_by_id={}, as_of=AS_OF + timedelta(hours=1))
        assert m.get_snapshot(TAB, h.points[-1].date).state == first.state


class TestArchive:
    def test_section_registered(self):
        from marketpulse.archive.collect import CAPTURE_FILES
        from marketpulse.archive.service import load_archive_config
        assert CAPTURE_FILES["semiconductor_cycle"] == "semiconductor_cycle.json"
        assert "semiconductor_cycle" in load_archive_config()["sections"]

    def test_existing_archives_are_untouched(self):
        """탭이 생기기 전 저장본에는 섹션이 없다 — 현재 값으로 메우지 않는다(화면은 NOT ARCHIVED)."""
        for f in sorted((PKG / "data" / "archive" / "2026" / "10").glob("2026-10-*.json")):
            assert "semiconductor_cycle" not in json.loads(f.read_text(encoding="utf-8")), f.name

    def test_capture_section_has_all_api_keys(self):
        doc = json.loads((CAP / "semiconductor_cycle.json").read_text(encoding="utf-8"))
        for k in API_KEYS:
            assert k in doc, k
        assert doc["as_of"].startswith("2026-10-22T22:30")


API_KEYS = ["regime", "market_read", "memory_prices", "spot_premium", "momentum", "breadth", "normalized", "dram_map", "nand_map", "memory_history",
            "spot_to_contract", "hbm_supply", "export_nowcast", "price_to_export", "fundamental_confirmation", "equity_confirmation", "stock_impact",
            "news", "what_matters_next", "data_quality"]


class TestApi:
    def test_endpoint_returns_sections(self, tmp_path):
        from fastapi.testclient import TestClient
        from marketpulse.api.deps import get_history_service, get_service
        from marketpulse.api.main import create_app
        from marketpulse.api.semi_service import get_semiconductor_cycle_service
        from marketpulse.history import DailySnapshotManager, JsonDirStore
        get_service().clear(); get_semiconductor_cycle_service().clear()
        get_history_service().use(DailySnapshotManager(JsonDirStore(tmp_path / "h")))
        try:
            r = TestClient(create_app()).get("/api/v1/semiconductor-cycle")
            assert r.status_code == 200
            d = r.json()
            for k in API_KEYS:
                assert k in d, k
            assert d["market_read"]["status"] == "skipped"  # MOCK 은 AI 해석을 만들지 않는다 — 정량 화면은 그대로
        finally:
            get_history_service().clear(); get_semiconductor_cycle_service().clear()
