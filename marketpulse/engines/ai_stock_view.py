"""
STOCK VIEW (2026-10-01) — AI STOCK IMPACT MAP · STOCK RADAR · NEWS → VALUE CHAIN → STOCK 의 표시 층.

세 영역의 역할을 나눈다.
  STOCK IMPACT MAP  = 개별 종목에서 지금 특이한 변화가 무엇인가 (anomaly 하나만 대표 라벨로, 강도 순 상위 N)
  STOCK RADAR       = 그중 다시 확인할 가치가 높은 종목 (버킷 이름·설명·WHY WATCH)
  NEWS              = 중요한 뉴스가 어느 밸류체인·종목까지 전파되는가 (TOP IMPACT / OTHER, 뉴스 × 가격 관계)

계산은 하나도 새로 하지 않는다. stocks(네 축 · 상대 수익 · 언급), radar(버킷), news_impact(체인 · confirmation)를
config/ai_regime.yaml `stock_view` 의 규칙으로 선별·라벨·문장화한다. 임의의 종합 점수(Radar Score 같은 것)는 만들지 않는다.
문장은 템플릿이다 — LLM 이 있으면 다듬을 수 있지만 없어도 그대로 뜬다.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence

from ..models.ai_regime import AiRegime, NewsCard, RadarBucketView, RadarItem, StockImpactRow, StockSignal, StockView
from .korean import fix_particles


def _ax(r: StockImpactRow, k: str) -> float | None:
    return next((a.value for a in r.axes if a.key == k), None)


def _axd(r: StockImpactRow, k: str) -> str:
    return next((a.detail for a in r.axes if a.key == k), "")


def _label(r: StockImpactRow, cfg: Mapping) -> str:
    t, f, m, c = _ax(r, "theme"), _ax(r, "fundamental"), _ax(r, "market"), _ax(r, "macro")
    on = float(cfg.get("axis_on", 0.5)); br = float(cfg.get("breakout_rel", 4.0)); ms = float(cfg.get("macro_strong", -1.0))
    rel = r.rel_5d
    g = lambda v: v is not None and v >= on  # noqa: E731
    b = lambda v: v is not None and v <= -on  # noqa: E731
    if g(t) and g(f) and g(m):
        return "CONFIRMED"
    if g(f) and m is not None and m <= 0:
        return "FUNDAMENTAL LEADING"
    if rel is not None and rel >= br:
        return "RELATIVE BREAKOUT"
    if rel is not None and rel <= -br:
        return "RELATIVE BREAKDOWN"
    if g(t) and r.mentions > 0 and m is not None and m <= 0:
        return "NEWS > PRICE"
    if c is not None and c <= ms and g(m):
        return "MACRO RESILIENT"
    if g(m) and not g(f):
        return "PRICE LEADING"
    if b(c) and b(m):
        return "MACRO SENSITIVE"
    if g(m) and (t is None or t < on) and r.mentions == 0:
        return "PRICE > NEWS"
    if (g(f) and b(m)) or (b(f) and g(m)) or (g(t) and b(m)):
        return "DIVERGENCE"
    return "IN LINE"


def _rank(r: StockImpactRow, label: str, cfg: Mapping) -> float:
    """선별 순서 — 수익률 순위가 아니라 '얼마나 특이한가'. 상대강도 크기 · 축 간 괴리 · 뉴스 언급 · 확인 여부."""
    f, m, t = _ax(r, "fundamental"), _ax(r, "market"), _ax(r, "theme")
    br = float(cfg.get("breakout_rel", 4.0))
    v = abs(r.rel_5d or 0) / br
    if f is not None and m is not None:
        v += abs(f - m) * 0.6
    if t is not None and m is not None and t > 0.5 and m < 0:
        v += 0.5
    v += 0.4 * min(r.mentions, 3)
    v += {"CONFIRMED": 1.0, "FUNDAMENTAL LEADING": 0.8, "RELATIVE BREAKOUT": 0.6, "RELATIVE BREAKDOWN": 0.6, "MACRO RESILIENT": 0.7, "IN LINE": -5.0}.get(label, 0.3)
    return round(v, 2)


def build_signals(r: AiRegime, cfg: Mapping, seg_ko: Mapping[str, str], seg_lab: Mapping[str, str]) -> tuple[list[StockSignal], list[StockSignal]]:
    labels = cfg.get("labels", {}) or {}; reads = cfg.get("read", {}) or {}; watches = cfg.get("watch", {}) or {}
    fl = cfg.get("fundamental_label", {}) or {}; ml = cfg.get("macro_label", {}) or {}; tn = cfg.get("tension", {}) or {}
    out: list[StockSignal] = []
    for row in r.stocks:
        if not row.available:
            continue
        label = _label(row, cfg); spec = labels.get(label, {}) or {}
        seg = seg_lab.get(row.segments[0], row.segments[0]) if row.segments else "AI"
        c = _ax(row, "macro"); f = _ax(row, "fundamental"); m = _ax(row, "market")
        macro_clause = (", " + str(cfg.get("macro_clause", ""))) if c is not None and c <= -0.5 and label not in ("MACRO SENSITIVE", "MACRO RESILIENT") else ""
        rel_txt = "–" if row.rel_5d is None else f"{row.rel_5d:+.1f}%p vs NDX · 1W"
        sig_val = rel_txt if label in ("RELATIVE BREAKOUT", "RELATIVE BREAKDOWN", "PRICE LEADING", "MACRO RESILIENT", "MACRO SENSITIVE", "PRICE > NEWS", "CONFIRMED") else ""
        st = lambda v: str(tn.get("strong", "Strong")) if v is not None and v >= 0.5 else str(tn.get("weak", "Weak")) if v is not None and v <= -0.5 else str(tn.get("neutral", "Neutral"))  # noqa: E731
        tension = f"Price {st(m)} / Fundamental {st(f)}" if row.overall in ("MIXED", "UNCONFIRMED") and f is not None and m is not None else ""
        news_line = row.news_flow if row.mentions else ""
        sig = StockSignal(id=row.id, name=row.name, segment=seg, segment_ko=seg_ko.get(row.segments[0], "") if row.segments else "", region=row.region, ret_5d=row.ret_5d, rel_5d=row.rel_5d, ret_21d=row.ret_21d,
                          label=label, label_ko=str(spec.get("ko", "")), signal=str(spec.get("signal", "")), signal_value=sig_val,
                          fundamental=str(fl.get(row.semiconductor, row.semiconductor)), macro=str(ml.get(row.rates_sensitivity, row.rates_sensitivity)), news=news_line, tension=tension,
                          read=fix_particles(str(reads.get(label, "")).format(seg=seg, macro=macro_clause)),
                          what_changed=f"{spec.get('signal', '')}{' · ' + rel_txt if row.rel_5d is not None else ''} — {spec.get('ko', '')}",
                          price_relative=_axd(row, "market"), fundamentals=_axd(row, "fundamental"), news_sentiment=f"{_axd(row, 'theme')} · 뉴스 {row.news_flow}", macro_exposure=f"{_axd(row, 'macro')} · 금리 민감 {row.rates_sensitivity}",
                          watch=[str(w).format(seg=seg) for w in (watches.get(label, []) or [])][:3], rank_value=_rank(row, label, cfg))
        out.append(sig)
    ranked = sorted([s for s in out if s.label != "IN LINE"], key=lambda s: -s.rank_value)
    per = int(cfg.get("max_per_segment", 2)); seen: dict[tuple[str, str], int] = {}; top: list[StockSignal] = []
    for s in ranked:  # 같은 세그먼트·같은 라벨은 기본 목록에 per 개까지 — 나머지는 View all 에
        k = (s.segment, s.label)
        if seen.get(k, 0) >= per:
            continue
        seen[k] = seen.get(k, 0) + 1; top.append(s)
        if len(top) >= int(cfg.get("max_default", 10)):
            break
    return top, sorted(out, key=lambda s: -s.rank_value)


def build_radar(r: AiRegime, cfg: Mapping, sig_by: Mapping[str, StockSignal], seg_lab: Mapping[str, str]) -> list[RadarBucketView]:
    st_by = {s.id: s for s in r.stocks}; pl = cfg.get("price_label", {}) or {}; out: list[RadarBucketView] = []
    old = {b.key: b for b in r.radar}
    for spec in cfg.get("buckets", []):
        items: list[RadarItem] = []; seen: set[str] = set()
        for src in spec.get("from", []):
            for it in (old.get(str(src)).items if old.get(str(src)) else []):
                iid = str(it["id"])
                if iid in seen or iid not in st_by:
                    continue
                seen.add(iid); row = st_by[iid]; m = _ax(row, "market")
                seg = seg_lab.get(row.segments[0], row.segments[0]) if row.segments else "AI"
                price = str(pl.get("none", "N/A")) if m is None else str(pl.get("up" if m >= 0.5 else "down" if m <= -0.5 else "flat", "–"))
                sig = sig_by.get(iid)
                items.append(RadarItem(id=iid, name=row.name, segment=seg, relative="–" if row.rel_5d is None else f"{row.rel_5d:+.1f}%p", price=price,
                                       fundamental=sig.fundamental if sig else row.semiconductor, why_watch=fix_particles(str(spec.get("why", "")).format(seg=seg)), detail=str(it.get("reason", ""))))
        out.append(RadarBucketView(key=str(spec["key"]), label=str(spec["label"]), desc=str(spec.get("desc", "")), items=items))
    return out


_TOK = re.compile(r"[A-Za-z가-힣0-9]{2,}")


def _tokens(s: str) -> set[str]:
    return {t.lower() for t in _TOK.findall(s)}


def build_news(r: AiRegime, cfg: Mapping) -> tuple[list[NewsCard], list[NewsCard]]:
    tl = cfg.get("tone_label", {}) or {}; cat = cfg.get("category", {}) or {}; why = cfg.get("why", {}) or {}; rx = cfg.get("reaction", {}) or {}; pw = cfg.get("priority", {}) or {}
    thr = float(cfg.get("dedupe_jaccard", 0.5))
    cards: list[NewsCard] = []
    for n in r.news_impact:
        toks = _tokens(n.event); dup = None
        for c in cards:
            a = _tokens(c.event); shared = len(a & toks); j = shared / len(a | toks) if a | toks else 0.0
            same_chain = bool(n.drivers) and c._drivers == list(n.drivers) and set(c.key_stocks) == set(n.primary_stocks[:3]) and shared >= 2  # driver 미분류끼리는 묶지 않는다
            if j >= thr or same_chain:
                dup = c; break
        if dup is not None:
            dup.cluster_size += 1
            if abs(n.tone) > abs(dup.tone):
                dup.tone = n.tone
                dup.impact = "POSITIVE" if n.tone >= float(tl.get("pos", 10)) else "NEGATIVE" if n.tone <= float(tl.get("neg", -10)) else "NEUTRAL"
            continue
        conf = n.confirmation
        react = ("CONFIRMED" if conf.startswith("CONFIRMED —") else "CONFIRMED NEGATIVE" if conf.startswith("CONFIRMED NEGATIVE") else "NOT PRICED" if "MARKET UNCONFIRMED" in conf
                 else "RESILIENT" if "PRICE RESILIENT" in conf else "UNCLEAR")
        impact = "POSITIVE" if n.tone >= float(tl.get("pos", 10)) else "NEGATIVE" if n.tone <= float(tl.get("neg", -10)) else "NEUTRAL"
        d0 = n.drivers[0] if n.drivers else "none"
        stocks_all = [x for x in n.primary_stocks + n.secondary_stocks + n.infrastructure_stocks if x]
        cards.append(NewsCard(event=n.event, source=n.source, url=n.url, tone=n.tone, impact=impact, category=" · ".join(str(cat.get(d, d.upper())) for d in n.drivers[:2]) or "UNCLASSIFIED",
                              primary=n.primary[:2], secondary=n.secondary, tertiary=n.infrastructure, key_stocks=(n.primary_stocks or stocks_all)[:3], all_stocks=list(dict.fromkeys(stocks_all)),
                              reaction=react, reaction_ko=str((rx.get(react) or {}).get("ko", "")), reaction_read=str((rx.get(react) or {}).get("read", "")), why=str(why.get(d0, why.get("none", "")))))
        cards[-1]._drivers = list(n.drivers)  # 같은 catalyst 묶기용(직렬화 안 됨)
    for c in cards:
        spread = len(c.primary) + len(c.secondary) + len(c.tertiary)
        c.priority = round(abs(c.tone) * float(pw.get("impact_w", 1.0)) + spread * float(pw.get("spread_w", 6.0))
                           + (float(pw.get("reaction_w", 8.0)) if c.reaction.startswith("CONFIRMED") else 0.0)
                           + (float(pw.get("divergence_w", 10.0)) if c.reaction in ("NOT PRICED", "RESILIENT") else 0.0)
                           + (c.cluster_size - 1) * float(pw.get("cluster_w", 4.0)), 1)
    cards.sort(key=lambda c: -c.priority)
    top_n = int(cfg.get("top_impact", 3))
    return cards[:top_n], cards[top_n:]


def build_stock_view(r: AiRegime, cfg_all: Mapping) -> StockView:
    cfg = cfg_all.get("stock_view", {}) or {}
    seg_lab = {str(s["key"]): str(s.get("label", s["key"])) for s in (cfg_all.get("value_chain") or {}).get("segments", [])}
    seg_ko = {str(s["key"]): str(s.get("label_ko", "")) for s in (cfg_all.get("value_chain") or {}).get("segments", [])}
    ic, rc, nc = cfg.get("impact", {}) or {}, cfg.get("radar", {}) or {}, cfg.get("news", {}) or {}
    top, allsig = build_signals(r, ic, seg_ko, seg_lab)
    sig_by = {s.id: s for s in allsig}
    news_top, news_others = build_news(r, nc)
    return StockView(impact_subtitle=str(ic.get("subtitle", "")), signals=top, all_signals=allsig, label_legend={k: str((v or {}).get("ko", "")) for k, v in (ic.get("labels") or {}).items()},
                     radar_subtitle=str(rc.get("subtitle", "")), radar=build_radar(r, rc, sig_by, seg_lab), radar_default=int(rc.get("max_default", 3)),
                     news_subtitle=str(nc.get("subtitle", "")), news_top=news_top, news_others=news_others, news_others_default=int(nc.get("others_default", 6)),
                     news_legend={k: str(v) for k, v in (nc.get("legend") or {}).items()},
                     note="선별은 수익률 순위가 아니라 상대강도 크기 · 축 간 괴리 · 뉴스 언급 · 확인 여부로 정한 '특이성' 순이다. 문장은 템플릿이며 확률·추천이 아니다.")
