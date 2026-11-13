"""
금리 탭 MARKET READ — Macro + Rates Investment Interpretation (2026-10-13).

이전 MARKET READ 는 지배 driver 를 문장으로 다시 읽는 템플릿이었다. 여기서는 PM/매크로 전략가 관점의 짧은 해석(2~4문장)을
LLM 이 쓴다. 역할 분담은 그대로다 — 숫자 · regime · driver 점수는 정량 엔진이 이미 계산했고, LLM 은 그것을 바꾸지 않고
'이 금리 움직임의 성격이 무엇이고, 위험자산에 어떤 환경인가' 만 쓴다.

지어낸 데이터가 화면에 오르지 않게
------------------------------------
1. 컨텍스트는 이 모듈이 결정적으로 만든다. 엔진 값 · 출처 확인된 이벤트 파일 · 수집된 뉴스 외에는 넣지 않는다.
2. 결측 · 지연(STALE) 계열은 값 대신 상태로 넘기고, 마지막 관측일을 함께 준다 — 시점이 다른 자산을 같은 날로 읽지 않게.
3. 출력의 모든 숫자는 컨텍스트 숫자(반올림 허용)와 대조한다. 금지어(직접 추천 · 확률 · 단정 전망) · 상투 문구 ·
   인과 단정 · 문장 수를 검사한다. 하나라도 걸리면 문제를 알려주고 한 번 더 쓰게 하고, 그래도 안 되면 규칙 기반 문장으로 돌아간다.
4. 어떤 실패도 예외로 새지 않는다. 규칙 기반 문장과 그 이유가 화면에 남고 정량 대시보드는 그대로 돈다.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from ..config.settings import CONFIG_DIR
from ..models.market import MarketSeries, MarketSnapshot
from ..models.rates_regime import MarketReadMeta, RatesRegime
from .client import LLMClient, LLMFailure

logger = logging.getLogger(__name__)

THEMES = ["term_premium", "fed", "inflation", "growth", "fiscal_supply", "liquidity", "risk_off", "oil", "fx", "credit"]
MOVE_QUALITY = ["growth_scare", "financial_conditions_easing", "disinflation_repricing", "flight_to_quality",
                "fiscal_supply_premium", "inflation_shock", "policy_repricing", "mixed", "unclear"]

SCHEMA: dict = {
    "type": "object",
    "properties": {
        "read": {"type": "string", "description": "화면에 보일 MARKET READ — 한국어 2~4문장"},
        "move_quality": {"type": "string", "enum": MOVE_QUALITY},
        "themes": {"type": "array", "items": {"type": "string", "enum": THEMES}},
        "regime_fit": {"type": "string", "enum": ["consistent", "partly_consistent", "inconsistent"]},
        "data_caveat": {"type": "string", "description": "지연·결측 때문에 해석에 단서가 필요하면 한 줄, 없으면 빈 문자열"},
    },
    "required": ["read", "move_quality", "themes", "regime_fit", "data_caveat"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 글로벌 매크로·금리 포트폴리오 매니저다. 운용역이 금리 탭 맨 위에서 3초 안에 읽는 MARKET READ 를 쓴다.
화면에는 이미 regime 판정, 금리 방향, 주도 driver 와 점수, 10년물 수준과 5일 변화, 커브·실질금리·기대인플레 칸, 이벤트 표가 있다.
당신의 글은 그 숫자를 문장으로 옮기는 것이 아니라, 지금 금리 움직임이 '어떤 성격의 움직임'이고 위험자산에 '어떤 환경'인지에 대한 투자 해석이다.

[생각하는 순서 — 화면에 이 구조를 쓰지 않는다]
A. 금리가 실제로 어떻게 움직였나: 어느 구간이 이끌었나(단기/장기), 실질금리 대 기대인플레 중 어디서 왔나, 커브 모양.
B. 왜 움직였나: 컨텍스트의 매크로 발표(실제치만), 정책 결정·톤, 뉴스 헤드라인 중 이 움직임과 시점·방향이 맞는 것. 맞지 않으면 원인을 지어내지 않는다.
C. 시장이 어떻게 반응했나(가장 중요): 주식(지수·성장주·반도체·은행·경기민감 대 방어), 달러·원화·엔, 금, 원유·구리, 변동성(VIX·MOVE), 하이일드 스프레드.
   DATA → MARKET REACTION 순서로 본다. 발표 자체보다 시장이 그것을 어떻게 받아들였는지가 해석의 중심이다.
D. 움직임의 성격 판정: 성장 우려 / 금융여건 완화 / 디스인플레이션 재평가 / 안전자산 선호 / 재정·공급 프리미엄 / 물가 충격 / 정책 경로 재평가 / 혼재.
   regime 모델의 판정을 그대로 반복하지 말고, cross-asset 과 매크로가 그 판정과 맞는지·어긋나는지를 대조한다. 어긋나면 그 점이 해석의 핵심이다.
E. 위험자산 환경: 이 성격의 금리 움직임이 주식·크레딧·밸류에이션에 우호적인지, 부담인지, 선별적인지.
F. 다음 확인 지점: 꼭 필요할 때만 한 구절. 컨텍스트의 예정 이벤트 중 해석을 바꿀 수 있는 것만.

[주제 선택]
기간 프리미엄 · Fed 경로 · 물가 · 성장 · 재정/공급 · 유동성 · 위험회피 · 유가 · 달러/환율 · 크레딧 중 지금 가장 관련 있는 1~3개만 골라 쓴다.
정책(Fed·해외 중앙은행)은 지금 움직임과 관련 있을 때만 언급한다. 매번 같은 주제를 나열하지 않는다.

[쓰는 법]
- 한국어 평서문 2~4문장. 불릿·제목·마크다운·줄바꿈 없이 문장으로만.
- 숫자는 꼭 필요한 1~3개만, 컨텍스트에 있는 값 그대로(반올림만 허용). 화면에 이미 보이는 숫자(displayed_elsewhere)는 다시 쓰지 않는다.
- 인과를 단정하지 않는다. '~에 더 부합한다', '~에 가깝다', '현재까지는 ~로 읽힌다', '신호가 엇갈린다' 처럼 근거의 강도만큼만 말한다.
- 마지막 문장은 이 금리 환경이 위험자산에 어떤 환경인지로 맺는다(우호적·부담·선별적 등). 매수·매도·비중 확대/축소 같은 직접 추천은 하지 않는다.
- '확률', '전망' 이라는 말을 쓰지 않는다. 미래 가격을 예측하지 않는다.
- 다음 상투 문구를 쓰지 않는다: '주된 원인은 ~입니다', '아직 확인되지 않았습니다', '반대 방향으로 뚜렷한 driver 는 없습니다',
  '시장을 계속 모니터링해야 합니다', '향후 추이를 지켜볼 필요가 있습니다' 및 같은 뜻의 변형.
- 고정된 문장 틀을 쓰지 않는다. 매번 그날의 데이터에서 가장 중요한 대조점부터 시작한다.

[데이터 정직성]
- 컨텍스트에 없는 데이터·사건·발언·수치를 상상하지 않는다. 결측(MISSING) 계열은 없는 것으로 다룬다(0 이 아니다).
- STALE 이거나 마지막 관측일이 다른 자산과 다르면 같은 날의 반응으로 묶지 않는다. 해석에 영향이 크면 data_caveat 에 한 줄로 적는다.
- term_premium_proxy 는 모델 점수다. 기간 프리미엄 추정치(예: ACM)를 본 것처럼 쓰지 않는다.
- 뉴스는 제목·요약에 적힌 사실만 쓴다. 기사가 말하지 않은 인과를 붙이지 않는다.

[출력 필드]
read: 화면에 보일 문장. move_quality: D 의 판정. themes: 고른 주제 1~3개. regime_fit: regime 모델 판정과 실제 cross-asset·매크로가 맞는 정도.
data_caveat: 필요할 때만 한 줄, 아니면 빈 문자열.
"""


@lru_cache(maxsize=4)
def _load(config_dir: Path | None) -> dict:
    return yaml.safe_load(((config_dir or CONFIG_DIR) / "rates_read.yaml").read_text(encoding="utf-8")) or {}


def load_rates_read_config(config_dir: Path | None = None) -> dict:
    return _load(config_dir)


# ── 컨텍스트 ──────────────────────────────────────────────
def _r(v: float | None, nd: int) -> float | None:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


def _last(series: Mapping[str, MarketSeries], iid: str) -> tuple[float | None, datetime | None]:
    s = series.get(iid)
    if s is None or not s.values:
        return None, None
    for t, v in zip(reversed(s.timestamps), reversed(s.values)):
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            return float(v), t
    return None, None


def _status(last: datetime | None, as_of: datetime, stale_days: int, flagged: bool) -> str:
    if last is None:
        return "MISSING"
    if flagged or (as_of.date() - last.date()).days > stale_days:
        return "STALE"
    return "OK"


def _row(iid: str, label: str, market: MarketSnapshot, series: Mapping[str, MarketSeries], as_of: datetime, stale_days: int,
         kinds: Mapping[str, str]) -> dict:
    f = market.features.get(iid)
    level, last = _last(series, iid)
    if f is None and level is None:
        return {"id": iid, "label": label, "status": "MISSING"}
    if f is not None and f.meta is not None and f.meta.as_of is not None:
        last = f.meta.as_of
    st = _status(last, as_of, stale_days, bool(f is not None and f.meta is not None and f.meta.is_stale))
    is_level = kinds.get(iid) == "level"
    unit = "bp" if is_level else "%"
    row: dict[str, Any] = {"id": iid, "label": label, "status": st, "last_obs": last.date().isoformat() if last else None,
                           "level": _r(level, 2), "chg_unit": unit}
    if f is not None:
        nd = 0 if is_level else 2
        row.update({"chg_1d": _r(f.ret_1d, nd), "chg_5d": _r(f.ret_5d, nd), "chg_20d": _r(f.ret_20d, nd), "z_1d": _r(f.z_1d, 1), "z_5d": _r(f.z_5d, 1)})
    return row


def _spread(series: Mapping[str, MarketSeries], a: str, b: str) -> dict:
    """b − a (bp). 두 계열이 같은 날 값을 가진 날만 쓴다."""
    sa, sb = series.get(a), series.get(b)
    if sa is None or sb is None:
        return {"status": "MISSING"}
    da = {t.date(): v for t, v in zip(sa.timestamps, sa.values) if v is not None}
    db = {t.date(): v for t, v in zip(sb.timestamps, sb.values) if v is not None}
    days = sorted(set(da) & set(db))
    if not days:
        return {"status": "MISSING"}
    sp = [(db[d] - da[d]) * 100.0 for d in days]
    out: dict[str, Any] = {"level_bp": _r(sp[-1], 0), "last_obs": days[-1].isoformat()}
    if len(sp) > 1:
        out["chg_1d_bp"] = _r(sp[-1] - sp[-2], 0)
    if len(sp) > 5:
        out["chg_5d_bp"] = _r(sp[-1] - sp[-6], 0)
    return out


def _news(events: Iterable[Any], as_of: datetime, cfg: Mapping) -> list[dict]:
    nc = cfg.get("news") or {}
    themes = set(nc.get("themes") or []); types = set(nc.get("event_types") or [])
    since = as_of - timedelta(hours=float(nc.get("lookback_hours", 48)))
    rows = []
    for e in events:
        ts = getattr(e, "timestamp", None)
        if ts is None or ts < since or ts > as_of + timedelta(hours=1):
            continue
        et = getattr(getattr(e, "event_type", None), "value", getattr(e, "event_type", ""))
        if not (set(getattr(e, "themes", []) or []) & themes or et in types):
            continue
        bonus = float(nc.get("priority_bonus", 0)) if set(getattr(e, "themes", []) or []) & set(nc.get("priority_themes") or []) else 0.0
        rows.append((float(getattr(e, "impact_score", 0) or 0) + bonus, ts, e))
    rows.sort(key=lambda x: (-x[0], -x[1].timestamp()))
    n = int(nc.get("reason_chars", 220))
    return [{"time_utc": ts.strftime("%Y-%m-%d %H:%M"), "source": getattr(e, "source", ""), "title": getattr(e, "event", ""),
             "summary": str(getattr(e, "reason", "") or "")[:n], "themes": list(getattr(e, "themes", []) or [])}
            for _imp, ts, e in rows[: int(nc.get("limit", 10))]]


def build_context(regime: RatesRegime, market: MarketSnapshot, series: Mapping[str, MarketSeries], *, news: Iterable[Any] = (),
                  instrument_kinds: Mapping[str, str] | None = None, as_of: datetime | None = None, cfg: Mapping | None = None) -> dict:
    """LLM 에 넘길 사실 전부. 여기 없는 숫자는 MARKET READ 에 나올 수 없다."""
    cfg = cfg or load_rates_read_config()
    as_of = as_of or regime.as_of
    sd = int(cfg.get("stale_days", 2))
    kinds = dict(instrument_kinds or {})
    rc = cfg.get("rates") or {}

    def rows(ids: Sequence, labels: Mapping[str, str] | None = None) -> list[dict]:
        return [_row(i, (labels or {}).get(i, i), market, series, as_of, sd, kinds) for i in ids]

    tp = next((d for d in regime.drivers if d.id == rc.get("term_premium_driver", "term_premium")), None)
    rates = {
        "tenors": rows(rc.get("tenors", [])),
        "curve": {k: _spread(series, v[0], v[1]) for k, v in (rc.get("curve") or {}).items()},
        "real_yield": rows(rc.get("real", [])),
        "breakeven": rows(rc.get("breakeven", [])),
        "term_premium_proxy": None if tp is None else {"model_score": _r(tp.score, 0), "status": tp.status,
                                                       "note": "엔진 driver 점수(−100 하락 압력 … +100 상승 압력). 기간 프리미엄 직접 추정치가 아니다."},
        "decomposition": [{"tenor": d.tenor, "window_days": d.window_days, "nominal_bp": _r(d.nominal_bp, 0), "breakeven_bp": _r(d.breakeven_bp, 0),
                           "real_measured_bp": _r(d.real_measured_bp, 0)} for d in (regime.decomposition or [])],
    }
    rm = regime.rate_move
    reg = {
        "label": regime.regime_label, "headline": regime.headline,
        "rate_direction": rm.direction, "signal_strength": regime.signal_strength_label, "inflation_status": regime.inflation_status,
        "curve_shape": regime.curve.shape, "curve_lead": regime.curve.lead,
        "drivers": [{"id": d.id, "label": d.label, "score": _r(d.score, 0), "status": d.status} for d in regime.drivers],
        "dominant": regime.dominant, "margin_vs_second": _r(regime.margin, 0),
        "confirmations": [{"label": c.label, "status": c.status, "note": c.note} for c in regime.confirmations],
        "divergences": [{"label": d.label, "why": d.why} for d in regime.divergences],
    }
    ev = regime.events
    macro: dict[str, Any] = {"releases": [], "policy": [], "upcoming": [], "missing": []}
    if ev is not None:
        for x in sorted(ev.releases, key=lambda r: r.date, reverse=True)[: int(cfg.get("releases_limit", 5))]:
            macro["releases"].append({
                "name": x.name, "period": x.period, "date": x.date.isoformat(), "surprise": x.surprise,
                "actuals": [{"label": m.label, "actual": m.actual, "consensus": m.consensus, "prior": m.prior, "unit": m.unit}
                            for m in x.measures if m.actual is not None],
                "rates_reaction_bp": {"US2Y": _r(x.reaction.us2y_bp, 0), "US10Y": _r(x.reaction.us10y_bp, 0), "date": x.reaction.date.isoformat() if x.reaction.date else None},
            })
        for p in ev.policy:
            macro["policy"].append({"bank": p.bank, "date": p.date.isoformat(), "decision": p.decision_label, "tone": p.tone,
                                    "rate": p.current_rate, "line": p.line, "next_meeting": p.next_meeting.isoformat() if p.next_meeting else None})
        for u in ev.upcoming[: int(cfg.get("upcoming_limit", 5))]:
            macro["upcoming"].append({"date": u.date.isoformat(), "name": u.name, "importance": u.importance, "days_ahead": u.days_ahead})
        macro["missing"] = list(ev.missing)
    else:
        macro["note"] = "확인된 이벤트 파일 없음 — 매크로 발표·정책 결정은 컨텍스트에 없다"

    cross = [_row(str(c["id"]), str(c.get("label", c["id"])), market, series, as_of, sd, kinds) for c in cfg.get("cross_asset", [])]
    for rel in cfg.get("relative", []):
        fa, fb = market.features.get(str(rel["a"])), market.features.get(str(rel["b"]))
        if fa is None or fb is None or fa.ret_1d is None or fb.ret_1d is None:
            cross.append({"id": rel["id"], "label": rel["label"], "status": "MISSING"})
            continue
        cross.append({"id": rel["id"], "label": rel["label"], "status": "OK", "chg_unit": "%p",
                      "chg_1d": _r(fa.ret_1d - fb.ret_1d, 2), "chg_5d": None if fa.ret_5d is None or fb.ret_5d is None else _r(fa.ret_5d - fb.ret_5d, 2)})

    all_rows = rates["tenors"] + rates["real_yield"] + rates["breakeven"] + [r for r in cross if "last_obs" in r or r.get("status") == "MISSING"]
    stale = sorted({f"{r['id']}({r.get('last_obs') or '-'})" for r in all_rows if r.get("status") == "STALE"})
    missing = sorted({r["id"] for r in all_rows if r.get("status") == "MISSING"})
    rate_obs = sorted({r["last_obs"] for r in rates["tenors"] if r.get("last_obs")})
    eq_obs = sorted({r["last_obs"] for r in cross if r.get("last_obs") and r["id"] in ("SPX", "NDX")})
    timing = ""
    if rate_obs and eq_obs and rate_obs[-1] != eq_obs[-1]:
        timing = f"미국채 마지막 관측 {rate_obs[-1]}, 미국 주식 마지막 관측 {eq_obs[-1]} — 같은 날 반응으로 묶지 않는다"

    displayed = sorted({x for x in [_r(rm.level, 2), _r(rm.change_5d_bp, 0), _r(regime.margin, 0), _r(regime.signal_strength, 0)]
                        + [_r(d.score, 0) for d in regime.drivers] if x is not None})
    return {
        "as_of_utc": as_of.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "data_status": {"stale": stale, "missing": missing, "timing_note": timing,
                        "note": "STALE = 마지막 관측이 오래됨, MISSING = 계열 없음(0 아님). 변화 단위: level 계열은 bp, 가격 계열은 %."},
        "rates": rates,
        "regime_model": reg,
        "macro": macro,
        "cross_asset": cross,
        "headlines": _news(news, as_of, cfg),
        "displayed_elsewhere": {"numbers": displayed, "note": "화면 상단에 이미 보이는 숫자 — MARKET READ 에서 반복하지 않는다"},
    }


def context_text(ctx: Mapping) -> str:
    return json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))


# ── 검증 ──────────────────────────────────────────────────
_NUM = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*(?:\.\d+)?")
#: 날짜·기간 표현(14일 · 10월 · 3분기) — 숫자 개수에는 넣지 않고, 컨텍스트 대조만 한다
_DATE_SUFFIX = re.compile(r"\s*(?:월|일|년|분기|주)")
#: 만기·구간 이름(10년물 · 10Y · 2s10s · 1D) — 숫자가 아니라 이름이다
_TENOR_SUFFIX = re.compile(r"(?:년물|Y\b|s\d|D\b|M\b|Q\b|개월물)")
#: 지수 이름 속 숫자
_NAMES = re.compile(r"S&P\s?500|Nasdaq\s?100|나스닥\s?100|Russell\s?2000|러셀\s?2000|코스피\s?200|KOSPI\s?200")


def _numbers(text: str) -> list[tuple[str, int]]:
    """(정규화 숫자, 끝 위치). 부호·천단위 구분 무시."""
    out = []
    for m in _NUM.finditer(text):
        tok = m.group(0).lstrip("+-−").replace(",", "")
        if tok:
            out.append((tok, m.end()))
    return out


def _context_numbers(ctx_text: str) -> list[float]:
    vals = []
    for tok, _end in _numbers(ctx_text):
        try:
            vals.append(abs(float(tok)))
        except ValueError:
            pass
    return vals


def _matches(tok: str, pool: Sequence[float]) -> bool:
    nd = len(tok.split(".")[1]) if "." in tok else 0
    v = abs(float(tok))
    return any(abs(round(c, nd) - v) < 1e-9 for c in pool)


def number_check(text: str, ctx: Mapping) -> tuple[int, list[str], list[str]]:
    """(센 숫자 개수, 컨텍스트에 없는 숫자, 화면에 이미 보이는 소수 반복)."""
    body = _NAMES.sub("§", text)
    pool = _context_numbers(context_text(ctx))
    displayed = [abs(float(x)) for x in ((ctx.get("displayed_elsewhere") or {}).get("numbers") or [])]
    counted, invented, repeated = 0, [], []
    for tok, end in _numbers(body):
        after = body[end:end + 4]
        if _TENOR_SUFFIX.match(after):
            continue
        if not _matches(tok, pool):
            invented.append(tok)
        if _DATE_SUFFIX.match(after):
            continue
        counted += 1
        if "." in tok and any(abs(float(tok) - d) < 1e-9 for d in displayed):
            repeated.append(tok)
    return counted, sorted(set(invented)), sorted(set(repeated))


def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _phrase_hits(text: str, v: Mapping) -> list[str]:
    out = []
    for group, why in (("forbidden", "직접 추천·확률·전망 표현"), ("filler", "정보 없는 상투 문구"), ("certainty", "인과 단정 표현")):
        hit = [w for w in v.get(group, []) if w.lower() in text.lower()]
        if hit:
            out.append(f"{why} 사용: {', '.join(hit)}")
    return out


def validate_read(read: str, ctx: Mapping, cfg: Mapping | None = None) -> list[str]:
    """문제 목록. 비어 있으면 통과."""
    cfg = cfg or load_rates_read_config()
    v = cfg.get("validate") or {}
    problems: list[str] = []
    text = (read or "").strip()
    if not text:
        return ["문장이 비어 있다"]
    if "\n" in text or re.search(r"^\s*[-*•#]", text):
        problems.append("줄바꿈·불릿·제목 없이 문장으로만 써야 한다")
    n = len(split_sentences(text))
    lo, hi = int(v.get("min_sentences", 2)), int(v.get("max_sentences", 4))
    if not lo <= n <= hi:
        problems.append(f"문장 수 {n} — {lo}~{hi}문장이어야 한다")
    if len(text) > int(v.get("max_chars", 460)):
        problems.append(f"길이 {len(text)}자 — {v.get('max_chars', 460)}자 이내로 줄여야 한다")
    problems += _phrase_hits(text, v)
    counted, invented, repeated = number_check(text, ctx)
    if counted > int(v.get("max_numbers", 3)):
        problems.append(f"숫자 {counted}개 — 꼭 필요한 {v.get('max_numbers', 3)}개 이내로")
    if invented:
        problems.append(f"컨텍스트에 없는 숫자: {', '.join(invented)}")
    if repeated:
        problems.append(f"화면에 이미 보이는 숫자 반복: {', '.join(repeated)}")
    return problems


# ── 생성 ──────────────────────────────────────────────────
def _user_message(ctx: Mapping, *, previous: str | None = None, problems: Sequence[str] = ()) -> str:
    msg = f"아래는 지금 시점의 컨텍스트(JSON)다. 이것만 근거로 MARKET READ 를 써라.\n\n{context_text(ctx)}"
    if previous is not None:
        msg += ("\n\n이전 답안이 화면 검증을 통과하지 못했다. 같은 해석을 유지할 필요는 없다 — 문제를 고쳐 다시 써라.\n"
                f"이전 답안: {previous}\n문제: " + " / ".join(problems))
    return msg


def normalize_output(data: Mapping, cfg: Mapping | None = None) -> dict:
    cfg = cfg or load_rates_read_config()
    themes = [t for t in (data.get("themes") or []) if t in THEMES]
    themes = list(dict.fromkeys(themes))[:3]
    mq = data.get("move_quality") if data.get("move_quality") in MOVE_QUALITY else None
    fit = data.get("regime_fit") if data.get("regime_fit") in ("consistent", "partly_consistent", "inconsistent") else None
    tko = cfg.get("theme_ko") or {}; mko = cfg.get("move_quality_ko") or {}
    return {"read": re.sub(r"\s+", " ", str(data.get("read") or "")).strip(), "themes": themes, "themes_ko": [str(tko.get(t, t)) for t in themes],
            "move_quality": mq, "move_quality_ko": mko.get(mq) if mq else None, "regime_fit": fit,
            "data_caveat": re.sub(r"\s+", " ", str(data.get("data_caveat") or "")).strip()}


def check_output(out: Mapping, ctx: Mapping, cfg: Mapping | None = None) -> list[str]:
    cfg = cfg or load_rates_read_config()
    problems = validate_read(str(out.get("read") or ""), ctx, cfg)
    if not out.get("themes"):
        problems.append("themes 는 1~3개를 골라야 한다")
    cav = str(out.get("data_caveat") or "")
    if cav:
        _n, invented, _rep = number_check(cav, ctx)
        if invented:
            problems.append(f"data_caveat 에 컨텍스트에 없는 숫자: {', '.join(invented)}")
        problems += [f"data_caveat: {p}" for p in _phrase_hits(cav, cfg.get("validate") or {})]
    return problems


def generate_market_read(client: LLMClient, ctx: Mapping, *, cfg: Mapping | None = None, model: str | None = None) -> tuple[dict | None, list[str], str]:
    """
    (검증 통과 출력 | None, 경고 목록, 실패 사유). 실패 사유는 화면에 그대로 보인다 — 키·모델 이름은 담지 않는다.
    """
    cfg = cfg or load_rates_read_config()
    warnings: list[str] = []
    previous: str | None = None
    problems: list[str] = []
    for attempt in range(1 + int(cfg.get("retries_on_invalid", 1))):
        res = client.interpret(system=SYSTEM_PROMPT, user=_user_message(ctx, previous=previous, problems=problems), schema=SCHEMA,
                               effort=str(cfg.get("effort", "high")), max_tokens=int(cfg.get("max_tokens", 16000)),
                               timeout_sec=float(cfg.get("timeout_sec", 120)), model=model)
        if isinstance(res, LLMFailure):
            return None, warnings, failure_reason(res, client)
        out = normalize_output(res, cfg)
        problems = check_output(out, ctx, cfg)
        if not problems:
            return out, warnings, ""
        warnings.append(f"검증 {attempt + 1}회차: " + " / ".join(problems))
        previous = out["read"]
    return None, warnings, "AI 해석이 화면 검증(숫자 대조·금지어·문장 수)을 통과하지 못했다"


_KIND_KO = {"disabled": "LLM 비활성", "unavailable": "LLM 사용 불가", "auth": "API 인증 실패", "timeout": "응답 시간 초과",
            "rate_limit": "요청 한도 초과", "api": "API 오류", "refusal": "모델이 응답을 거절", "parse": "응답 형식 오류"}


def failure_reason(f: LLMFailure, client: LLMClient | None = None) -> str:
    """화면용 한 줄. 키·모델 이름·원문 오류는 담지 않는다."""
    base = _KIND_KO.get(f.kind, f.kind)
    detail = ((client.last_error if client is not None else None) or "") + " " + f.reason
    if "credit balance" in detail.lower():
        return f"{base} — API 계정 크레딧 부족"
    return base


# ── 적용 ──────────────────────────────────────────────────
def apply_read(regime: RatesRegime, *, out: Mapping | None, status: str, reason: str = "", generator: str = "none",
               warnings: Sequence[str] = (), ctx_as_of: datetime | None = None, now: datetime | None = None) -> RatesRegime:
    """regime.top 에 MARKET READ 를 붙인 사본. out 이 없으면 규칙 기반 문장을 그대로 두고 이유를 남긴다."""
    top = regime.top
    if top is None:
        return regime
    rule = top.market_read_meta.rule_read if top.market_read_meta and top.market_read_meta.rule_read else top.market_read
    now = now or datetime.now(timezone.utc)
    if out:
        meta = MarketReadMeta(source="llm", status="ok", generator=generator, reason=reason, themes=list(out["themes"]), themes_ko=list(out["themes_ko"]),  # type: ignore[arg-type]
                              move_quality=out.get("move_quality"), move_quality_ko=out.get("move_quality_ko"), regime_fit=out.get("regime_fit"),
                              data_caveat=str(out.get("data_caveat") or ""), generated_at=now, context_as_of=ctx_as_of, rule_read=rule, warnings=list(warnings))
        new_top = top.model_copy(update={"market_read": str(out["read"]), "market_read_meta": meta})
    else:
        # 규칙 기반에는 생성 시각을 남기지 않는다 — 같은 입력이면 같은 응답
        meta = MarketReadMeta(source="rule", status=status, reason=reason, context_as_of=ctx_as_of, rule_read=rule, warnings=list(warnings))  # type: ignore[arg-type]
        new_top = top.model_copy(update={"market_read": rule, "market_read_meta": meta})
    return regime.model_copy(update={"top": new_top})


def attach_market_read(regime: RatesRegime, *, client: LLMClient | None, market: MarketSnapshot, series: Mapping[str, MarketSeries],
                       news: Iterable[Any] = (), instrument_kinds: Mapping[str, str] | None = None, as_of: datetime | None = None,
                       session_read: Mapping | None = None, model: str | None = None) -> tuple[RatesRegime, dict]:
    """
    컨텍스트 → LLM → 검증 → 적용. (regime 사본, 컨텍스트). 어떤 실패도 예외로 새지 않는다.

    session_read: 파이프라인 API 호출이 실패한 날, 같은 컨텍스트 · 같은 프롬프트로 세션에서 만든 출력. 같은 검증을 통과해야만 쓰고,
    화면에는 generator=session 과 API 실패 사유가 함께 남는다.
    """
    if regime.top is None:
        return regime, {}
    cfg = load_rates_read_config()
    model = model or os.getenv("MARKETPULSE_RATES_READ_MODEL") or None  # 없으면 클라이언트 기본 모델
    try:
        ctx = build_context(regime, market, series, news=news, instrument_kinds=instrument_kinds, as_of=as_of, cfg=cfg)
    except Exception:
        logger.exception("MARKET READ 컨텍스트 구성 실패 — 규칙 기반 문장 유지")
        return apply_read(regime, out=None, status="fallback", reason="컨텍스트 구성 실패"), {}
    ctx_as_of = as_of or regime.as_of
    if client is None or not client.enabled:
        reason = "LLM 비활성 — 키 없음 또는 설정 off"
        warnings: list[str] = []
    else:
        out, warnings, reason = generate_market_read(client, ctx, cfg=cfg, model=model)
        if out is not None:
            return apply_read(regime, out=out, status="ok", generator="api", warnings=warnings, ctx_as_of=ctx_as_of), ctx
    if session_read is not None:
        out = normalize_output(session_read, cfg)
        problems = check_output(out, ctx, cfg)
        if not problems:
            return apply_read(regime, out=out, status="ok", generator="session", reason=f"API 호출 실패({reason}) — 같은 컨텍스트·프롬프트·검증으로 세션 생성",
                              warnings=warnings, ctx_as_of=ctx_as_of), ctx
        warnings = warnings + ["세션 생성본 검증 실패: " + " / ".join(problems)]
    return apply_read(regime, out=None, status="fallback", reason=reason, warnings=warnings, ctx_as_of=ctx_as_of), ctx
