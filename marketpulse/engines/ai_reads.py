"""
BASKET READ · BREADTH READ (2026-10-01) — AI BASKET GROUPS 와 AI BREADTH 카드의 자동 코멘트.

둘을 합치지 않는다. 각 카드는 자기 데이터만 쓴다(그룹: 1D/1W/1M 상대 · rel z · >MA20 · 순위, breadth: >5DMA · >20DMA ·
상승 비율 · 1주 변화 · 그룹별 breadth). 숫자를 문장으로 다시 읽지 않고 '숫자 → 시장 구조 → 의미' 로 간다:
  그룹 — 진짜 leadership(실제 outperform)인지 방어적 상대강도(peer 중 가장 덜 약함)인지, 가격과 breadth 가 같은 방향인지,
         어디가 구조적 laggard 인지. 순위가 바뀌었다는 이유만으로 rotation 이라고 하지 않는다.
  breadth — 단기 확산(5DMA · 상승 비율)과 중기 추세(20DMA)를 분리하고, 20DMA 의 수준과 변화 속도를 함께 본다.
임계·문장은 config/ai_regime.yaml basket_read · breadth_read. 계산은 바꾸지 않는다.
"""

from __future__ import annotations

from typing import Mapping

from ..models.ai_regime import AiRegime, GroupMomentum
from .korean import fix_particles


def basket_read(r: AiRegime, cfg_all: Mapping) -> str:
    cfg = cfg_all.get("basket_read", {}) or {}; t = cfg.get("text", {}) or {}
    groups = [g for g in r.leadership.groups if g.in_basket and g.rel_5d is not None]
    if not groups:
        return str(t.get("empty", ""))
    lead_min = float(cfg.get("true_lead_rel", 0.5)); lag_max = float(cfg.get("lag_rel", -0.5))
    narrow = float(cfg.get("narrow_ma20", 50))
    ranked = sorted(groups, key=lambda g: -(g.rel_5d or 0))
    true_leaders = [g for g in ranked if (g.rel_5d or 0) >= lead_min]
    top = ranked[0]
    # 1) 큰 그림 — 진짜 leadership 인가 (+ rotation 절은 조건이 여럿 겹칠 때만, 같은 문장 안에)
    by = {g.key: g for g in groups}
    old = by.get(r.leadership.leader_1m or ""); new = by.get(r.leadership.leader_1w or "")
    rot = ""
    if old is not None and new is not None and old.key != new.key:
        gap = float(cfg.get("rotation_gap", 1.0))
        conds = [
            (old.rel_5d or 0) <= 0,                                                         # 옛 리더 상대모멘텀 둔화
            (new.rel_5d or 0) - (old.rel_5d or 0) >= gap,                                   # 상대격차가 의미 있게 벌어짐
            (new.above_ma20_pct or 0) >= (old.above_ma20_pct or 0),                         # breadth 가 같이 받침
            new.rel_z_5d is not None and old.rel_z_5d is not None and new.rel_z_5d > old.rel_z_5d,  # rel z 방향
            new.rel_1d is not None and old.rel_1d is not None and new.rel_1d > old.rel_1d,  # 1D 에서도 지속
        ]
        n = sum(1 for c in conds if c)
        if n >= int(cfg.get("rotation_min_conditions", 4)):
            rot = str(t.get("rot_confirmed", "")).format(old=old.label, new=new.label)
        elif n >= int(cfg.get("rotation_possible_conditions", 2)):
            rot = str(t.get("rot_possible", "")).format(old=old.label, new=new.label)
    big_key = "big_true" if true_leaders else "big_none" if (all((g.rel_5d or 0) <= lag_max for g in groups) or all((g.rel_5d or 0) < 0 for g in groups)) else "big_mixed"
    names = " · ".join(g.label for g in true_leaders[:2])
    s1 = str(t.get(big_key + ("_conj" if rot else ""), "")).format(leaders=names) + rot
    # 2) 가장 중요한 상대적 강점 — 그 강세의 질 (+ 가격은 약한데 중기 구조가 남은 그룹은 같은 문장의 대비 절로)
    top_narrow = top.above_ma20_pct is not None and top.above_ma20_pct < narrow
    div = [g for g in ranked if g.key != top.key and (g.rel_5d or 0) < 0 and (g.above_ma20_pct or 0) >= float(cfg.get("divergence_ma20", 70)) and (g.rel_21d or 0) > 0]
    top_key = ("top_true_narrow" if top_narrow else "top_true_broad") if (top.rel_5d or 0) >= lead_min else ("top_resilient_narrow" if top_narrow else "top_resilient_broad")
    s2 = str(t.get(top_key + ("_conj" if div else ""), "")).format(top=top.label) + (str(t.get("divergence_clause", "")).format(div=div[0].label) if div else "")
    # 3) 가장 중요한 약점 — 구조적 laggard 인가
    structural = [g for g in ranked if (g.rel_5d or 0) <= lag_max and (g.rel_21d if g.rel_21d is not None else 0) <= float(cfg.get("structural_rel_1m", 0.0)) and g.above_ma20_pct is not None and g.above_ma20_pct < narrow]
    if structural:
        worst = sorted(structural, key=lambda g: (g.rel_21d or 0) + (g.rel_5d or 0))[0]
        s3 = str(t.get("weak_structural", "")).format(lag=worst.label)
    else:
        lag = ranked[-1]
        s3 = str(t.get("weak_short", "")).format(lag=lag.label) if (lag.rel_5d or 0) <= lag_max else str(t.get("weak_none", ""))
    return fix_particles(" ".join(x for x in (s1, s2, s3) if x))


def breadth_read(r: AiRegime, cfg_all: Mapping) -> str:
    cfg = cfg_all.get("breadth_read", {}) or {}; t = cfg.get("text", {}) or {}
    b = r.breadth
    if b.above_ma20_pct is None or b.above_ma5_pct is None or b.advancing_pct is None:
        return str(t.get("empty", ""))
    ma5, ma20, adv = b.above_ma5_pct, b.above_ma20_pct, b.advancing_pct
    selloff = adv <= float(cfg.get("selloff_max", 20)) and ma5 <= float(cfg.get("selloff_max", 20))
    advance = adv >= float(cfg.get("advance_min", 80)) and ma5 >= float(cfg.get("advance_min", 80))
    short_weak = selloff or ma5 < float(cfg.get("short_weak_max", 50))
    s_short = str(t.get("short_selloff" if selloff else "short_advance" if advance else "short_weak" if short_weak else "short_mixed", ""))
    intact = ma20 >= float(cfg.get("medium_intact_min", 50))
    share = str(t.get("share_most" if ma20 >= float(cfg.get("medium_strong_min", 75)) else "share_majority", ""))
    if short_weak:
        s_med = str(t.get("medium_intact_after_weak" if intact else "medium_broken_after_weak", "")).format(share=share)
    else:
        s_med = str(t.get("medium_intact_after_strong" if intact else "medium_broken_after_strong", "")).format(share=share)
    s1 = f"{s_short} {s_med}".strip()
    # 그룹 contrast — 가장 견조한 그룹과 가장 취약한 그룹만
    labels = {g.key: g.label for g in r.leadership.groups if g.in_basket}
    vals = [(k, v) for k, v in b.by_group.items() if k in labels and v is not None]
    s2 = ""
    if len(vals) >= 2:
        vals.sort(key=lambda kv: -kv[1])
        if vals[0][1] - vals[-1][1] >= float(cfg.get("contrast_gap", 20)):
            strong = [k for k, v in vals if v >= vals[0][1] - 10][:2]; weak = [k for k, v in vals if v <= vals[-1][1] + 10][-2:]
            s2 = str(t.get("contrast", "")).format(strong=" · ".join(labels[k] for k in strong), weak=" · ".join(labels[k] for k in weak))
    # 다음 확인 포인트 — 20DMA 의 수준과 변화 속도
    chg = b.change_1w_pts
    if chg is not None and chg <= float(cfg.get("fast_drop", -15)):
        s3 = str(t.get("next_fast_drop", ""))
    elif chg is not None and chg >= float(cfg.get("fast_rise", 10)):
        s3 = str(t.get("next_fast_rise", ""))
    else:
        s3 = str(t.get("next_hold" if intact else "next_recover", ""))
    return fix_particles(" ".join(x for x in (s1, s2, s3) if x))


def annotate_reads(r: AiRegime, cfg_all: Mapping) -> None:
    r.leadership.read = basket_read(r, cfg_all)
    r.breadth.read = breadth_read(r, cfg_all)
