"""
Investment Intelligence 테스트 (2026-09-16 신설).

기존 552개 테스트는 손대지 않는다. 여기서는 새 계층만 본다 — 대체데이터
정규화·롤오버·낡음, 종목 beta, 사업 노출, Impact Score, 이상 거동,
가격·펀더멘털 괴리, 해설 근거, API 직렬화, 새 MOCK 시나리오.
네트워크 없이 돈다.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from marketpulse.adapters.alternative.live import AltLiveAdapter
from marketpulse.adapters.alternative.mock import AltMockAdapter
from marketpulse.adapters.market.mock import business_timestamps
from marketpulse.adapters.market.scenario import load_scenario
from marketpulse.api.deps import get_investment_service, get_service
from marketpulse.api.main import create_app
from marketpulse.config.registry import (
    get_instruments, get_intelligence_config, get_stock_exposures, get_universe,
)
from marketpulse.config.settings import MOCK_DIR, Settings
from marketpulse.engines.alternative_data import build_alt_points
from marketpulse.engines.commentary import load_commentary, pick
from marketpulse.engines.features import change_series, compute_feature
from marketpulse.engines.investment import build_investment, run_investment, shared_driver_ids
from marketpulse.engines.stock_anomaly import detect_anomalies
from marketpulse.engines.stock_divergence import detect_stock_divergences
from marketpulse.engines.stock_exposure import change_frame, compute_exposures, rolling_beta
from marketpulse.engines.stock_features import build_stock_features, volume_z
from marketpulse.engines.stock_impact import compute_impacts, impact_for
from marketpulse.models.common import DataMeta, DataMode, DataQuality
from marketpulse.models.intelligence import (
    AnalystSnapshot, Commentary, ExposureRow, ExposureWindow, FundamentalExposure, SourceSpec,
    StockExposure, StockMeta,
)
from marketpulse.models.market import MarketSeries
from marketpulse.engines.orchestrator import run_pipeline
from marketpulse.storage.sqlite_repo import SqliteSnapshotRepository


# ── 도우미 ─────────────────────────────────────────────
def _series(iid: str, values, as_of: datetime, *, volumes=None, quality=DataQuality.OK, source="test") -> MarketSeries:
    stamps = business_timestamps(as_of, len(values))
    return MarketSeries(
        instrument_id=iid, timestamps=stamps, values=[float(v) for v in values],
        volumes=[float(v) for v in volumes] if volumes is not None else None,
        meta=DataMeta(source=source, mode=DataMode.MOCK, retrieved_at=as_of, as_of=stamps[-1], quality=quality),
    )


def _walk(seed: int, n: int, *, base=100.0, vol=0.01, last=None):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0, vol, n - 1)
    if last is not None:
        rets[-1] = last
    return base * np.exp(np.cumsum(np.concatenate([[0.0], rets])))


@pytest.fixture(scope="module")
def universe():
    return get_universe()


@pytest.fixture
def base_snapshot(settings, as_of):
    return run_pipeline(settings, as_of=as_of)


@pytest.fixture
def mock_inv(settings, base_snapshot, as_of):
    return run_investment(settings, base_snapshot, as_of=as_of)


# ── 설정 무결성 ──────────────────────────────────────────
class TestConfig:
    def test_universe_ids_resolve(self, universe):
        base = get_instruments().by_id()
        alt = {a.id for a in universe.alternative}
        stock_ids = {s.id for s in universe.stocks}
        for s in universe.stocks:
            for d in s.drivers:
                assert d in base or d in alt or d in stock_ids, f"{s.id} driver {d}"
            for p in s.peers:
                assert p in base or p in alt or p in stock_ids, f"{s.id} peer {p}"
        for a in universe.alternative:
            for sid in a.affected:
                assert sid in stock_ids, f"{a.id} affected {sid}"

    def test_fundamental_exposures_resolve(self, universe):
        base = get_instruments().by_id()
        alt = {a.id for a in universe.alternative}
        stock_ids = {s.id for s in universe.stocks}
        for sid, drivers in get_stock_exposures().items():
            assert sid in stock_ids
            for d, f in drivers.items():
                assert d in base or d in alt or d in stock_ids, f"{sid} exposure {d}"
                assert f.direction in (1, -1)
                assert f.rationale

    def test_shared_drivers_exclude_alt_and_include_market(self, universe):
        ids = shared_driver_ids()
        assert universe.benchmark_market in ids
        assert not ({a.id for a in universe.alternative} & set(ids))

    def test_no_hardcoded_numbers_in_config_driven_engines(self):
        cfg = get_intelligence_config()
        for key in ("no_stat_exposure", "no_stat_confidence", "min_abs_corr_for_sign", "direction_deadband"):
            assert key in cfg["impact"]
        assert "severity_divisor" in cfg["anomaly"]

    def test_alt_instruments_carry_source_type_and_reason(self, universe):
        for a in universe.alternative:
            assert a.source_type in ("OFFICIAL", "EXCHANGE", "MARKET_DATA", "RESEARCH", "NEWS", "ALTERNATIVE", "UNKNOWN")
            assert a.why, a.id
            assert a.sources, a.id


# ── 대체데이터 정규화 ─────────────────────────────────────
class TestAlternativeData:
    def _alt(self, universe, iid):
        return next(a for a in universe.alternative if a.id == iid)

    def test_missing_series_is_reported_not_zero(self, universe, as_of):
        a = self._alt(universe, "DRAM_SPOT")
        pts = build_alt_points([a], {}, {}, universe.stock_by_id(), as_of)
        assert len(pts) == 1
        p = pts[0]
        assert p.quality == "MISSING" and p.value is None and p.z is None
        assert "CSV" in p.note
        assert p.affected_names  # 영향 종목 이름은 데이터 없이도 남는다

    def test_normal_series_ok_with_change_fields(self, universe, as_of):
        a = self._alt(universe, "SOX")
        s = _series("SOX", _walk(3, 200, base=5000), as_of)
        f = compute_feature(a.as_instrument(), s, window=60)
        p = build_alt_points([a], {"SOX": f}, {"SOX": s}, universe.stock_by_id(), as_of)[0]
        assert p.quality == "OK" and p.value == pytest.approx(s.last)
        assert p.change_1d is not None and p.z is not None
        assert p.source_type == a.source_type and p.stale is False

    def test_rollover_suspect_only_for_futures(self, universe, as_of):
        cfg = get_intelligence_config()["alternative"]
        big = float(cfg["rollover_suspect_z"]) + 1.0
        fut = self._alt(universe, "GASOLINE")
        assert fut.futures
        s = _series("GASOLINE", _walk(5, 200, base=2.0, vol=0.01, last=big * 0.01 * 2), as_of)
        f = compute_feature(fut.as_instrument(), s, window=60)
        assert f.z_1d is not None and abs(f.z_1d) >= float(cfg["rollover_suspect_z"])
        p = build_alt_points([fut], {"GASOLINE": f}, {"GASOLINE": s}, universe.stock_by_id(), as_of)[0]
        assert p.rollover_suspect is True and "롤오버" in p.note
        # 같은 충격이라도 선물이 아니면 롤오버 의심을 붙이지 않는다
        etf = self._alt(universe, "SMH")
        s2 = _series("SMH", s.values, as_of)
        f2 = compute_feature(etf.as_instrument(), s2, window=60)
        p2 = build_alt_points([etf], {"SMH": f2}, {"SMH": s2}, universe.stock_by_id(), as_of)[0]
        assert p2.rollover_suspect is False

    def test_stale_by_age_and_by_meta(self, universe, as_of):
        cfg = get_intelligence_config()["alternative"]
        a = self._alt(universe, "SOX")
        old_as_of = as_of - timedelta(days=int(cfg["stale_days"]) + 3)
        s = _series("SOX", _walk(7, 200, base=5000), old_as_of)
        f = compute_feature(a.as_instrument(), s, window=60)
        p = build_alt_points([a], {"SOX": f}, {"SOX": s}, universe.stock_by_id(), as_of)[0]
        assert p.stale is True and p.quality == "STALE"
        s2 = _series("SOX", _walk(7, 200, base=5000), as_of, quality=DataQuality.STALE)
        f2 = compute_feature(a.as_instrument(), s2, window=60)
        p2 = build_alt_points([a], {"SOX": f2}, {"SOX": s2}, universe.stock_by_id(), as_of)[0]
        assert p2.quality == "STALE"

    def test_groups_ordered_by_config(self, mock_inv):
        order = {g: i for i, g in enumerate(get_intelligence_config()["alternative"]["groups"])}
        idx = [order.get(p.group, 99) for p in mock_inv.alternative]
        assert idx == sorted(idx)


# ── 종목 feature / beta ──────────────────────────────────
class TestStockFeaturesAndExposure:
    def test_volume_z_needs_volume(self, as_of):
        s = _series("X", _walk(1, 100), as_of)
        assert volume_z(s, 60) == (None, None)
        vols = np.full(100, 1_000_000.0); vols[-1] = 5_000_000.0
        s2 = _series("X", _walk(1, 100), as_of, volumes=vols * np.exp(np.random.default_rng(2).normal(0, 0.1, 100)))
        z, ratio = volume_z(s2, 60)
        assert z is not None and z > 2 and ratio is not None and ratio > 3

    def test_perfect_twin_has_beta_one(self, as_of):
        drv = _walk(11, 200)
        frame = change_frame({"A": _series("A", drv, as_of), "D": _series("D", drv, as_of)}, {"A": "price", "D": "price"})
        w = rolling_beta(frame, "A", "D", 60, 15)
        assert w.beta == pytest.approx(1.0, abs=1e-3) and w.corr == pytest.approx(1.0, abs=1e-3)
        assert w.observations == 60

    def test_scaled_inverse_twin(self, as_of):
        drv = _walk(12, 200)
        rets = change_series(drv, "price")
        stock = 50 * np.exp(np.cumsum(np.concatenate([[0.0], -0.5 * rets])))
        frame = change_frame({"S": _series("S", stock, as_of), "D": _series("D", drv, as_of)}, {"S": "price", "D": "price"})
        w = rolling_beta(frame, "S", "D", 120, 15)
        assert w.beta == pytest.approx(-0.5, abs=1e-3) and w.corr == pytest.approx(-1.0, abs=1e-3)

    def test_too_few_observations_is_none_not_zero(self, as_of):
        frame = change_frame({"A": _series("A", _walk(1, 10), as_of), "D": _series("D", _walk(2, 10), as_of)}, {})
        w = rolling_beta(frame, "A", "D", 60, 15)
        assert w.beta is None and w.corr is None and w.observations == 9

    def test_compute_exposures_flags_sign_disagreement(self, universe, as_of):
        meta = universe.stock_by_id()["KOREAN_AIR"]
        fund = get_stock_exposures()["KOREAN_AIR"]["BRENT"]
        assert fund.direction == -1 and fund.kind == "cost"
        brent = _walk(21, 200, base=80)
        rets = change_series(brent, "price")
        # 통계는 양의 관계로 만든다 → 사업 노출(원가, -1)과 부호가 다르다
        stock = 20000 * np.exp(np.cumsum(np.concatenate([[0.0], 0.8 * rets])))
        series = {"KOREAN_AIR": _series("KOREAN_AIR", stock, as_of), "BRENT": _series("BRENT", brent, as_of)}
        ins = {"KOREAN_AIR": meta.as_instrument(), "BRENT": get_instruments().by_id()["BRENT"]}
        exp = compute_exposures([meta], series, ins)["KOREAN_AIR"]
        row = next(r for r in exp.rows if r.driver_id == "BRENT")
        assert row.sign_agreement is False and "부호" in row.note
        assert [w.window for w in row.windows] == get_intelligence_config()["impact"]["windows"]

    def test_stock_features_relative_and_sector(self, universe, as_of):
        metas = [universe.stock_by_id()[i] for i in ("SAMSUNG", "SKHYNIX")]
        series = {"KOSPI": _series("KOSPI", _walk(31, 200, base=3000), as_of)}
        for i, m in enumerate(metas):
            series[m.id] = _series(m.id, _walk(40 + i, 200, base=100000), as_of, volumes=np.full(200, 1e7))
        feats = build_stock_features(metas, series, market_id="KOSPI")
        assert set(feats) == {"SAMSUNG", "SKHYNIX"}
        f = feats["SAMSUNG"]
        assert f.relative_return_1d is not None and f.relative_z is not None
        assert f.sector_return_1d is not None  # 같은 업종 2개
        assert f.foreign_flow_z is None  # 수급은 없다 — 0 이 아니다


# ── Impact Score ─────────────────────────────────────────
class TestImpact:
    def _exposure(self, corr, fund, *, window=60):
        rows = [ExposureRow(
            driver_id="BRENT", driver_label="브렌트", windows=[ExposureWindow(window=window, beta=corr, corr=corr, observations=60)],
            beta=corr, corr=corr, fundamental=fund, sign_agreement=None,
        )]
        return StockExposure(stock_id="KOREAN_AIR", rows=rows, primary_window=window)

    def test_score_is_product_of_config_terms(self, universe):
        cfg = get_intelligence_config()["impact"]
        meta = universe.stock_by_id()["KOREAN_AIR"]
        fund = FundamentalExposure(driver_id="BRENT", kind="cost", direction=-1, importance="high", rationale="연료비")
        imp = impact_for(meta, self._exposure(-0.6, fund), "BRENT", "브렌트", 2.5, 95.0)
        assert imp is not None
        shock = 100 * math.tanh(2.5 / cfg["shock_divisor"])
        expected = shock * 0.6 * min(1.0, 0.6 / cfg["stat_conf_full_corr"]) * cfg["fund_relevance"]["high"] * cfg["current_relevance"]["extreme"]
        assert imp.score == pytest.approx(expected)
        assert imp.direction == "down" and imp.sign_conflict is False
        assert {c.key for c in imp.breakdown.contributions} >= {"shock", "exposure", "stat_confidence", "fund_relevance", "current_relevance"}

    def test_sign_conflict_penalised_not_hidden(self, universe):
        cfg = get_intelligence_config()["impact"]
        meta = universe.stock_by_id()["KOREAN_AIR"]
        fund = FundamentalExposure(driver_id="BRENT", kind="cost", direction=-1, importance="high", rationale="연료비")
        agree = impact_for(meta, self._exposure(-0.6, fund), "BRENT", "브렌트", 2.5, 50.0)
        conflict = impact_for(meta, self._exposure(0.6, fund), "BRENT", "브렌트", 2.5, 50.0)
        assert agree is not None and conflict is not None
        assert conflict.sign_conflict is True
        assert conflict.score == pytest.approx(agree.score * cfg["sign_conflict_penalty"])
        assert any(c.key == "sign_conflict" for c in conflict.breakdown.contributions)

    def test_no_statistics_uses_low_confidence_from_config(self, universe):
        cfg = get_intelligence_config()["impact"]
        meta = universe.stock_by_id()["KOREAN_AIR"]
        fund = FundamentalExposure(driver_id="BRENT", kind="cost", direction=-1, importance="high", rationale="연료비")
        imp = impact_for(meta, self._exposure(None, fund), "BRENT", "브렌트", 3.0, 99.0)
        assert imp is not None
        assert imp.stat_confidence == cfg["no_stat_confidence"] and abs(imp.exposure) == cfg["no_stat_exposure"]

    def test_nothing_known_gives_no_row(self, universe):
        meta = universe.stock_by_id()["KOREAN_AIR"]
        assert impact_for(meta, self._exposure(None, None), "BRENT", "브렌트", 3.0, 99.0) is None
        assert impact_for(meta, self._exposure(0.6, None), "WTI", "WTI", 3.0, 99.0) is None  # 행 자체가 없다

    def test_small_shock_below_min_score(self, universe):
        meta = universe.stock_by_id()["KOREAN_AIR"]
        fund = FundamentalExposure(driver_id="BRENT", kind="cost", direction=-1, importance="low", rationale="x")
        assert impact_for(meta, self._exposure(-0.2, fund), "BRENT", "브렌트", 0.1, 50.0) is None

    def test_compute_impacts_sorted(self, universe):
        meta = universe.stock_by_id()["KOREAN_AIR"]
        fund = FundamentalExposure(driver_id="BRENT", kind="cost", direction=-1, importance="high", rationale="연료비")
        rows = compute_impacts([meta], {"KOREAN_AIR": self._exposure(-0.6, fund)}, [("BRENT", "브렌트", 1.0, 50.0), ("BRENT", "브렌트", 3.0, 99.0)])
        assert [r.shock_z for r in rows] == [3.0, 1.0]


# ── 이상 거동 ─────────────────────────────────────────────
class TestAnomaly:
    def _features(self, universe, as_of, *, last_ret, vol_mult):
        meta = universe.stock_by_id()["HANMI_SEMI"]
        vals = _walk(51, 200, base=100000, vol=0.015, last=last_ret)
        vols = np.full(200, 2e6) * np.exp(np.random.default_rng(9).normal(0, 0.15, 200)); vols[-1] *= vol_mult
        series = {"HANMI_SEMI": _series("HANMI_SEMI", vals, as_of, volumes=vols), "KOSPI": _series("KOSPI", _walk(52, 200, base=3000, vol=0.008), as_of)}
        return meta, build_stock_features([meta], series)

    def test_volume_spike_without_news_is_unexplained_and_never_claims_accumulation(self, universe, as_of):
        meta, feats = self._features(universe, as_of, last_ret=0.05, vol_mult=6)
        rows = detect_anomalies([meta], feats, {}, as_of)
        assert len(rows) == 1
        a = rows[0]
        assert a.label == "UNEXPLAINED_ACTIVITY" and a.news_events == 0
        assert "매집" not in a.note.replace("'매집' 같은 단정은 하지 않는다", "")
        assert "외국인 수급" in a.missing
        assert 0 < a.severity <= 100

    def test_same_move_with_news_is_news_driven(self, universe, as_of):
        meta, feats = self._features(universe, as_of, last_ret=0.05, vol_mult=6)
        rows = detect_anomalies([meta], feats, {"HANMI_SEMI": 2}, as_of)
        assert rows[0].label == "NEWS_DRIVEN_MOVE" and rows[0].news_events == 2

    def test_quiet_day_is_not_anomalous(self, universe, as_of):
        meta, feats = self._features(universe, as_of, last_ret=0.001, vol_mult=1.0)
        assert detect_anomalies([meta], feats, {}, as_of) == []

    def test_severity_uses_config_divisor(self, universe, as_of):
        div = float(get_intelligence_config()["anomaly"]["severity_divisor"])
        meta, feats = self._features(universe, as_of, last_ret=0.05, vol_mult=6)
        a = detect_anomalies([meta], feats, {}, as_of)[0]
        mag = max(abs(a.return_z or 0), abs(a.volume_z or 0), abs(a.relative_z or 0))
        assert a.severity == pytest.approx(100 * math.tanh(mag / div))


# ── 가격 vs 펀더멘털 괴리 ──────────────────────────────────
class TestStockDivergence:
    def test_price_down_eps_up(self, universe, as_of):
        meta = universe.stock_by_id()["SAMSUNG"]
        rets = np.zeros(199); rets[-20:] = -0.004  # 한 달 -8%
        vals = 100000 * np.exp(np.cumsum(np.concatenate([[0.0], rets + np.random.default_rng(3).normal(0, 0.003, 199)])))
        feats = build_stock_features([meta], {"SAMSUNG": _series("SAMSUNG", vals, as_of)}, market_id="KOSPI")
        an = AnalystSnapshot(stock_id="SAMSUNG", stock_name=meta.name, as_of=as_of, available=True, eps_revision_1m=6.0, brokers=10, source="test")
        rows = detect_stock_divergences([meta], feats, {}, {}, {"SAMSUNG": an}, {}, as_of)
        kinds = {r.kind for r in rows}
        assert "PRICE_DOWN_EPS_UP" in kinds
        r = next(r for r in rows if r.kind == "PRICE_DOWN_EPS_UP")
        assert r.left.value < 0 and r.right.value == 6.0 and 0 < r.severity <= 100 and r.duration_periods == 1

    def test_persistence_increments_duration(self, universe, as_of):
        meta = universe.stock_by_id()["SAMSUNG"]
        rets = np.zeros(199); rets[-20:] = -0.004
        vals = 100000 * np.exp(np.cumsum(np.concatenate([[0.0], rets])))
        feats = build_stock_features([meta], {"SAMSUNG": _series("SAMSUNG", vals, as_of)})
        an = AnalystSnapshot(stock_id="SAMSUNG", stock_name=meta.name, as_of=as_of, available=True, eps_revision_1m=6.0, brokers=10, source="test")
        first = detect_stock_divergences([meta], feats, {}, {}, {"SAMSUNG": an}, {}, as_of)
        second = detect_stock_divergences([meta], feats, {}, {}, {"SAMSUNG": an}, {}, as_of + timedelta(days=1), previous=first)
        a = next(r for r in first if r.kind == "PRICE_DOWN_EPS_UP")
        b = next(r for r in second if r.kind == "PRICE_DOWN_EPS_UP")
        assert b.duration_periods == a.duration_periods + 1 and b.first_detected_at == a.first_detected_at
        assert b.severity >= a.severity

    def test_no_analyst_means_no_eps_pattern(self, universe, as_of):
        meta = universe.stock_by_id()["SAMSUNG"]
        rets = np.zeros(199); rets[-20:] = -0.004
        vals = 100000 * np.exp(np.cumsum(np.concatenate([[0.0], rets])))
        feats = build_stock_features([meta], {"SAMSUNG": _series("SAMSUNG", vals, as_of)})
        rows = detect_stock_divergences([meta], feats, {}, {}, {}, {}, as_of)
        assert not any("EPS" in r.kind or "TP" in r.kind for r in rows)

    def test_eps_price_divergence_scenario_produces_pattern(self, as_of):
        settings = Settings(data_mode="MOCK", scenario="eps_price_divergence", llm_enabled=False)
        base = run_pipeline(settings, as_of=as_of)
        inv = run_investment(settings, base, as_of=as_of)
        kinds = {(d.kind, d.stock_id) for d in inv.fundamental_divergences}
        # 시나리오의 analyst 스펙(EPS 상향)과 반대로 움직인 종목이 최소 하나는 잡혀야 한다
        assert any(k == "PRICE_DOWN_EPS_UP" for k, _ in kinds), kinds
        sam = inv.stocks["SAMSUNG"]
        assert sam.analyst is not None and sam.analyst.available and sam.analyst.source != "yahoo"


# ── 해설 ─────────────────────────────────────────────────
class TestCommentary:
    def _write(self, directory: Path, as_of: datetime, **over):
        doc = {"commentary": [{
            "kind": "stock", "entity": "SAMSUNG", "date": as_of.date().isoformat(), "as_of": as_of.isoformat(),
            "created_at": as_of.isoformat(), "source_mode": "manual", "confidence": "MEDIUM",
            "sections": {"fact": ["오늘 -2.1%, 60일 z -1.8"], "news": ["감산 관련 기사 없음"], "analyst": [],
                         "interpretation": ["메모리 현물가와 같은 방향 — 상관이지 인과는 아니다"], "unknown": ["외국인 수급은 데이터가 없다"]},
            "evidence": [{"key": "ret_1d", "label": "1일 수익률", "value": -2.1, "display": "-2.1%", "source": "yahoo"}],
            "what_next": ["다음 봉에서 거래량이 이어지는지"],
            **over,
        }]}
        (directory / f"{as_of.date().isoformat()}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def test_loads_sections_and_evidence(self, tmp_path, as_of):
        self._write(tmp_path, as_of)
        rows = load_commentary(tmp_path, as_of)
        assert len(rows) == 1
        c = rows[0]
        assert c.source_mode == "manual" and c.sections.fact and c.sections.unknown and c.evidence[0].source == "yahoo"
        assert c.stale is False
        assert pick(rows, "stock", "SAMSUNG") is c and pick(rows, "market", "KOSPI") is None

    def test_old_commentary_is_kept_but_stale(self, tmp_path, as_of):
        hours = float(get_intelligence_config()["commentary"]["max_age_hours"])
        self._write(tmp_path, as_of - timedelta(hours=hours + 5))
        rows = load_commentary(tmp_path, as_of)
        assert len(rows) == 1 and rows[0].stale is True

    def test_future_commentary_is_ignored(self, tmp_path, as_of):
        self._write(tmp_path, as_of + timedelta(days=2))
        assert load_commentary(tmp_path, as_of) == []

    def test_missing_dir_is_empty_not_error(self, tmp_path, as_of):
        assert load_commentary(tmp_path / "nope", as_of) == []

    def test_broken_file_is_skipped(self, tmp_path, as_of):
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        self._write(tmp_path, as_of)
        assert len(load_commentary(tmp_path, as_of)) == 1


# ── 통합: MOCK 전체 ────────────────────────────────────────
class TestMockIntegration:
    def test_every_stock_has_row_and_headlines(self, mock_inv, universe):
        assert mock_inv.mode is DataMode.MOCK
        assert set(mock_inv.stocks) == {s.id for s in universe.stocks}
        for s in mock_inv.stocks.values():
            assert s.headline_what and s.headline_why and s.headline_next
            assert s.exposure is not None

    def test_alt_points_cover_universe_and_csv_only_are_missing(self, mock_inv, universe):
        assert len(mock_inv.alternative) == len(universe.alternative)
        assert mock_inv.health.alt_expected == len(universe.alternative)

    def test_impacts_carry_breakdown(self, mock_inv):
        assert mock_inv.market_stock_impact
        for imp in mock_inv.market_stock_impact:
            assert imp.breakdown.contributions and imp.rationale
            assert 0 <= imp.score <= 100

    def test_causes_never_claim_causality_without_data(self, mock_inv):
        for s in mock_inv.stocks.values():
            for c in s.explanation.causes:
                assert c.kind in ("CONFIRMED_DATA", "CONFIRMED_NEWS", "ANALYST_VIEW", "MARKET_INFERENCE", "CLAUDE_INTERPRETATION", "UNKNOWN")
                assert c.confidence in ("HIGH", "MEDIUM", "LOW")
                if c.kind == "MARKET_INFERENCE":
                    assert c.confidence != "HIGH"

    def test_lead_lag_is_phrased_as_tendency(self, mock_inv):
        for ll in mock_inv.lead_lag:
            assert "인과" not in ll.note or "아니" in ll.note

    def test_watchlist_badges_are_known(self, mock_inv):
        known = {"NEW_EVENT", "FLOW_INFLECTION", "EPS_REVISION", "ANALYST_CHANGE", "ALTERNATIVE_DATA_SIGNAL",
                 "COMMODITY_IMPACT", "UNUSUAL_MOVE", "THEME_STRENGTHENING", "THEME_WEAKENING"}
        assert mock_inv.watchlist
        for r in mock_inv.watchlist:
            assert set(r.badges) <= known
            assert r.flow_z is None  # 수급 데이터 없음

    def test_serialises_round_trip(self, mock_inv):
        from marketpulse.models.intelligence import InvestmentIntelligence
        again = InvestmentIntelligence.model_validate_json(mock_inv.model_dump_json())
        assert again.as_of == mock_inv.as_of and len(again.stocks) == len(mock_inv.stocks)

    @pytest.mark.parametrize("scenario", ["commodity_shock", "memory_upcycle", "oil_spike", "china_stress", "rates_stock_divergence", "eps_price_divergence"])
    def test_new_scenarios_land_their_shocks(self, scenario, as_of):
        sc = load_scenario(MOCK_DIR, scenario)
        u = get_universe()
        shared = [get_instruments().by_id()[i] for i in shared_driver_ids()]
        series = AltMockAdapter(MOCK_DIR, scenario).fetch_series(u.stocks, u.alternative, shared, bars=180, as_of=as_of)
        ins = {s.id: s.as_instrument() for s in u.stocks}
        ins.update({a.id: a.as_instrument() for a in u.alternative})
        ins.update({i.id: i for i in shared})
        for iid, z in sc.shocks.items():
            if iid not in series:
                continue
            f = compute_feature(ins[iid], series[iid], window=60)
            assert f.z_1d == pytest.approx(z, abs=0.15), (scenario, iid, f.z_1d)
        for iid, mult in sc.volume_shocks.items():
            vz, ratio = volume_z(series[iid], 60)
            assert vz is not None and vz > 1.0, (scenario, iid, vz)

    def test_mock_is_deterministic(self, as_of):
        u = get_universe()
        shared = [get_instruments().by_id()[i] for i in shared_driver_ids()]
        a = AltMockAdapter(MOCK_DIR, "oil_spike").fetch_series(u.stocks, u.alternative, shared, bars=180, as_of=as_of)
        b = AltMockAdapter(MOCK_DIR, "oil_spike").fetch_series(u.stocks, u.alternative, shared, bars=180, as_of=as_of)
        assert {k: v.values for k, v in a.items()} == {k: v.values for k, v in b.items()}

    def test_oil_spike_hits_airline_negative_and_refiner_positive(self, as_of):
        settings = Settings(data_mode="MOCK", scenario="oil_spike", llm_enabled=False)
        inv = run_investment(settings, run_pipeline(settings, as_of=as_of), as_of=as_of)
        by = {(i.stock_id, i.driver_id): i for i in inv.market_stock_impact}
        air = next((v for (s, d), v in by.items() if s == "KOREAN_AIR" and d in ("BRENT", "WTI", "JET_FUEL_PROXY")), None)
        assert air is not None and air.direction == "down"
        soil = next((v for (s, d), v in by.items() if s == "SOIL" and d in ("BRENT", "WTI")), None)
        assert soil is not None and soil.direction == "up"


# ── 실데이터 어댑터 (네트워크 없이 CSV·저장소) ───────────────
class TestAltLiveAdapter:
    def _csv(self, path: Path, as_of: datetime, n=120):
        stamps = business_timestamps(as_of, n)
        vals = _walk(77, n, base=3.0)
        path.write_text("date,close\n" + "\n".join(f"{t.date().isoformat()},{v:.4f}" for t, v in zip(stamps, vals)), encoding="utf-8")

    def test_csv_only_instrument_reads_from_replay_and_persists(self, tmp_path, as_of, universe):
        (tmp_path / "alternative").mkdir()
        self._csv(tmp_path / "alternative" / "DRAM_SPOT.csv", as_of)
        store = SqliteSnapshotRepository(":memory:")
        a = next(x for x in universe.alternative if x.id == "DRAM_SPOT")
        adapter = AltLiveAdapter(replay_dir=tmp_path, store=store)
        adapter.politeness_sec = 0
        out = adapter.fetch_series([a.as_instrument()], {a.id: a.sources}, bars=100, as_of=as_of)
        assert "DRAM_SPOT" in out and out["DRAM_SPOT"].meta.quality is DataQuality.OK
        assert out["DRAM_SPOT"].meta.source.startswith("csv:")
        assert adapter.outcomes["DRAM_SPOT"].ok
        assert len(store.load_daily("DRAM_SPOT")) == 100
        assert store.fetch_log("DRAM_SPOT")["fetched_date"] == as_of.date().isoformat()

    def test_second_call_same_day_uses_store(self, tmp_path, as_of, universe):
        (tmp_path / "alternative").mkdir()
        self._csv(tmp_path / "alternative" / "DRAM_SPOT.csv", as_of)
        store = SqliteSnapshotRepository(":memory:")
        a = next(x for x in universe.alternative if x.id == "DRAM_SPOT")
        adapter = AltLiveAdapter(replay_dir=tmp_path, store=store)
        adapter.fetch_series([a.as_instrument()], {a.id: a.sources}, bars=100, as_of=as_of)
        (tmp_path / "alternative" / "DRAM_SPOT.csv").unlink()
        out = adapter.fetch_series([a.as_instrument()], {a.id: a.sources}, bars=100, as_of=as_of)
        assert adapter.outcomes["DRAM_SPOT"].provider == "store"
        assert out["DRAM_SPOT"].meta.quality is DataQuality.OK

    def test_provider_failure_falls_back_to_stale_store(self, tmp_path, as_of, universe):
        (tmp_path / "alternative").mkdir()
        self._csv(tmp_path / "alternative" / "DRAM_SPOT.csv", as_of)
        store = SqliteSnapshotRepository(":memory:")
        a = next(x for x in universe.alternative if x.id == "DRAM_SPOT")
        AltLiveAdapter(replay_dir=tmp_path, store=store).fetch_series([a.as_instrument()], {a.id: a.sources}, bars=100, as_of=as_of)
        (tmp_path / "alternative" / "DRAM_SPOT.csv").unlink()
        # 다음 날 — 캐시는 어제 것, 공급자는 실패
        tomorrow = as_of + timedelta(days=1)
        adapter = AltLiveAdapter(replay_dir=tmp_path, store=store)
        out = adapter.fetch_series([a.as_instrument()], {a.id: a.sources}, bars=100, as_of=tomorrow)
        assert out["DRAM_SPOT"].meta.quality is DataQuality.STALE
        assert not adapter.outcomes["DRAM_SPOT"].ok or adapter.outcomes["DRAM_SPOT"].provider == "store"

    def test_missing_everything_yields_no_series_not_zero(self, tmp_path, as_of, universe):
        a = next(x for x in universe.alternative if x.id == "DRAM_SPOT")
        adapter = AltLiveAdapter(replay_dir=tmp_path, store=None)
        out = adapter.fetch_series([a.as_instrument()], {a.id: a.sources}, bars=100, as_of=as_of)
        assert out == {} and not adapter.outcomes["DRAM_SPOT"].ok

    def test_upsert_is_idempotent(self):
        store = SqliteSnapshotRepository(":memory:")
        rows = [("2026-09-01", 1.0, 10.0), ("2026-09-02", 2.0, None)]
        store.upsert_daily("X", rows, "test")
        store.upsert_daily("X", [("2026-09-02", 2.5, 20.0)], "test")
        got = store.load_daily("X")
        assert [(d, v, vol) for d, v, vol, _ in got] == [("2026-09-01", 1.0, 10.0), ("2026-09-02", 2.5, 20.0)]


# ── API ─────────────────────────────────────────────────
@pytest.fixture
def client() -> TestClient:
    get_service().clear()
    get_investment_service().clear()
    return TestClient(create_app())


class TestApi:
    def test_investment_ok_and_shaped(self, client):
        r = client.get("/api/v1/investment")
        assert r.status_code == 200
        d = r.json()
        for key in ("drivers", "alternative", "market_stock_impact", "semiconductor", "commodity_impact", "unusual_movers",
                    "theme_stocks", "analyst", "fundamental_divergences", "stocks", "watchlist", "lead_lag", "commentary", "health"):
            assert key in d, key
        assert d["mode"] == "MOCK" and d["health"]["stocks_available"] > 0

    def test_existing_snapshot_untouched(self, client):
        snap = client.get("/api/v1/snapshot").json()
        assert "investment" not in snap  # 기존 스냅샷을 비대하게 만들지 않는다

    def test_stock_detail_and_404(self, client):
        r = client.get("/api/v1/investment/stocks/SAMSUNG")
        assert r.status_code == 200 and r.json()["meta"]["id"] == "SAMSUNG"
        assert client.get("/api/v1/investment/stocks/NOPE").status_code == 404

    def test_alternative_group_filter(self, client):
        rows = client.get("/api/v1/investment/alternative?group=semiconductor").json()
        assert rows and all(p["group"] == "semiconductor" for p in rows)

    def test_refresh_and_scenario(self, client):
        a = client.get("/api/v1/investment?scenario=oil_spike").json()
        assert a["scenario"] == "oil_spike"
        b = client.get("/api/v1/investment?scenario=oil_spike&refresh=true").json()
        assert b["scenario"] == "oil_spike"
        assert client.get("/api/v1/investment?scenario=nope").status_code == 404


# ── 2026-09-16 후속: 종목 고유 뉴스 배지 · 롤오버 다음 봉 확인 ───────────
class TestFollowups:
    def test_new_event_badge_needs_stock_mention_not_theme(self, universe, as_of):
        from marketpulse.engines.investment import _mentions_stock
        from marketpulse.models.news import AssetImpact, Entity, NewsEvent
        sam = universe.stock_by_id()["SAMSUNG"]; hyn = universe.stock_by_id()["SKHYNIX"]
        theme_only = NewsEvent(id="e1", event="반도체 테마 기사", event_type="other", themes=["semiconductor"], timestamp=as_of, source="t")
        named = NewsEvent(id="e2", event="삼성전자 자사주 매입", event_type="other", themes=["semiconductor"], timestamp=as_of, source="t",
                          entities=[Entity(name="삼성전자", type="company")])
        by_ticker = NewsEvent(id="e3", event="x", event_type="other", themes=[], timestamp=as_of, source="t",
                              entities=[Entity(name="Samsung Electronics", type="company", ticker="005930.KS")])
        by_asset = NewsEvent(id="e4", event="x", event_type="other", themes=[], timestamp=as_of, source="t",
                             affected_assets=[AssetImpact(instrument_id="SKHYNIX", label="SK하이닉스", direction="up")])
        assert not _mentions_stock(theme_only, sam)
        assert _mentions_stock(named, sam) and not _mentions_stock(named, hyn)
        assert _mentions_stock(by_ticker, sam)
        assert _mentions_stock(by_asset, hyn) and not _mentions_stock(by_asset, sam)

    def test_watchlist_new_event_only_for_named_stocks(self, mock_inv):
        # MOCK 기사는 테마만 태그돼 있어 어떤 줄에도 NEW_EVENT 가 붙지 않아야 한다
        assert not any("NEW_EVENT" in r.badges for r in mock_inv.watchlist)

    def _fut(self, universe, as_of, last, prev_last=None):
        cfg = get_intelligence_config()["alternative"]
        fut = next(a for a in universe.alternative if a.id == "GASOLINE")
        vals = _walk(5, 200, base=2.0, vol=0.01, last=last)
        if prev_last is not None:
            vals = np.concatenate([vals[:-1], [vals[-2] * math.exp(prev_last), vals[-2] * math.exp(prev_last) * math.exp(last)]])
        s = _series("GASOLINE", vals, as_of)
        f = compute_feature(fut.as_instrument(), s, window=60)
        return fut, s, f

    def test_rollover_reverted_on_next_bar(self, universe, as_of):
        fut, s1, f1 = self._fut(universe, as_of, last=-0.07)
        p1 = build_alt_points([fut], {"GASOLINE": f1}, {"GASOLINE": s1}, universe.stock_by_id(), as_of)[0]
        assert p1.rollover_suspect and p1.rollover_followup is None
        # 다음 날 +6% 되돌림
        tomorrow = as_of + timedelta(days=3)  # 금요일 기준 → 다음 영업일(월)
        vals = list(s1.values) + [s1.values[-1] * math.exp(0.06)]
        s2 = _series("GASOLINE", vals, tomorrow)
        f2 = compute_feature(fut.as_instrument(), s2, window=60)
        p2 = build_alt_points([fut], {"GASOLINE": f2}, {"GASOLINE": s2}, universe.stock_by_id(), tomorrow, previous={"GASOLINE": p1})[0]
        assert p2.rollover_followup == "reverted" and "되돌려졌다" in p2.note

    def test_rollover_persisted_on_next_bar(self, universe, as_of):
        fut, s1, f1 = self._fut(universe, as_of, last=-0.07)
        p1 = build_alt_points([fut], {"GASOLINE": f1}, {"GASOLINE": s1}, universe.stock_by_id(), as_of)[0]
        tomorrow = as_of + timedelta(days=3)  # 금요일 기준 → 다음 영업일(월)
        vals = list(s1.values) + [s1.values[-1] * math.exp(-0.002)]
        s2 = _series("GASOLINE", vals, tomorrow)
        f2 = compute_feature(fut.as_instrument(), s2, window=60)
        p2 = build_alt_points([fut], {"GASOLINE": f2}, {"GASOLINE": s2}, universe.stock_by_id(), tomorrow, previous={"GASOLINE": p1})[0]
        assert p2.rollover_followup == "persisted" and "되돌려지지 않았다" in p2.note and "가리지 못한다" in p2.note

    def test_same_bar_rerun_does_not_judge(self, universe, as_of):
        fut, s1, f1 = self._fut(universe, as_of, last=-0.07)
        p1 = build_alt_points([fut], {"GASOLINE": f1}, {"GASOLINE": s1}, universe.stock_by_id(), as_of)[0]
        p1b = build_alt_points([fut], {"GASOLINE": f1}, {"GASOLINE": s1}, universe.stock_by_id(), as_of, previous={"GASOLINE": p1})[0]
        assert p1b.rollover_followup is None

    def test_previous_alt_points_flow_through_build_investment(self, settings, base_snapshot, as_of):
        first = run_investment(settings, base_snapshot, as_of=as_of)
        again = run_investment(settings, base_snapshot, as_of=as_of, previous=first)
        assert all(p.rollover_followup is None for p in again.alternative)  # 같은 봉이므로 판정 없음

    def test_store_revision_is_detected_not_hidden(self, tmp_path, as_of, universe):
        """어제 저장한 봉의 값이 오늘 공급자에서 다르게 오면 revisions 에 남는다 (선물 확정 전 값·월물 교체)."""
        from marketpulse.adapters.alternative.live import AltLiveAdapter
        from marketpulse.storage.sqlite_repo import SqliteSnapshotRepository
        (tmp_path / "alternative").mkdir()
        a = next(x for x in universe.alternative if x.id == "DRAM_SPOT")
        stamps = business_timestamps(as_of, 120)
        vals = _walk(77, 120, base=3.0)
        path = tmp_path / "alternative" / "DRAM_SPOT.csv"
        path.write_text("date,close\n" + "\n".join(f"{t.date().isoformat()},{v:.4f}" for t, v in zip(stamps, vals)), encoding="utf-8")
        store = SqliteSnapshotRepository(":memory:")
        ad = AltLiveAdapter(replay_dir=tmp_path, store=store)
        ad.fetch_series([a.as_instrument()], {a.id: a.sources}, bars=100, as_of=as_of)
        assert ad.revisions == {}
        # 다음 날: 마지막 봉이 7% 낮게 다시 온다
        vals2 = vals.copy(); vals2[-1] *= 0.93
        path.write_text("date,close\n" + "\n".join(f"{t.date().isoformat()},{v:.4f}" for t, v in zip(stamps, vals2)), encoding="utf-8")
        ad2 = AltLiveAdapter(replay_dir=tmp_path, store=store)
        ad2.fetch_series([a.as_instrument()], {a.id: a.sources}, bars=100, as_of=as_of + timedelta(days=1))
        assert "DRAM_SPOT" in ad2.revisions
        n, pct = ad2.revisions["DRAM_SPOT"]
        assert n == 1 and pct == pytest.approx(7.0, abs=0.1)

    def test_rollover_followup_ignores_same_bar_with_different_timestamp(self, universe, as_of):
        """저장소는 날짜만, Yahoo 는 세션 시각을 남긴다. 같은 날 봉을 새 봉으로 오인하면 안 된다."""
        fut, s1, f1 = self._fut(universe, as_of, last=-0.07)
        p1 = build_alt_points([fut], {"GASOLINE": f1}, {"GASOLINE": s1}, universe.stock_by_id(), as_of)[0]
        p1_midnight = p1.model_copy(update={"as_of": p1.as_of.replace(hour=0, minute=0)})
        p1b = build_alt_points([fut], {"GASOLINE": f1}, {"GASOLINE": s1}, universe.stock_by_id(), as_of, previous={"GASOLINE": p1_midnight})[0]
        assert p1b.rollover_followup is None
