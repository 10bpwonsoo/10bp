"""
MARKET LEADERSHIP → Leadership Intelligence (2026-09-30).

"무엇이 강한가" 에 더해 "왜 강한가 · 무엇이 확인하는가 · 지속 가능한가 · 어떤 종목으로 이어지는가 · 시장 전문가는 무엇을 보는가" 를
테마/섹터 행마다 만든다. 새 판정을 만들지 않는다 — 기존 값(1D z · 1주 상대 · breadth · 테마 뉴스 톤 · AI 세그먼트 · 종목 z · 관련 계열 z)을
config/cockpit.yaml leadership_intel 의 힌트(driver · links · risk · watch · stocks)와 합쳐 문장으로 만든다. 없는 데이터는 문장에서 빠진다.

SYSTEM VIEW(내부 데이터 해석)와 STREET VIEW(외부 리서치)는 절대 섞지 않는다. STREET VIEW 는 data/street_views/manual/*.json 에서
기관 · 발행일 · URL · 요약이 모두 확인된 것만 싣고(애널리스트 이름은 확인된 경우에만), 없으면 빈 목록이라 화면이 영역을 숨긴다.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..models.cockpit import ConfirmRow, KeyStock, LeaderRow, LeadershipDetail, StreetView

logger = logging.getLogger(__name__)

#: 상태 의미 — 리더(상승 방향)와 후미(하락 방향)를 따로 쓴다. 같은 CONFIRMED 라도 후미에서는 '광범위한 약세' 다.
STATUS_MEANING = {
    "PRICE": {"CONFIRMED": "하루 상승이 뚜렷", "PARTIAL": "단기 상승은 제한적", "UNCONFIRMED": "하루 움직임이 작음", "CONTRADICTED": "하루 가격은 반대 방향", "DATA MISSING": "가격 데이터 없음"},
    "RELATIVE": {"CONFIRMED": "시장 대비 강세", "PARTIAL": "시장 대비 소폭 우위", "UNCONFIRMED": "시장과 비슷", "CONTRADICTED": "시장 대비 약세", "DATA MISSING": "상대 데이터 없음"},
    "BREADTH": {"CONFIRMED": "상승이 종목 전반으로 확산", "PARTIAL": "일부 종목만 참여", "UNCONFIRMED": "참여 종목이 적음", "CONTRADICTED": "대부분 20일선 아래", "DATA MISSING": "breadth 없음"},
    "NEWS": {"CONFIRMED": "뉴스 sentiment 가 가격 방향을 확인", "PARTIAL": "뉴스 톤이 약하게 같은 방향", "UNCONFIRMED": "뉴스 톤 중립", "CONTRADICTED": "뉴스 sentiment 는 가격 방향을 확인하지 않음", "DATA MISSING": "테마 뉴스 없음"},
    "FUNDAMENTAL": {"CONFIRMED": "세그먼트 펀더멘털이 같은 방향", "PARTIAL": "펀더멘털 일부 확인", "UNCONFIRMED": "펀더멘털 중립", "CONTRADICTED": "펀더멘털은 반대 방향", "DATA MISSING": "펀더멘털 데이터 없음"},
    "MACRO": {"CONFIRMED": "관련 매크로 변수가 같은 방향", "PARTIAL": "매크로 변수 일부 확인", "UNCONFIRMED": "매크로 변수 움직임 작음", "CONTRADICTED": "매크로 변수는 반대 방향", "DATA MISSING": "관련 계열 없음"},
    "DRIVER": {"CONFIRMED": "관련 driver 계열이 같은 방향", "PARTIAL": "driver 계열 일부 확인", "UNCONFIRMED": "driver 계열 움직임 작음", "CONTRADICTED": "driver 계열은 반대 방향", "DATA MISSING": "관련 계열 없음"},
}
STATUS_MEANING_LAG = {
    "PRICE": {"CONFIRMED": "하루 하락이 뚜렷", "PARTIAL": "단기 하락은 제한적", "UNCONFIRMED": "하루 움직임이 작음", "CONTRADICTED": "하루 가격은 반등", "DATA MISSING": "가격 데이터 없음"},
    "RELATIVE": {"CONFIRMED": "시장 대비 약세", "PARTIAL": "시장 대비 소폭 약세", "UNCONFIRMED": "시장과 비슷", "CONTRADICTED": "시장 대비 강세", "DATA MISSING": "상대 데이터 없음"},
    "BREADTH": {"CONFIRMED": "대부분 20일선 아래 — 광범위한 약세", "PARTIAL": "일부 종목만 약세", "UNCONFIRMED": "약세 참여 종목이 적음", "CONTRADICTED": "대부분 20일선 위 — 약세 확산 아님", "DATA MISSING": "breadth 없음"},
    "NEWS": {"CONFIRMED": "뉴스 sentiment 도 약세를 확인", "PARTIAL": "뉴스 톤이 약하게 같은 방향", "UNCONFIRMED": "뉴스 톤 중립", "CONTRADICTED": "뉴스 sentiment 는 약세를 확인하지 않음", "DATA MISSING": "테마 뉴스 없음"},
    "FUNDAMENTAL": {"CONFIRMED": "세그먼트 펀더멘털도 약세", "PARTIAL": "펀더멘털 일부 약세", "UNCONFIRMED": "펀더멘털 중립", "CONTRADICTED": "펀더멘털은 오히려 개선", "DATA MISSING": "펀더멘털 데이터 없음"},
    "MACRO": {"CONFIRMED": "관련 매크로 변수가 약세를 설명", "PARTIAL": "매크로 변수 일부 확인", "UNCONFIRMED": "매크로 변수 움직임 작음", "CONTRADICTED": "매크로 변수는 반대 방향", "DATA MISSING": "관련 계열 없음"},
    "DRIVER": {"CONFIRMED": "관련 driver 계열이 약세를 설명", "PARTIAL": "driver 계열 일부 확인", "UNCONFIRMED": "driver 계열 움직임 작음", "CONTRADICTED": "driver 계열은 반대 방향", "DATA MISSING": "관련 계열 없음"},
}


def _st(v: float | None, direction: int, *, confirm: float, partial: float) -> str:
    if v is None:
        return "DATA MISSING"
    s = v * direction
    if s >= confirm:
        return "CONFIRMED"
    if s >= partial:
        return "PARTIAL"
    if s <= -confirm:
        return "CONTRADICTED"
    return "UNCONFIRMED"


def load_street_views(path: Path, *, as_of: datetime, max_age_days: int) -> dict[str, list[StreetView]]:
    """테마 키 → 확인된 외부 view. 기관·발행일·URL·요약이 없거나 max_age 를 넘으면 버린다."""
    out: dict[str, list[StreetView]] = {}
    if not path.exists():
        return out
    for fp in sorted(path.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("street view 파일 읽기 실패 %s", fp)
            continue
        for raw in (data.get("views") if isinstance(data, dict) else data) or []:
            try:
                inst = str(raw.get("institution") or "").strip(); url = str(raw.get("source_url") or "").strip(); summ = str(raw.get("summary") or "").strip()
                pub = date.fromisoformat(str(raw.get("published_date"))[:10])
            except Exception:
                continue
            if not (inst and url.startswith("http") and summ):
                continue
            age = (as_of.date() - pub).days
            if age < 0 or age > max_age_days:
                continue
            stance = str(raw.get("stance") or "neutral")
            sv = StreetView(institution=inst, analyst=str(raw.get("analyst") or "").strip(), published_date=pub.isoformat(), source_url=url, source_title=str(raw.get("source_title") or ""),
                            quote=str(raw.get("quote") or ""), summary=summ, stance=stance if stance in ("constructive", "cautious", "neutral", "mixed") else "neutral",  # type: ignore[arg-type]
                            key_variables=[str(x) for x in (raw.get("key_variables") or [])][:5], age_days=age, freshness=f"{age}D", retrieved_by=str(raw.get("retrieved_by") or "manual"))  # type: ignore[arg-type]
            for t in raw.get("themes") or []:
                out.setdefault(str(t), []).append(sv)
    for k in out:
        out[k].sort(key=lambda v: v.age_days)
    return out


def _street_read(views: Sequence[StreetView]) -> str:
    if len(views) < 2:
        return ""
    stances = {v.stance for v in views}
    if stances <= {"constructive"}:
        return "기관 견해가 대체로 긍정적 — " + " · ".join(f"{v.institution}: {v.key_variables[0]}" for v in views[:3] if v.key_variables) + " 을(를) driver 로 봄."
    if stances <= {"cautious"}:
        return "기관 견해가 대체로 신중 — " + " · ".join(f"{v.institution}: {v.key_variables[0]}" for v in views[:3] if v.key_variables) + " 을(를) 위험으로 봄."
    pos = [v.institution for v in views if v.stance == "constructive"]; neg = [v.institution for v in views if v.stance in ("cautious", "mixed")]
    return ("Fundamental / driver 시각은 " + (" · ".join(pos) + " 가 긍정적" if pos else "엇갈림") + (f"이지만 {' · '.join(neg)} 는 위험·밸류에이션·수익화를 함께 지적" if neg else "") + " — 하나의 컨센서스로 합치지 않는다.")


def build_leadership_intel(
    rows: Sequence[LeaderRow], cfg: Mapping, *, z_of: Callable[[str], float | None], name_of: Callable[[str], str], themes: Mapping[str, object],
    segments: Mapping[str, object], stock_of: Callable[[str], tuple[str, float | None, str] | None], radar_ids: set[str],
    street: Mapping[str, Sequence[StreetView]], regime_short: str, is_leader: Callable[[LeaderRow], bool],
    fund_of: Callable[[str], tuple[float | None, str]] | None = None,
) -> list[LeaderRow]:
    bc = float(cfg.get("breadth_confirm", 70)); bp = float(cfg.get("breadth_partial", 40)); rc = float(cfg.get("rel_confirm", 0.8)); pc = float(cfg.get("price_confirm", 0.8)); nc = float(cfg.get("news_confirm", 15))
    hints = cfg.get("hints") or {}; qko = cfg.get("quality_ko") or {}; dflt = cfg.get("default") or {}
    ks_max = int(cfg.get("key_stocks_max", 5)); w_max = int(cfg.get("watch_max", 3))
    out: list[LeaderRow] = []
    for r in rows:
        h = dict(hints.get(r.key) or {})
        if "alias" in h:
            h = dict(hints.get(str(h["alias"])) or {})
        lead = is_leader(r); d = 1 if lead else -1
        # ── MARKET CONFIRMATION ──
        conf: list[ConfirmRow] = []
        mtab = STATUS_MEANING if lead else STATUS_MEANING_LAG
        def row(key: str, label: str, value: str, status: str) -> None:
            conf.append(ConfirmRow(key=key, label=label, value=value, status=status, meaning=mtab[key][status]))  # type: ignore[arg-type]
        row("PRICE", "PRICE", "–" if r.z_1d is None else f"{r.z_1d:+.1f}σ 1D", _st(r.z_1d, d, confirm=pc, partial=pc / 3))
        row("RELATIVE", "RELATIVE STRENGTH", "–" if r.rel_1w is None else f"{r.rel_1w:+.1f}σ vs S&P 1W", _st(r.rel_1w, d, confirm=rc, partial=rc / 3))
        if r.breadth is None:
            row("BREADTH", "BREADTH", "–", "DATA MISSING")
        else:
            b = r.breadth if lead else 100 - r.breadth
            row("BREADTH", "BREADTH", f"{r.breadth:.0f}% 20일선 위", "CONFIRMED" if b >= bc else "PARTIAL" if b >= bp else "CONTRADICTED" if b < 100 - bc else "UNCONFIRMED")
        t = themes.get(r.key)
        ns = getattr(t, "news_sentiment", None) if t is not None else None
        row("NEWS", "NEWS", "–" if ns is None else f"{ns:+.0f} 톤", _st(None if ns is None else ns / nc, d, confirm=1.0, partial=0.4) if t is not None else "DATA MISSING")
        seg = segments.get(str(h.get("ai_segment", ""))) if h.get("ai_segment") else None
        fund_v, fund_lbl = (fund_of(str(h.get("ai_segment"))) if (fund_of and h.get("ai_segment")) else (None, ""))
        if seg is not None:
            row("FUNDAMENTAL", "FUNDAMENTAL", "–" if fund_v is None else f"{fund_lbl or getattr(seg, 'label', '')} {float(fund_v):+.0f}", _st(None if fund_v is None else float(fund_v) / 40.0, d, confirm=1.0, partial=0.4))
        links = [dict(x) for x in (h.get("links") or [])]
        link_rows = []
        for lk in links:
            z = z_of(str(lk["id"])); sgn = int(lk.get("sign", 1))
            if z is None:
                continue
            link_rows.append((lk, z, _st(z, sgn * d, confirm=0.8, partial=0.3)))
        macro_link = any(bool(lk.get("macro")) for lk, _z, _s in link_rows)
        if link_rows:
            lk, z, st = link_rows[0]
            row("MACRO" if lk.get("macro") else "DRIVER", str(lk.get("text") or name_of(str(lk["id"]))), f"{name_of(str(lk['id']))} {z:+.1f}σ", st)
        # ── WHY ──
        why: list[str] = []
        for lk, z, st in link_rows:
            if st in ("CONFIRMED", "PARTIAL"):
                why.append(f"{lk.get('text') or name_of(str(lk['id']))} ({name_of(str(lk['id']))} {z:+.1f}σ) — 현재 확인됨")
        if r.rel_1w is not None and abs(r.rel_1w) >= rc / 3:
            why.append(f"S&P 500 대비 1주 상대수익 {r.rel_1w:+.1f}σ — {'시장 ' + regime_short + ' 에도 상대강도 유지' if lead and regime_short == 'Risk-Off' else ('시장보다 강하다' if lead else '시장보다 약하다')}")
        if r.breadth is not None:
            if lead and r.breadth >= bc:
                why.append(f"breadth {r.breadth:.0f}% — 소수 종목 중심 상승이 아니라 종목 전반으로 확산")
            elif lead and r.breadth < bp:
                why.append(f"breadth {r.breadth:.0f}% — 소수 종목이 끌고 있어 확산은 아직")
            elif not lead and r.breadth <= 100 - bc:
                why.append(f"breadth {r.breadth:.0f}% — 대부분 20일선 아래, 광범위한 약세")
        if seg is not None and fund_v is not None and (float(fund_v) > 0) == lead and abs(float(fund_v)) >= 16:
            why.append(f"{getattr(seg, 'label', '')} 세그먼트 펀더멘털 {float(fund_v):+.0f} — 가격과 같은 방향")
        if lead and fund_v is not None and float(fund_v) >= 16 and not any("펀더멘털" in w for w in why):
            why.append(f"{fund_lbl} 펀더멘털 {float(fund_v):+.0f} — 가격과 같은 방향")
        why = why[:3] or [f"1주 상대수익 {r.rel_1w:+.1f}σ" if r.rel_1w is not None else "상대강도 데이터로 선정"]
        # ── QUALITY ──
        cs = {c.key: c.status for c in conf}
        if lead:
            if r.breadth is not None and r.breadth < bp and cs.get("RELATIVE") == "CONFIRMED":
                q = "NARROW"
            elif cs.get("FUNDAMENTAL") == "CONFIRMED" and cs.get("RELATIVE") in ("CONFIRMED", "PARTIAL"):
                q = "FUNDAMENTAL-LED"
            elif macro_link and cs.get("MACRO") == "CONFIRMED" and cs.get("RELATIVE") in ("CONFIRMED", "PARTIAL"):
                q = "MACRO-DRIVEN"
            elif r.breadth is not None and r.breadth >= bc and cs.get("RELATIVE") in ("CONFIRMED", "PARTIAL"):
                q = "BROADENING"
            elif cs.get("NEWS") == "CONFIRMED" and cs.get("PRICE") in ("UNCONFIRMED", "PARTIAL"):
                q = "NEWS-DRIVEN"
            elif cs.get("PRICE") in ("CONFIRMED", "PARTIAL") and cs.get("NEWS") in ("CONTRADICTED", "UNCONFIRMED", "DATA MISSING") and cs.get("FUNDAMENTAL") not in ("CONFIRMED",):
                q = "PRICE-LED"
            else:
                q = "FRAGILE"
        else:
            q = "MACRO-DRIVEN" if (macro_link and cs.get("MACRO") == "CONFIRMED") else "BROADENING" if (r.breadth is not None and r.breadth <= 100 - bc) else "FRAGILE"
        qd = " · ".join(x for x in [f"Breadth {r.breadth:.0f}%" if r.breadth is not None else "", f"Relative {r.rel_1w:+.1f}σ" if r.rel_1w is not None else ""] if x)
        # ── SYSTEM VIEW ──
        rel_text = f"S&P 대비 1주 {r.rel_1w:+.1f}σ 의 상대강도" if r.rel_1w is not None else "상대강도"
        breadth_text = (f"breadth {r.breadth:.0f}% 로 종목 전반이 참여한다" if r.breadth is not None and r.breadth >= bc else f"breadth {r.breadth:.0f}% 로 참여는 일부다" if r.breadth is not None else "breadth 는 없다")
        seg_text = ""
        if segments:
            strong = [getattr(s, "label", k) for k, s in segments.items() if (getattr(s, "rel_z_5d", None) or 0) >= 0.8]
            weak = [getattr(s, "label", k) for k, s in segments.items() if (getattr(s, "rel_z_5d", None) or 0) <= -0.8]
            seg_text = ("리더십은 " + " · ".join(strong[:2]) + " 까지 확산" if strong else "세그먼트별 상대강도는 아직 뚜렷하지 않음") + (f" (후미 {' · '.join(weak[:2])})" if weak else "")
        link_text = (f"{link_rows[0][0].get('text') or name_of(str(link_rows[0][0]['id']))} ({name_of(str(link_rows[0][0]['id']))} {link_rows[0][1]:+.1f}σ)" if link_rows else "관련 계열 없음")
        tpl = str(h.get("view_up" if lead else "view_down") or ("{label} 강세는 {rel_text}가 이끌고 {breadth_text}." if lead else "{label} 약세는 {rel_text}로 지수보다 깊고 {breadth_text}."))
        view = tpl.format(label=r.label, rel_text=rel_text, breadth_text=breadth_text, seg_text=seg_text or "세그먼트 데이터 없음", link_text=link_text)
        caveat = " 뉴스 톤은 가격을 확인하지 않는다." if cs.get("NEWS") == "CONTRADICTED" else ""
        system_view = (view + caveat).strip()
        short_view = why[0].split(" — ")[0] if why else system_view
        # ── KEY STOCKS ──
        ks: list[KeyStock] = []
        for sid in (h.get("stocks") or []):
            st = stock_of(str(sid))
            if st is None:
                continue
            nm, z, seg_lbl = st
            note = ("relative strength ↑" if z is not None and z >= 0.8 else "price confirmation ↑" if z is not None and z >= 0.3 else "price partial" if z is not None and z > -0.3 else "price ↓ — 확인 안 됨" if z is not None else "가격 데이터 없음")
            ks.append(KeyStock(id=str(sid), name=nm, role=seg_lbl, note=note, in_radar=str(sid) in radar_ids, z=None if z is None else round(z, 2)))
        ks.sort(key=lambda k: (0 if k.in_radar else 1, -(k.z or 0)))
        ks = ks[:ks_max]
        # ── STREET ──
        sv = list(street.get(r.key, []))[:3]
        detail = LeadershipDetail(why=why, confirmation=conf, system_view=system_view, driver=str(h.get("driver") or (link_rows[0][0].get("text") if link_rows else "Relative strength")),
                                  quality=q, quality_ko=str(qko.get(q, "")), quality_detail=qd, risk=str(h.get("risk") or dflt.get("risk", "")), street=sv, street_read=_street_read(sv),
                                  key_stocks=ks, watch=[str(x) for x in (h.get("watch") or dflt.get("watch") or [])][:w_max])
        out.append(r.model_copy(update={"system_view": short_view, "detail": detail}))
    return out


def leadership_read(leaders: Sequence[LeaderRow], laggards: Sequence[LeaderRow], *, regime_short: str, label: str) -> str:
    if not leaders and not laggards:
        return f"현재 시장은 {regime_short}이고 상대강도 문턱을 넘는 리더·후미가 없다 — 지수 방향이 곧 테마 방향이다."
    lead_txt = " · ".join(r.label for r in leaders[:3])
    lag_txt = " · ".join(r.label for r in laggards[:2])
    lag_reason = ""
    if laggards and laggards[0].detail is not None and laggards[0].detail.driver:
        lag_reason = f" {laggards[0].detail.driver} 와 함께"
    s = f"현재 시장은 broad {regime_short}이지만 " if regime_short in ("Risk-Off", "Risk-On") else f"현재 판정은 {regime_short}이고 "
    s += (f"{lead_txt} 는 상대강도를 유지." if leaders else "상대강도를 유지하는 리더가 없다.")
    if laggards:
        s += f" {lag_txt} 는{lag_reason} leadership 에서 이탈."
    broad = [r for r in leaders if r.breadth is not None and r.breadth >= 70]
    if leaders and len(broad) == len(leaders):
        s += " 지수는 약해도 내부적으로 선별적 Risk-On 이 breadth 를 갖고 유지되고 있음." if regime_short == "Risk-Off" else " 리더의 breadth 가 넓다."
    elif leaders:
        s += " 다만 리더 일부는 breadth 가 좁아 소수 종목 중심이다."
    return s
