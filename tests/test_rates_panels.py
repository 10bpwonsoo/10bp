"""금리 탭 아래 세 패널(2026-10-13) — INFLATION PRESSURE MAP · TREASURY CURVE · YIELD MOVE BREAKDOWN, 그리고 분해의 날짜 맞춤."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from marketpulse.ai import inflation_read
from marketpulse.ai.client import LLMFailure
from marketpulse.engines.rates_panels import _shape, build_inflation_map, build_yield_breakdown, load_rates_panels_config
from marketpulse.engines.rates_regime import _aligned_change, build_rates_regime
from marketpulse.models.common import DataMeta, DataMode, DataQuality
from marketpulse.models.market import MarketSeries
from marketpulse.models.rates_regime import ComponentScore, EvidenceItem, YieldDecomposition
from tests.test_rates_regime import _run

CFG = load_rates_panels_config()


def _series(iid: str, start: datetime, vals: list[float | None]) -> MarketSeries:
    ts = [start + timedelta(days=i) for i in range(len(vals))]
    meta = DataMeta(source="test", mode=DataMode.DELAYED, retrieved_at=ts[-1], as_of=ts[-1], quality=DataQuality.OK)
    return MarketSeries(instrument_id=iid, timestamps=ts, values=vals, meta=meta)


@pytest.fixture(scope="module")
def mock():
    snap, market, by_id = _run("inflation_shock")
    return snap, market, by_id, build_rates_regime(market, snap.themes, by_id)


class TestAlignment:
    def test_breakeven_published_a_day_earlier_is_aligned(self):
        """FRED 기대인플레가 하루 먼저 나오는 날 — 각자의 마지막 5봉을 쓰면 항등식이 깨진다. 공통 날짜로 맞추면 명목 = 실질 + 기대인플레."""
        d0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
        nom = _series("US10Y", d0, [5.24, 5.28, 5.31, 5.27, 5.28, 5.22])
        tips = _series("TIPS10Y", d0, [2.88, 2.92, 2.95, 2.91, 2.92, 2.87])
        be = _series("BE10Y", d0 + timedelta(days=1), [2.36, 2.36, 2.36, 2.36, 2.35, 2.33])  # 하루 늦게 시작해 하루 더 간다
        out = _aligned_change({"US10Y": nom, "BE10Y": be, "TIPS10Y": tips}, ["US10Y", "BE10Y", "TIPS10Y"], 4)
        assert out is not None
        chg, start, end = out
        assert end == (d0 + timedelta(days=5)).date() and start == (d0 + timedelta(days=1)).date()
        assert chg["US10Y"] == pytest.approx(chg["BE10Y"] + chg["TIPS10Y"], abs=0.11)

    def test_too_few_common_days(self):
        d0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
        assert _aligned_change({"A": _series("A", d0, [1, 2]), "B": _series("B", d0, [1, 2])}, ["A", "B"], 5) is None

    def test_without_series_falls_back_and_flags(self, mock):
        r = mock[3]
        for d in r.decomposition:
            assert d.aligned is not None  # 날짜가 같은지 표시가 있다


class TestCurveShape:
    @pytest.mark.parametrize("chg,spread,expect", [
        ({"2Y": -3, "5Y": -2, "10Y": -2, "30Y": -1}, 1, "bull_steepening"),   # 단기물이 더 내림 → 스티프닝(요청 예시)
        ({"2Y": -2, "5Y": -4, "10Y": -6, "30Y": -7}, -4, "bull_flattening"),  # 장기물이 더 내림
        ({"2Y": 2, "10Y": 6, "30Y": 7}, 4, "bear_steepening"),
        ({"2Y": 6, "10Y": 2, "30Y": 1}, -4, "bear_flattening"),
        ({"2Y": -3, "10Y": -3, "30Y": -3}, 0, "parallel_down"),
        ({"2Y": -3, "10Y": 2, "30Y": 3}, 5, "twist_steepening"),
        ({"2Y": 0.2, "10Y": -0.3, "30Y": 0.1}, -0.5, "flat"),
    ])
    def test_shape_from_bp(self, chg, spread, expect):
        assert _shape(chg, spread, None, CFG["curve_move"])[0] == expect

    def test_curve_view_separates_bp_and_sigma(self, mock):
        cv = mock[3].curve_move
        assert cv.window_label == "5D" and all(p.z_window == "5D" for p in cv.points)
        for p in cv.points:
            if p.today is not None and p.chg_bp is not None:
                assert p.ago == pytest.approx(p.today - p.chg_bp / 100.0, abs=1e-3)
        s = next(x for x in cv.spreads if x.key == "2s10s")
        two, ten = (next(p for p in cv.points if p.label == t) for t in ("2Y", "10Y"))
        assert s.chg_bp == pytest.approx(ten.chg_bp - two.chg_bp)
        assert not re.search(r"\d", cv.read) and "확률" not in cv.read


class TestInflationMap:
    def _comp(self, key, score, ev=()):
        return ComponentScore(key=key, label=key.title(), label_ko=key, score=score, status="missing" if score is None else ("down" if score < 0 else "up"),
                              evidence=[EvidenceItem(id=i, label=i, value=v, sign=1, weight=1, contribution=v) for i, v in ev])

    def test_missing_is_not_zero_and_weakens_signal(self):
        m = build_inflation_map([self._comp("realized", None), self._comp("implied", -58.5, [("BE10Y", -1.2), ("BE5Y", -1.1)]), self._comp("energy", 16.3),
                                 self._comp("wages", None), self._comp("fx", -36.2)], CFG)
        assert m.available == 3 and m.total == 5 and m.confirmation == "PARTIAL"
        assert m.signal == "COOLING BIAS"  # 실제 물가가 없으면 'COOLING' 이라고 단정하지 않는다
        st = {i.key: i for i in m.items}
        assert st["realized"].state == "DATA UNAVAILABLE" and st["realized"].score is None and "CPI / PCE" in st["realized"].missing_text
        assert st["realized"].source_class == "UNAVAILABLE" and st["realized"].in_signal is False
        assert st["implied"].state == "COOLING" and st["energy"].state == "MILD PRESSURE" and st["fx"].state == "EASING"
        assert st["implied"].evidence_text == "10Y BE -1.2σ · 5Y BE -1.1σ"
        for txt in (m.summary, m.read, m.link):
            assert not re.search(r"\d", txt.replace("CPI/PCE", "")) and "확률" not in txt
        assert "(" not in m.summary and "(" not in m.read  # 조사 이중 표기가 남지 않는다

    def test_full_data_allows_strong_label_and_mixed(self):
        full = [self._comp(k, -40) for k in ("realized", "implied", "energy", "wages", "fx")]
        assert build_inflation_map(full, CFG).signal == "COOLING"
        mixed = [self._comp("realized", -40), self._comp("implied", -40), self._comp("energy", 45), self._comp("wages", 0), self._comp("fx", -10)]
        assert build_inflation_map(mixed, CFG).signal == "MIXED"

    def test_nothing_available(self):
        m = build_inflation_map([self._comp("realized", None), self._comp("wages", None)], CFG)
        assert m.signal == "NO SIGNAL" and m.confirmation == "INSUFFICIENT"


class TestBreakdown:
    def _d(self, tenor, nom, be, tips):
        return YieldDecomposition(tenor=tenor, window_days=5, nominal_bp=nom, breakeven_bp=be, real_implied_bp=None if nom is None or be is None else nom - be,
                                  real_measured_bp=tips, aligned=True)

    def test_primary_and_character(self, mock):
        market = mock[1]
        yb = build_yield_breakdown([self._d("10Y", -8, -9, 1), self._d("5Y", -6, 1, -7), self._d("30Y", -5, None, None)], market, CFG)
        t = {x.tenor: x for x in yb.tenors}
        assert [x.tenor for x in yb.tenors][:2] == ["5Y", "10Y"] and yb.default_tenors == ["5Y", "10Y"]
        assert t["10Y"].primary == "breakeven" and t["10Y"].primary_label == "INFLATION EXPECTATION ↓"
        assert "실질금리 하락이 아니라 기대인플레이션 하락이 주도" in t["10Y"].line
        assert t["5Y"].primary == "real" and "실질금리 하락이 주도" in t["5Y"].line
        assert t["30Y"].primary == "unknown"
        assert yb.character_key == "disinflation"

    def test_model_vs_observed_divergence(self, mock):
        yb = build_yield_breakdown([self._d("10Y", -2, -3, -1)], mock[1], CFG)  # 모델 실질 +1 vs TIPS −1
        t = yb.tenors[0]
        assert t.real_bp == 1 and t.tips_bp == -1 and t.divergence and "MODEL / MARKET DIVERGENCE" in t.divergence_text and t.small_move

    def test_unaligned_is_not_judged(self, mock):
        d = self._d("10Y", -2, -3, -1).model_copy(update={"aligned": False})
        t = build_yield_breakdown([d], mock[1], CFG).tenors[0]
        assert not t.divergence and "관측일" in t.divergence_text


class FakeClient:
    def __init__(self, *responses, enabled=True):
        self.responses = list(responses); self.enabled = enabled; self.last_error = None; self.calls = []

    def interpret(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


class TestInflationRead:
    def test_numbers_rejected_then_ok(self, mock):
        r = mock[3]
        c = FakeClient({"read": "기대인플레가 1.2σ 내렸다."}, {"read": "시장 기대인플레와 실물 투입 비용이 같은 쪽으로 움직여 물가 압력은 위쪽으로 기운 편입니다."})
        out = inflation_read.attach_inflation_read(r, client=c)
        m = out.inflation_map.read_meta
        assert m.source == "llm" and len(c.calls) == 2 and m.warnings and "숫자" in m.warnings[0]
        assert out.inflation_map.read.startswith("시장 기대인플레")

    def test_failure_keeps_rule_read(self, mock):
        r = mock[3]
        out = inflation_read.attach_inflation_read(r, client=FakeClient(LLMFailure("x", "api")))
        assert out.inflation_map.read_meta.source == "rule" and out.inflation_map.read == r.inflation_map.read
        assert out.model_dump(exclude={"inflation_map"}) == r.model_dump(exclude={"inflation_map"})


class TestApi:
    def test_mock_route_has_panels(self):
        from fastapi.testclient import TestClient
        from marketpulse.api.deps import get_investment_service, get_rates_regime_service, get_scenario_check_service, get_service, get_state_history_service
        from marketpulse.api.main import create_app
        for svc in (get_service(), get_state_history_service(), get_investment_service(), get_scenario_check_service(), get_rates_regime_service()):
            svc.clear()
        body = TestClient(create_app()).get("/api/v1/rates-regime?scenario=inflation_shock").json()
        assert body["inflation_map"]["read_meta"]["status"] == "skipped" and body["curve_move"]["shape"] and body["yield_breakdown"]["tenors"]
