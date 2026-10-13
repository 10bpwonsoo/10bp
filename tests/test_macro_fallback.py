"""신뢰도 기반 macro fallback data layer(2026-10-13) — 급(tier) 순서 · PROXY 표시 · STALE · 뉴스 분리 · 숫자를 만들지 않는다."""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from marketpulse.engines.macro_fallback import build_layer, build_news_pulse, load_macro_config, resolve_series, transforms
from marketpulse.engines.rates_panels import build_inflation_map, load_rates_panels_config
from marketpulse.models.rates_regime import ComponentScore

CFG = load_macro_config()
AS_OF = datetime(2026, 10, 13, 0, 12, tzinfo=timezone.utc)


def _monthly(n: int, end: date, growth: float, wiggle: float = 0.0, *, last_months: list[float] | None = None) -> list[list]:
    """end 에서 끝나는 월간 지수. 앞은 growth(%/월) ± wiggle, 마지막 몇 달은 last_months 로 덮는다."""
    vals, v = [], 100.0
    for i in range(n):
        g = growth + (wiggle * math.sin(i * 1.7))
        if last_months and i >= n - len(last_months):
            g = last_months[i - (n - len(last_months))]
        v *= 1 + g / 100.0
        vals.append(v)
    rows = []
    for i, x in enumerate(vals):
        m = end.year * 12 + end.month - 1 - (n - 1 - i)
        rows.append([date(m // 12, m % 12 + 1, 1).isoformat(), round(x, 4)])
    return rows


def _raw(rows, vintage="2026-09-30", path="PRIMARY"):
    return {"path": path, "observations": rows, "vintage": vintage, "error": None}


CURATED = {"releases": [
    {"key": "us_cpi", "period": "2026-08", "date": "2026-09-11", "measures": [{"key": "headline_yoy", "actual": 3.4, "consensus": 3.4}, {"key": "core_yoy", "actual": 2.4, "consensus": 2.4, "prior": 2.5}],
     "sources": [{"publisher": "CNBC", "url": "https://x"}]},
    {"key": "us_cpi", "period": "2026-09", "date": "2026-10-14", "measures": [{"key": "headline_yoy", "actual": 9.9, "consensus": 3.5}], "sources": [{"publisher": "Future"}]},
]}


class TestTransforms:
    def test_cooling_momentum_is_negative_z(self):
        rows = _monthly(90, date(2026, 8, 1), 0.25, 0.08, last_months=[0.0, 0.0, 0.0])
        tr = transforms({date.fromisoformat(d): v for d, v in rows}, "monthly", CFG)
        assert tr["yoy"] > tr["ann"] and tr["accel"] < 0 and tr["z"] < -1

    def test_missing_month_is_skipped_not_zero(self):
        rows = _monthly(90, date(2026, 8, 1), 0.25, 0.08)
        rows[-11][1] = None  # 1년 전 바로 다음 달이 미집계
        tr = transforms({date.fromisoformat(d): v for d, v in rows if v is not None}, "monthly", CFG)
        assert tr["yoy"] is not None and tr["z"] is not None


class TestTiers:
    def test_primary_from_fred(self):
        p = resolve_series("CPI", CFG["series"]["CPI"], _raw(_monthly(90, date(2026, 8, 1), 0.25, 0.08), vintage="2026-09-11"), CURATED, AS_OF.date(), CFG)
        assert p.source_tier == "PRIMARY" and p.is_original_data and p.source == "BLS via FRED"
        assert p.last_updated == date(2026, 9, 11) and p.freshness_days == 32 and not p.stale
        assert p.consensus == 3.4 and p.period == "2026-08"  # 같은 기간 보도 컨센서스만 붙인다

    def test_secondary_when_fred_fails_and_no_forecasts(self):
        p = resolve_series("CPI", CFG["series"]["CPI"], {"path": None, "observations": [], "vintage": None, "error": "API auth · 미러 http"}, CURATED, AS_OF.date(), CFG)
        assert p.source_tier == "SECONDARY" and p.value == 3.4 and p.source == "CNBC" and p.release_date == date(2026, 9, 11)
        assert "FRED: API auth" in p.fallback_reason and p.confidence < 0.95
        # 10/14 발표(as_of 이후)는 쓰지 않는다 — 9.9 는 어디에도 없다
        assert p.value != 9.9

    def test_unavailable_never_invents_a_number(self):
        p = resolve_series("AHE", CFG["series"]["AHE"], None, CURATED, AS_OF.date(), CFG)
        assert p.source_tier == "UNAVAILABLE" and p.value is None and p.pressure_z is None and not p.is_original_data

    def test_stale_is_flagged_and_excluded(self):
        p = resolve_series("PCE", CFG["series"]["PCE"], _raw(_monthly(90, date(2026, 5, 1), 0.25, 0.08), vintage="2026-06-27"), None, AS_OF.date(), CFG)
        assert p.stale and p.confidence == pytest.approx(0.95 * 0.5, abs=0.01)
        layer = build_layer({"PCEPI": _raw(_monthly(90, date(2026, 5, 1), 0.25, 0.08), vintage="2026-06-27")}, as_of=AS_OF)
        assert layer.components["realized"].score is None and layer.components["realized"].stale  # STALE 만 있으면 점수를 내지 않는다


class TestComponents:
    def _fred(self, ids, vintage="2026-09-30"):
        return {i: _raw(_monthly(90, date(2026, 8, 1), 0.25, 0.08, last_months=[0.1, 0.1, 0.1]), vintage=vintage) for i in ids}

    def test_realized_real_data_keeps_proxy_out_of_score(self):
        raw = self._fred(["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PPIFIS", "IR"])
        c = build_layer(raw, as_of=AS_OF).components["realized"]
        assert c.source_class == "PRIMARY" and c.is_original_data and c.display_label == "Realized Inflation"
        assert {p.series for p in c.series} == {"CPI", "CORE_CPI", "PCE", "CORE_PCE"}
        assert {p.series for p in c.reference} == {"PPI_FD", "IMPORT_PRICES"} and all("점수에 넣지 않음" in p.note for p in c.reference)

    def test_realized_proxy_is_renamed_and_disclosed(self):
        c = build_layer(self._fred(["PPIFIS", "IR"]), as_of=AS_OF).components["realized"]
        assert c.display_label == "REALIZED INFLATION PROXY" and c.source_class == "PROXY" and not c.is_original_data
        assert "실제 CPI/PCE 데이터 미연결" in c.fallback_reason and c.proxy_components == ["PPI Final Demand", "Import Prices"]

    def test_wages_is_always_proxy_even_from_official_inputs(self):
        c = build_layer(self._fred(["CES0500000003", "ECIWAG", "CUSR0000SASLE", "IA001260M"]), as_of=AS_OF).components["wages"]
        assert c.source_class == "PROXY" and not c.is_original_data and c.score is not None
        assert c.proxy_components == ["AHE", "ECI", "Services CPI", "Core Services PCE"] and "단일 원데이터 미연결" in c.fallback_reason
        assert all(p.source_tier == "PRIMARY" for p in c.series if p.series != "ECI")  # ECI 는 분기라 위 월간 합성으로는 안 맞을 수 있다

    def test_nothing_is_unavailable(self):
        L = build_layer({}, as_of=AS_OF)
        assert L.components["realized"].source_class == "UNAVAILABLE" and L.components["realized"].score is None
        assert L.components["wages"].source_class == "UNAVAILABLE"


class TestNews:
    def test_news_pulse_from_themes(self):
        th = [SimpleNamespace(theme_id="inflation", news_sentiment=20.0), SimpleNamespace(theme_id="oil", news_sentiment=30.0)]
        ev = [SimpleNamespace(timestamp=AS_OF, themes=["inflation"])]
        n = build_news_pulse(th, ev, AS_OF, CFG)
        assert n.score == pytest.approx((20 * 1.0 + 30 * 0.6) / 1.6, abs=0.1) and n.articles == 1
        assert [d.arrow for d in n.drivers][:2] == ["↑", "↑"] and "공식" in n.comment


class TestPanel:
    def _comp(self, key, score, **kw):
        return ComponentScore(key=key, label=key.title(), label_ko=key, score=score, status="missing" if score is None else ("down" if score < 0 else "up"), coverage=1.0, **kw)

    def test_quality_counts_and_news_outside_signal(self):
        raw = {i: _raw(_monthly(90, date(2026, 8, 1), 0.25, 0.08, last_months=[0.1, 0.1, 0.1])) for i in
               ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "CES0500000003", "ECIWAG", "CUSR0000SASLE", "IA001260M"]}
        th = [SimpleNamespace(theme_id="inflation", news_sentiment=90.0)]
        L = build_layer(raw, as_of=AS_OF, themes=th, events=[SimpleNamespace(timestamp=AS_OF, themes=["inflation"])])
        comps = [self._comp("realized", L.components["realized"].score, source_class="PRIMARY", is_original_data=True, confidence=0.95),
                 self._comp("implied", -50.0), self._comp("energy", 10.0),
                 self._comp("wages", L.components["wages"].score, source_class="PROXY", is_original_data=False, confidence=0.45), self._comp("fx", -30.0)]
        m = build_inflation_map(comps, load_rates_panels_config(), L)
        items = {i.key: i for i in m.items}
        assert items["news"].source_class == "NEWS" and items["news"].in_signal is False and items["news"].score == 90.0
        assert items["wages"].source_class == "PROXY" and items["wages"].proxy_note == "실제 원데이터 미연결 · 대체 지표로 추정" and items["wages"].proxy_components
        assert items["realized"].values and items["realized"].values[0].source_class == "PRIMARY"
        assert (m.official_count, m.proxy_count, m.news_count) == (4, 1, 1)
        assert m.confirmation == "PARTIAL" and not m.signal.startswith("REACCELERATING")  # 뉴스가 강해도 신호를 끌어올리지 않는다
        assert len(m.data_sources) == len(L.series)
