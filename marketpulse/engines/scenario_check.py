"""
시나리오 점검 엔진 — 모의 시나리오의 충격 서명(shocks)을 실데이터 z 에 대어 본다.

규칙(config/scenario_checks.yaml):
  - 충격 조건(|기대 z| ≥ quiet_abs): 실제가 같은 방향이면 ratio = min(1, |실제|/|기대|), 반대면 0.
    ratio ≥ agree_ratio 면 agree, 아니면 weak. 실제는 하루·5일 z 중 같은 방향으로 큰 쪽.
  - 조용 조건(|기대 z| < quiet_abs): |실제| ≤ tolerance 면 1, tolerance ~ tolerance+1 사이는 선형 감소.
  - 일치도 = Σ(weight·ratio) / Σ(weight). 충격 조건의 weight 는 |기대 z|, 조용 조건은 quiet_weight.
  - 결측은 분모에서 뺀다 — 0 으로 치지 않는다.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from ..adapters.market.scenario import Scenario
from ..config.settings import CONFIG_DIR
from ..models.market import Instrument, MarketSnapshot
from ..models.scenario_check import ScenarioCheck, ScenarioCheckRow, ScenarioThemeRef
from ..models.state import MarketState, StateLabel
from ..models.theme import ThemeState

logger = logging.getLogger(__name__)
ENGINE_VERSION = "0.1.0"

LABEL_KO = {
    "RISK_ON": "Risk-On", "RISK_OFF": "Risk-Off", "GROWTH_SHOCK": "Growth Shock", "INFLATION_SHOCK": "Inflation Shock",
    "LIQUIDITY_STRESS": "Liquidity Stress", "POLICY_DRIVEN": "Policy Driven", "GEOPOLITICAL_RISK": "Geopolitical Risk",
    "NEUTRAL": "판정 없음",
}


@lru_cache(maxsize=4)
def _load(config_dir: Path | None) -> dict:
    path = (config_dir or CONFIG_DIR) / "scenario_checks.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_scenario_checks(config_dir: Path | None = None) -> dict:
    return _load(config_dir)


def reset_cache() -> None:
    _load.cache_clear()


#: 시장 층 밖의 z. (z_1d, z_5d) — 5일 z 가 없으면 None. 대체데이터·종목은 하루 z 만 있다.
ExtraZ = Mapping[str, tuple[float | None, float | None, str]]


def _fmt_row(r: ScenarioCheckRow) -> str:
    if r.layer == "theme":
        return f"{r.label} {r.used_z:+.0f}(기대 {r.expected_z:+.0f})"
    return f"{r.label} {r.used_z:+.1f}σ(기대 {r.expected_z:+.1f})"


def _pick(expected: float, z1: float | None, z5: float | None, windows: Sequence[int]) -> tuple[float | None, int | None]:
    """기대 방향으로 더 큰 창의 z. 둘 다 반대면 절댓값이 큰 쪽(반대 크기를 보이기 위해)."""
    cands: list[tuple[float, int]] = []
    if 1 in windows and z1 is not None:
        cands.append((z1, 1))
    if 5 in windows and z5 is not None:
        cands.append((z5, 5))
    if not cands:
        return None, None
    sign = 1.0 if expected >= 0 else -1.0
    same = [(z, w) for z, w in cands if z * sign > 0]
    if same:
        return max(same, key=lambda t: abs(t[0]))
    return max(cands, key=lambda t: abs(t[0]))


def check_scenario(
    scenario: Scenario,
    market: MarketSnapshot,
    state: MarketState,
    themes: Sequence[ThemeState],
    instruments_by_id: Mapping[str, Instrument],
    *,
    extra_z: ExtraZ | None = None,
    config_dir: Path | None = None,
) -> ScenarioCheck:
    cfg = load_scenario_checks(config_dir)
    th = cfg.get("thresholds", {})
    quiet_abs = float(th.get("quiet_abs", 0.3))
    quiet_tol = float(th.get("quiet_tolerance", 0.5))
    quiet_w = float(th.get("quiet_weight", 0.3))
    agree_ratio = float(th.get("agree_ratio", 0.5))
    windows = [int(w) for w in th.get("windows", [1, 5])]
    spec = (cfg.get("checks") or {}).get(scenario.name, {}) or {}
    label = StateLabel(spec["label"]) if spec.get("label") else None
    extra = extra_z or {}

    rows: list[ScenarioCheckRow] = []
    missing: list[str] = []
    num = den = 0.0
    counts = {"agree": 0, "weak": 0, "oppose": 0, "quiet_ok": 0, "quiet_broken": 0}
    for iid, expected in scenario.shocks.items():
        expected = float(expected)
        f = market.features.get(iid)
        if f is not None:
            z1, z5, layer = f.z_1d, f.z_5d, "market"
            name = instruments_by_id[iid].name if iid in instruments_by_id else iid
        elif iid in extra:
            z1, z5, layer = extra[iid][0], extra[iid][1], extra[iid][2]
            name = iid
        else:
            z1 = z5 = None
            layer = "market" if iid in instruments_by_id else "alternative"
            name = instruments_by_id[iid].name if iid in instruments_by_id else iid
        used, win = _pick(expected, z1, z5, windows)
        weight = abs(expected) if abs(expected) >= quiet_abs else quiet_w
        if used is None:
            missing.append(iid)
            rows.append(ScenarioCheckRow(instrument_id=iid, label=name, expected_z=expected, actual_z_1d=z1, actual_z_5d=z5,
                                         used_z=None, used_window=None, ratio=0.0, weight=weight, status="missing", layer=layer))  # type: ignore[arg-type]
            continue
        if abs(expected) < quiet_abs:
            over = max(0.0, abs(used) - quiet_tol)
            ratio = max(0.0, 1.0 - over)  # tolerance 를 1σ 넘으면 0
            status = "quiet_ok" if ratio >= agree_ratio else "quiet_broken"
        else:
            same = used * expected > 0
            ratio = min(1.0, abs(used) / abs(expected)) if same else 0.0
            status = "oppose" if not same else ("agree" if ratio >= agree_ratio else "weak")
        counts[status] += 1
        num += weight * ratio
        den += weight
        rows.append(ScenarioCheckRow(instrument_id=iid, label=name, expected_z=expected, actual_z_1d=z1, actual_z_5d=z5,
                                     used_z=used, used_window=win, ratio=round(ratio, 3), weight=weight, status=status, layer=layer))  # type: ignore[arg-type]
    # 테마 조건 — 가격 z 로는 못 잡는 서명(뉴스 톤·테마 가격 점수). 단위는 −100~+100 이지 z 가 아니다.
    theme_by_id = {t.theme_id: t for t in themes}
    for cond in spec.get("theme_conditions") or []:
        t = theme_by_id.get(str(cond.get("theme")))
        field = str(cond.get("field", "news_sentiment"))
        expected = float(cond.get("expected", 0.0))
        weight = float(cond.get("weight", 1.0))
        tol = cond.get("tolerance")
        actual = None if t is None else getattr(t, field, None)
        fname = "뉴스 톤" if field == "news_sentiment" else "가격 점수"
        rid = f"theme:{cond.get('theme')}:{field}"
        name = f"{t.name if t else cond.get('theme')} {fname}"
        if actual is None:
            missing.append(rid)
            rows.append(ScenarioCheckRow(instrument_id=rid, label=name, expected_z=expected, actual_z_1d=None, actual_z_5d=None, used_z=None,
                                         used_window=None, ratio=0.0, weight=weight, status="missing", layer="theme"))
            continue
        actual = float(actual)
        if tol is not None and expected == 0.0:
            over = max(0.0, abs(actual) - float(tol))
            ratio = max(0.0, 1.0 - over / float(tol))
            status = "quiet_ok" if ratio >= agree_ratio else "quiet_broken"
        else:
            same = actual * expected > 0
            ratio = min(1.0, abs(actual) / abs(expected)) if same else 0.0
            status = "oppose" if not same else ("agree" if ratio >= agree_ratio else "weak")
        counts[status] += 1
        num += weight * ratio
        den += weight
        rows.append(ScenarioCheckRow(instrument_id=rid, label=name, expected_z=expected, actual_z_1d=actual, actual_z_5d=None, used_z=actual,
                                     used_window=None, ratio=round(ratio, 3), weight=weight, status=status, layer="theme"))
    score = round(100.0 * num / den, 1) if den > 0 else 0.0
    match_label = next((str(b["label"]) for b in th.get("bands", []) if score >= float(b["min"])), "")

    # 판정 엔진 쪽 — 그 라벨의 가설과 require 룰
    hyp_score = req_expr = req_passed = req_obs = None
    if label is not None:
        for h in state.hypotheses:
            if h.label == label:
                hyp_score = round(h.score, 3)
                req = next((r for r in h.matched_rules if r.kind == "require"), None)
                if req is not None:
                    req_expr, req_passed, req_obs = req.expression, req.passed, req.observed
                break

    theme_refs = [ScenarioThemeRef(theme_id=t.theme_id, name=t.name, theme_score=round(t.theme_score, 1), news_sentiment=t.news_sentiment)
                  for t in themes if t.theme_id in (spec.get("themes") or [])]

    evaluated = len(rows) - len(missing)
    # 문장은 전부 위 숫자에서 나온다
    parts = [f"실데이터는 '{scenario.title or scenario.name}' 시나리오와 {score:.0f}% 닮았다({match_label})."]
    if evaluated:
        parts.append(f"서명 {len(rows)}개 중 {evaluated}개 평가 — 일치 {counts['agree']} · 미달 {counts['weak']} · 반대 {counts['oppose']}"
                     + (f" · 조용 {counts['quiet_ok']}/{counts['quiet_ok'] + counts['quiet_broken']}" if counts['quiet_ok'] + counts['quiet_broken'] else "")
                     + (f", 결측 {len(missing)}" if missing else "") + ".")
        top_agree = sorted((r for r in rows if r.status == "agree"), key=lambda r: -r.weight)[:3]
        top_oppose = sorted((r for r in rows if r.status == "oppose"), key=lambda r: -r.weight)[:3]
        if top_agree:
            parts.append("닮은 곳: " + ", ".join(_fmt_row(r) for r in top_agree) + ".")
        if top_oppose:
            parts.append("반대: " + ", ".join(_fmt_row(r) for r in top_oppose) + ".")
    else:
        parts.append("평가할 계열이 없다 — 이 시나리오의 서명은 지금 확보된 데이터 밖에 있다.")
    if theme_refs:
        parts.append("관련 테마(가격 점수 / 뉴스 톤): " + ", ".join(
            f"{t.name} {t.theme_score:+.0f} / {'없음' if t.news_sentiment is None else f'{t.news_sentiment:+.0f}'}" for t in theme_refs) + ".")
    if label == StateLabel.NEUTRAL:
        parts.append("평시는 어느 판정 룰(require)도 걸리지 않은 상태다"
                     + (" — 지금이 그렇다." if state.primary_label == StateLabel.NEUTRAL else f" — 지금은 {LABEL_KO[state.primary_label.value]} 룰이 걸려 있어 평시가 아니다."))
    elif label is not None:
        if hyp_score is None:
            parts.append(f"판정 엔진에는 {LABEL_KO[label.value]} 가설이 없다.")
        elif req_expr:
            parts.append(f"판정 룰: {LABEL_KO[label.value]} require '{req_expr}' {'통과' if req_passed else '실패'}"
                         + (f"(관측 {req_obs:+.2f})" if req_obs is not None else "") + f", 가설 점수 {hyp_score:.2f}.")
    parts.append(f"지금 판정은 {LABEL_KO[state.primary_label.value]} {state.confidence:.0f}%" + (" — 시나리오와 같다." if label == state.primary_label else "."))
    verdict = " ".join(parts)
    note = ("시나리오의 충격은 모의 데이터 마지막 봉의 목표 z 이고, 실데이터는 하루·5일 z 중 같은 방향으로 더 큰 쪽과 비교한다. "
            "일치도는 |기대 z| 를 가중치로 한 비율의 평균이며 결측은 분모에서 뺀다. 예측이 아니라 '지금 시장이 그 그림과 얼마나 닮았나' 다. "
            "판정은 여전히 state_rules 의 require 룰이 정한다 — 일치도가 높아도 require 가 안 걸리면 판정은 바뀌지 않는다.")
    return ScenarioCheck(
        name=scenario.name, title=scenario.title or scenario.name, description=scenario.description, as_of=market.as_of,
        label=label, focus=str(spec.get("focus", "rule")), factor=spec.get("factor"), commodities=[str(c) for c in (spec.get("commodities") or [])],  # type: ignore[arg-type]
        match_score=score, match_label=match_label, evaluated=evaluated,
        agree=counts["agree"], weak=counts["weak"], oppose=counts["oppose"], quiet_ok=counts["quiet_ok"], quiet_broken=counts["quiet_broken"],
        missing=missing, rows=rows, hypothesis_score=hyp_score, require_expression=req_expr, require_passed=req_passed,
        require_observed=req_obs, current_label=state.primary_label, current_confidence=state.confidence,
        themes=theme_refs, verdict=verdict, note=note,
    )


def check_scenarios(
    scenarios: Sequence[Scenario], market: MarketSnapshot, state: MarketState, themes: Sequence[ThemeState],
    instruments_by_id: Mapping[str, Instrument], *, extra_z: ExtraZ | None = None, config_dir: Path | None = None,
) -> list[ScenarioCheck]:
    cfg = load_scenario_checks(config_dir)
    order = list((cfg.get("checks") or {}).keys())
    by_name = {s.name: s for s in scenarios}
    out: list[ScenarioCheck] = []
    for name in order:
        sc = by_name.get(name)
        if sc is None:
            logger.warning("scenario_checks.yaml 의 %s 시나리오 파일이 없다", name)
            continue
        out.append(check_scenario(sc, market, state, themes, instruments_by_id, extra_z=extra_z, config_dir=config_dir))
    return out


def extra_z_from_investment(inv: object) -> dict[str, tuple[float | None, float | None, str]]:
    """Investment 층의 대체데이터·종목 하루 z. 5일 z 는 없다."""
    out: dict[str, tuple[float | None, float | None, str]] = {}
    for p in getattr(inv, "alternative", []) or []:
        if getattr(p, "z", None) is not None:
            out[p.id] = (float(p.z), None, "alternative")
    stocks = getattr(inv, "stocks", None) or {}
    for s in (stocks.values() if isinstance(stocks, dict) else stocks):
        row = getattr(s, "row", s)
        z = getattr(row, "z", None)
        sid = getattr(row, "stock_id", None) or getattr(s, "stock_id", None)
        if sid and z is not None:
            out[sid] = (float(z), None, "stock")
    return out
