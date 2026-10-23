"""
반도체 사이클 탭 MARKET READ (2026-10-23) — 메모리 업황 해석 2~4문장.

역할 분담은 금리 탭 MARKET READ(rates_read)와 같다. 국면 · 증거 점수 · 프리미엄 · 수출 나우캐스트 · 주가 확인은 정량 엔진
(engines/semiconductor_cycle)이 이미 계산했고, LLM 은 그것을 바꾸지 않고 '지금 업황의 성격' 만 쓴다.
컨텍스트는 엔진 결과에서 결정적으로 만든다. 출력의 모든 숫자는 컨텍스트 숫자와 대조하고 금지어(직접 추천 · 확률 · 전망) ·
상투 문구 · 인과 단정 · 문장 수를 검사한다. 실패하면 API → 세션 생성본(같은 컨텍스트·프롬프트·검증) → 규칙 기반 문장 순서로 내려가고,
어떤 실패도 예외로 새지 않는다(정량 화면은 그대로).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .rates_read import _NUM, _matches, _phrase_hits, split_sentences

logger = logging.getLogger(__name__)

THEMES = ["spot_strength", "premium", "contract_lag", "hbm_allocation", "export", "equity_divergence", "inventory", "data_gap"]
THEME_KO = {"spot_strength": "현물 강세", "premium": "Spot Premium", "contract_lag": "계약가 지연", "hbm_allocation": "HBM 캐파 배분",
            "export": "수출", "equity_divergence": "주가 괴리", "inventory": "재고", "data_gap": "데이터 공백"}

SCHEMA: dict = {
    "type": "object",
    "properties": {
        "read": {"type": "string", "description": "화면에 보일 MARKET READ — 한국어 2~4문장"},
        "themes": {"type": "array", "items": {"type": "string", "enum": THEMES}},
        "data_caveat": {"type": "string", "description": "이력 부족·오래된 계약가 등 단서가 필요하면 한 줄, 없으면 빈 문자열"},
    },
    "required": ["read", "themes", "data_caveat"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 메모리 반도체 업황을 보는 섹터 포트폴리오 매니저다. 반도체 사이클 탭 맨 위의 MARKET READ 를 쓴다.
화면에는 이미 국면 판정(STRONG UPSWING … DEEP DOWNTURN), 신뢰도, 증거 칩, 제품별 가격·변화율, Spot Premium, 수출 나우캐스트, 주가 확인 표가 있다.
당신의 글은 그 숫자를 옮기는 것이 아니라 '지금 메모리 업황이 어떤 성격인가' 에 대한 해석이다.

[생각하는 순서 — 화면에 이 구조를 쓰지 않는다]
A. 가격: 어느 제품(DDR5 / DDR4 / NAND)이 끌고 있나, 현물이 계약가보다 높은가(Spot Premium)와 그 방향.
B. 전이: 현물 강세가 계약가 → ASP → 수출 → 매출로 넘어가고 있는 증거가 있나. 계약가가 오래됐거나 비교가 proxy 면 그 한계를 반영한다.
C. 공급: HBM 이 캐파를 가져가 범용 DRAM 을 조이는 증거(앵커·보도)가 있나.
D. 확인: 수출 나우캐스트와 메모리 주가가 가격 방향을 확인하는가, 어긋나는가. 어긋나면 그 점이 해석의 핵심이다.
E. 이력이 짧거나 데이터가 비면(NO DATA) 그만큼 판단을 낮춘다. 없는 데이터를 있는 것처럼 쓰지 않는다.

[쓰는 법]
- 한국어 평서문 2~4문장. 불릿·제목·마크다운·줄바꿈 없이.
- 숫자는 꼭 필요한 1~3개만, 컨텍스트 값 그대로(반올림만 허용). displayed_elsewhere 의 숫자는 다시 쓰지 않는다.
- 인과를 단정하지 않는다('~에 가깝다', '~로 읽힌다', '신호가 엇갈린다').
- 매수·매도·비중 같은 직접 추천, '확률', '전망', 목표가, 미래 가격 예측을 쓰지 않는다.
- '모니터링해야', '지켜볼 필요', '향후 추이' 같은 상투 문구를 쓰지 않는다. 매번 그날 가장 중요한 대조점부터 시작한다."""


def _r(v: Any, nd: int = 1) -> Any:
    return None if v is None else round(float(v), nd)


def build_context(cyc: Mapping[str, Any]) -> dict:
    """LLM 에 넘길 사실 전부. 여기 없는 숫자는 MARKET READ 에 나올 수 없다."""
    reg = cyc.get("regime") or {}
    prices = [{"product": p["label"], "tier": p["tier"], "price_usd": _r(p.get("current"), 3), "updated": (p.get("updated_at") or "")[:10],
               "chg_1w_pct": _r(p.get("change_1w")), "chg_1m_pct": _r(p.get("change_1m")), "chg_3m_pct": _r(p.get("change_3m")),
               "chg_since_first_pct": _r(p.get("since_first")), "since": p.get("since_first_from"), "observations": p.get("observations"),
               "momentum_state": p.get("momentum_state") or "NO DATA"}
              for p in cyc.get("memory_prices") or [] if p.get("available")]
    prem = [{"spot": x["spot_label"], "contract": x.get("contract_label"), "comparability": x.get("comparability"), "premium_pct": _r(x.get("current")),
             "direction": x.get("direction"), "contract_anchor_month": x.get("contract_anchor_label"), "contract_stale": x.get("contract_stale"),
             "proxy": x.get("proxy", False)} if x.get("available") else {"spot": x["spot_label"], "status": "NOT COMPUTED", "reason": x.get("reason")}
            for x in cyc.get("spot_premium") or []]
    ex = cyc.get("export_nowcast") or {}
    now = ex.get("nowcast") or {}
    export = {"available": bool(ex.get("available")), "latest": ex.get("latest_scope_label"), "latest_yoy_pct": _r(ex.get("latest_yoy"), 1),
              "latest_daily_avg_yoy_pct": _r(ex.get("latest_daily_avg_yoy"), 1), "nowcast_yoy_mid_pct": _r(now.get("yoy_mid"), 0),
              "nowcast_yoy_range_pct": [_r(now.get("yoy_low"), 0), _r(now.get("yoy_high"), 0)] if now else None,
              "prev_month_yoy_pct": _r(ex.get("prev_month_yoy"), 0), "momentum": ex.get("momentum"), "price_vs_volume": ex.get("price_vs_volume")}
    eq = cyc.get("equity_confirmation") or {}
    hbm = cyc.get("hbm_supply") or {}
    news = [{"category": n["category"], "headline": n["headline"], "direction": n["direction"]} for n in (cyc.get("news") or [])[:6]]
    displayed = sorted({x for x in [_r(reg.get("composite"), 0), _r(reg.get("confidence"), 0)] + [_r(c.get("score"), 0) for c in reg.get("components") or []] if x is not None})
    return {
        "as_of_utc": str(cyc.get("as_of", ""))[:16],
        "regime_model": {"state": reg.get("label"), "composite": _r(reg.get("composite"), 0), "confidence": _r(reg.get("confidence"), 0), "coverage": reg.get("coverage"),
                         "evidence": [{"key": c["key"], "score": _r(c.get("score"), 0)} for c in reg.get("components") or []],
                         "chips": {c["label"]: c["value"] for c in reg.get("chips") or []}},
        "memory_prices": prices, "spot_premium": prem, "breadth": {k: (cyc.get("breadth") or {}).get(k) for k in ("state", "positive_momentum", "products_in_premium")},
        "contract": {"trend": (cyc.get("contract") or {}).get("trend"), "stale": (cyc.get("contract") or {}).get("stale"),
                     "rows": [{"item": r["label"], "avg_usd": r["avg"], "period": r["period"][:7], "chg_pct": r["change_pct"]} for r in (cyc.get("contract") or {}).get("rows") or []][:4]},
        "hbm": {"pricing": hbm.get("pricing"), "capacity": hbm.get("capacity"),
                "anchors": [{"item": a["label"], "value": a.get("value"), "date": a.get("date"), "chg_pct": a.get("change_pct")} for a in hbm.get("anchors") or [] if a.get("available")]},
        "export": export,
        "equity": {"status": eq.get("status"), "stocks": [{"name": s["label"], "ret_1m_pct": _r(s.get("ret_1m"), 1), "confirmation": s.get("confirmation")} for s in eq.get("stocks") or []]},
        "headlines": news,
        "data_gaps": [d["item"] for d in cyc.get("data_quality") or [] if d.get("status") == "UNAVAILABLE"],
        "displayed_elsewhere": {"numbers": displayed, "note": "화면 상단에 이미 보이는 숫자 — MARKET READ 에서 반복하지 않는다"},
    }


def context_text(ctx: Mapping) -> str:
    return json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))


#: 제품·기간 이름 속 숫자(DDR5 · 16Gb · 512Gb · HBM3E · 1~20일 · 1M) — 숫자가 아니라 이름이다
_NAMES = re.compile(r"DDR\d|LPDDR\d|HBM\d\w*|\d+\s?(?:Gb|GB|TB)\b|\d+\s?~\s?\d+\s?일|\b\d+[DWMY]\b|SK\s?hynix|DXI")
_DATE_SUFFIX = re.compile(r"\s*(?:월|일|년|분기|주)")


def number_check(text: str, ctx: Mapping) -> tuple[int, list[str], list[str]]:
    body = _NAMES.sub("§", text)
    pool = [abs(float(m.group(0).lstrip("+-−").replace(",", ""))) for m in _NUM.finditer(_NAMES.sub("§", context_text(ctx))) if m.group(0).lstrip("+-−").replace(",", "")]
    displayed = [abs(float(x)) for x in ((ctx.get("displayed_elsewhere") or {}).get("numbers") or [])]
    counted, invented, repeated = 0, [], []
    for m in _NUM.finditer(body):
        tok = m.group(0).lstrip("+-−").replace(",", "")
        if not tok:
            continue
        if not _matches(tok, pool):
            invented.append(tok)
        if _DATE_SUFFIX.match(body[m.end():m.end() + 4]):
            continue
        counted += 1
        if any(abs(float(tok) - d) < 1e-9 for d in displayed):
            repeated.append(tok)
    return counted, sorted(set(invented)), sorted(set(repeated))


def validate_read(read: str, ctx: Mapping, cfg: Mapping) -> list[str]:
    v = cfg.get("validate") or {}
    text = (read or "").strip()
    if not text:
        return ["문장이 비어 있다"]
    problems: list[str] = []
    if "\n" in text or re.search(r"^\s*[-*•#]", text):
        problems.append("줄바꿈·불릿·제목 없이 문장으로만 써야 한다")
    n = len(split_sentences(text))
    lo, hi = int(v.get("min_sentences", 2)), int(v.get("max_sentences", 4))
    if not lo <= n <= hi:
        problems.append(f"문장 수 {n} — {lo}~{hi}문장이어야 한다")
    if len(text) > int(v.get("max_chars", 480)):
        problems.append(f"길이 {len(text)}자 — {v.get('max_chars', 480)}자 이내로")
    problems += _phrase_hits(text, v)
    counted, invented, repeated = number_check(text, ctx)
    if counted > int(v.get("max_numbers", 3)):
        problems.append(f"숫자 {counted}개 — {v.get('max_numbers', 3)}개 이내로")
    if invented:
        problems.append(f"컨텍스트에 없는 숫자: {', '.join(invented)}")
    if repeated:
        problems.append(f"화면에 이미 보이는 숫자 반복: {', '.join(repeated)}")
    return problems


def normalize_output(data: Mapping) -> dict:
    themes = list(dict.fromkeys(t for t in (data.get("themes") or []) if t in THEMES))[:3]
    return {"read": re.sub(r"\s+", " ", str(data.get("read") or "")).strip(), "themes": themes, "themes_ko": [THEME_KO[t] for t in themes],
            "data_caveat": re.sub(r"\s+", " ", str(data.get("data_caveat") or "")).strip()}


def check_output(out: Mapping, ctx: Mapping, cfg: Mapping) -> list[str]:
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


# ── 규칙 기반 문장 ─────────────────────────────────────────
def rule_read(cyc: Mapping[str, Any]) -> str:
    """LLM 이 없을 때의 결정적 문장 — 그날 증거에서 고른다(고정 템플릿 하나가 아니라 증거 유무로 갈린다)."""
    reg = cyc.get("regime") or {}
    prem = [x for x in cyc.get("spot_premium") or [] if x.get("available")]
    high = [x for x in prem if x.get("comparability") == "HIGH"]
    ex = cyc.get("export_nowcast") or {}
    eq = cyc.get("equity_confirmation") or {}
    con = cyc.get("contract") or {}
    s: list[str] = []
    if high:
        top = max(high, key=lambda x: x.get("current") or 0)
        s.append(f"범용 DRAM 현물이 계약가({top['contract_anchor_label']} 기준)보다 높은 {top['state'].replace('_', ' ')} 구간이고, 프리미엄 방향은 {top['direction']} 이다.")
    elif prem:
        s.append("비교 가능한 계약가가 proxy 뿐이라 현물 프리미엄은 참고 수준으로만 읽힌다.")
    else:
        s.append("현물과 비교할 계약가가 없어 Spot Premium 은 계산하지 않았다.")
    if ex.get("available") and ex.get("latest_yoy") is not None:
        s.append(f"수출은 {ex.get('latest_scope_label')} 기준 전년 대비 증가가 이어지고 있어 가격 강세가 달러 매출로 넘어가는 신호와 맞는다." if ex["latest_yoy"] > 0
                 else f"수출은 {ex.get('latest_scope_label')} 기준 전년 대비 감소로 가격 신호와 엇갈린다.")
    if con.get("stale"):
        s.append("다만 공개 계약가가 오래돼 현물 강세가 계약가로 전이됐는지는 아직 확인 전 단계다.")
    elif eq.get("status") == "DIVERGENCE":
        s.append(str(eq.get("read") or ""))
    if len(s) < 2:
        s.append(f"종합 국면은 {reg.get('label', 'NO DATA')} 로 판정되지만 증거 확보 비율이 낮다.")
    return " ".join(s[:4])


# ── 생성 · 적용 ──────────────────────────────────────────
def _user_message(ctx: Mapping, *, previous: str | None = None, problems: Sequence[str] = ()) -> str:
    msg = f"아래는 지금 시점의 컨텍스트(JSON)다. 이것만 근거로 MARKET READ 를 써라.\n\n{context_text(ctx)}"
    if previous is not None:
        msg += f"\n\n이전 답안이 화면 검증을 통과하지 못했다. 문제를 고쳐 다시 써라.\n이전 답안: {previous}\n문제: " + " / ".join(problems)
    return msg


def generate(client, ctx: Mapping, cfg: Mapping) -> tuple[dict | None, list[str], str]:
    from .client import LLMFailure
    from .rates_read import failure_reason
    warnings: list[str] = []
    previous: str | None = None
    problems: list[str] = []
    for attempt in range(1 + int(cfg.get("retries_on_invalid", 1))):
        res = client.interpret(system=SYSTEM_PROMPT, user=_user_message(ctx, previous=previous, problems=problems), schema=SCHEMA,
                               effort=str(cfg.get("effort", "high")), max_tokens=int(cfg.get("max_tokens", 16000)), timeout_sec=float(cfg.get("timeout_sec", 120)))
        if isinstance(res, LLMFailure):
            return None, warnings, failure_reason(res, client)
        out = normalize_output(res)
        problems = check_output(out, ctx, cfg)
        if not problems:
            return out, warnings, ""
        warnings.append(f"검증 {attempt + 1}회차: " + " / ".join(problems))
        previous = out["read"]
    return None, warnings, "AI 해석이 화면 검증(숫자 대조·금지어·문장 수)을 통과하지 못했다"


def apply(cyc: dict, *, out: Mapping | None, status: str, reason: str = "", generator: str = "none", warnings: Sequence[str] = ()) -> dict:
    rule = rule_read(cyc)
    if out:
        cyc["market_read"] = {"read": out["read"], "source": "llm", "status": "ok", "generator": generator, "reason": reason, "themes": list(out["themes"]),
                              "themes_ko": list(out["themes_ko"]), "data_caveat": out.get("data_caveat", ""), "rule_read": rule, "warnings": list(warnings),
                              "generated_at": datetime.now(timezone.utc).isoformat() if generator == "api" else None}
    else:
        cyc["market_read"] = {"read": rule, "source": "rule", "status": status, "generator": "none", "reason": reason, "themes": [], "themes_ko": [],
                              "data_caveat": "", "rule_read": rule, "warnings": list(warnings), "generated_at": None}
    return cyc


def attach_read(cyc: dict, session_read: Mapping | None = None, *, client=None, cfg: Mapping | None = None) -> dict:
    """API → 세션 생성본 → 규칙 기반. 어떤 실패도 예외로 새지 않는다."""
    if cfg is None:
        from ..engines.semiconductor_cycle import load_config
        cfg = load_config().get("read") or {}
    try:
        ctx = build_context(cyc)
    except Exception:
        logger.exception("반도체 MARKET READ 컨텍스트 구성 실패 — 규칙 기반 문장")
        return apply(cyc, out=None, status="fallback", reason="컨텍스트 구성 실패")
    warnings: list[str] = []
    reason = "LLM 비활성 — 키 없음 또는 설정 off"
    if client is not None and getattr(client, "enabled", False):
        try:
            out, warnings, reason = generate(client, ctx, cfg)
        except Exception:
            logger.exception("반도체 MARKET READ 생성 실패")
            out, reason = None, "AI 해석 생성 중 오류"
        if out is not None:
            return apply(cyc, out=out, status="ok", generator="api", warnings=warnings)
    if session_read is not None:
        out = normalize_output(session_read)
        problems = check_output(out, ctx, cfg)
        if not problems:
            return apply(cyc, out=out, status="ok", generator="session", reason=f"API 호출 실패({reason}) — 같은 컨텍스트·프롬프트·검증으로 세션 생성", warnings=warnings)
        warnings = warnings + ["세션 생성본 검증 실패: " + " / ".join(problems)]
    return apply(cyc, out=None, status="fallback", reason=reason, warnings=warnings)
