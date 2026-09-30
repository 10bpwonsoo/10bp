"""
WHAT MATTERS NEXT · MARKET TRANSMISSION PATH (2026-09-29).

이슈 하나가 더 진행되면 Trigger → First-order → Asset → Theme/Industry → Stocks 로 어디로 번지는가를
config/cockpit.yaml what_matters_next.paths 의 예상 경로로 그리되, 단계마다 지금 시장 데이터(z · 상대 z · 테마 점수 ·
종목 z / AI 시장 축)로 CONFIRMED · PARTIAL · UNCONFIRMED · CONTRADICTED · DATA MISSING 을 붙인다.
"금리 ↑ → 기술주 ↓" 같은 정적 결론을 내지 않는다 — EXPECTED 와 OBSERVED 를 나눠 적고, 관측이 갈리면 그렇게 쓴다.
AI 이슈는 ai_regime 의 value_chain / stocks 를 그대로 재사용한다(새 AI 로직 없음).
"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from ..models.cockpit import IssuePath, PathCheck, PathStage, PathStock, PathSummary, PathTier

Status = str


def status_of(z: float | None, expect: int, *, confirm: float, partial: float) -> Status:
    if z is None:
        return "DATA MISSING"
    s = z * expect
    if s >= confirm:
        return "CONFIRMED"
    if s >= partial:
        return "PARTIAL"
    if s <= -confirm:
        return "CONTRADICTED"
    return "UNCONFIRMED"


def aggregate(statuses: Sequence[Status]) -> Status:
    xs = [s for s in statuses if s != "DATA MISSING"]
    if not xs:
        return "DATA MISSING"
    c = xs.count("CONFIRMED"); p = xs.count("PARTIAL"); x = xs.count("CONTRADICTED")
    if c == len(xs):
        return "CONFIRMED"
    if x == len(xs):
        return "CONTRADICTED"
    if c + p > 0:
        return "PARTIAL"
    if x > 0:
        return "CONTRADICTED" if x > len(xs) / 2 else "UNCONFIRMED"
    return "UNCONFIRMED"


class Observer:
    """관측값 조회. instrument → z(하루·5일 중 큰 쪽), segment → AI 밸류체인 상대 z, theme → 테마 가격 모멘텀(−100~100, /theme_scale)."""

    def __init__(self, *, z_of: Callable[[str], float | None], name_of: Callable[[str], str], segments: Mapping[str, object], themes: Mapping[str, object],
                 theme_scale: float, stock_of: Callable[[str], tuple[str, float | None, float | None, str] | None]):
        self.z_of, self.name_of, self.segments, self.themes, self.theme_scale, self.stock_of = z_of, name_of, segments, themes, theme_scale, stock_of

    def observe(self, kind: str, key: str) -> tuple[float | None, str]:
        if kind == "segment":
            seg = self.segments.get(key)
            z = getattr(seg, "rel_z_5d", None) if seg is not None else None
            return (None, "세그먼트 없음") if seg is None else (z, "–" if z is None else f"Nasdaq 대비 {z:+.1f}σ")
        if kind == "theme":
            t = self.themes.get(key)
            if t is None:
                return None, "테마 없음"
            ps = getattr(t, "price_momentum", None)
            return (None, "–") if ps is None else (float(ps) / self.theme_scale, f"테마 가격 모멘텀 {ps:+.0f}")
        z = self.z_of(key)
        return z, ("–" if z is None else f"{z:+.1f}σ")


def _check(row: Mapping, obs: Observer, *, confirm: float, partial: float, default_label: str = "") -> PathCheck:
    kind = str(row.get("kind", "instrument")); key = str(row.get("key") or row.get("id") or "")
    z, txt = obs.observe(kind, key)
    label = str(row.get("label") or default_label or obs.name_of(key))
    return PathCheck(label=label, id=key, kind=kind, expect=int(row.get("sign", 1)), observed=None if z is None else round(z, 2), observed_text=txt,  # type: ignore[arg-type]
                     status=status_of(z, int(row.get("sign", 1)), confirm=confirm, partial=partial))


def _stage(key: str, spec: Mapping | None, obs: Observer, *, confirm: float, partial: float, rows_key: str = "checks", explain: str = "") -> PathStage:
    spec = spec or {}
    checks = [_check(r, obs, confirm=confirm, partial=partial) for r in (spec.get(rows_key) or [])]
    return PathStage(key=key, label=str(spec.get("label", key.upper())), text=[str(t) for t in spec.get("text", [])], checks=checks, status=aggregate([c.status for c in checks]), explain=explain)


def _tier(name: str, ids: Sequence[str], expect: int, obs: Observer, radar_ids: set[str], *, confirm: float, partial: float, trigger_ko: str = "") -> PathTier:
    """종목은 관련성만으로 판정하지 않는다 — 종목 z 로 확인. 노출 우선순위: radar → |z| → 뚜렷한 확인 → 중요한 contradiction."""
    stocks: list[PathStock] = []
    exp_txt = f"{'↑' if expect > 0 else '↓'} {trigger_ko + ' 시 ' if trigger_ko else ''}{'강세' if expect > 0 else '약세'} 예상"
    for sid in ids:
        st = obs.stock_of(sid)
        if st is None:
            continue  # 시스템에 없는 종목은 싣지 않는다
        nm, z, ch, seg = st
        status = status_of(z, expect, confirm=confirm, partial=partial)
        pri = (10.0 if sid in radar_ids else 0.0) + (abs(z) if z is not None else 0.0) + (1.0 if status == "CONFIRMED" else 0.8 if status == "CONTRADICTED" else 0.0)
        stocks.append(PathStock(id=sid, name=nm, expect=expect, arrow="↑" if expect > 0 else "↓", z=None if z is None else round(z, 2), change_1d=None if ch is None else round(ch, 2),
                                status=status, segment=seg, in_radar=sid in radar_ids, expected_text=exp_txt, priority=round(pri, 2)))
    stocks.sort(key=lambda x: -x.priority)
    return PathTier(tier=name, stocks=stocks)  # type: ignore[arg-type]


def build_issue_path(spec: Mapping, cfg: Mapping, obs: Observer, *, radar_ids: set[str], ai_regime: object | None = None, driver_label: str = "", explain: Mapping | None = None) -> IssuePath:
    confirm = float(cfg.get("confirm_z", 0.5)); partial = float(cfg.get("partial_z", 0.25)); tier_max = int(cfg.get("tier_max", 5))
    expect = int(spec.get("expect", -1))
    ex = dict(explain or {}); se = ex.get("stage_explain") or {}
    def _ex(stage: str) -> str:
        return str(spec.get(f"{stage}_explain") or se.get(stage, ""))
    trigger_ko = str(spec.get("trigger_explain") or "").split(" — ")[0]
    trigger = _stage("trigger", spec.get("trigger"), obs, confirm=confirm, partial=partial, explain=_ex("trigger"))
    first = _stage("first_order", spec.get("first_order"), obs, confirm=confirm, partial=partial, explain=_ex("first_order"))
    source = "config"
    if spec.get("reuse_ai_value_chain") and ai_regime is not None:
        # AI 이슈: 기존 AI 센티 밸류체인을 그대로 단계·종목으로 쓴다
        source = "ai_value_chain"
        order = [str(k) for k in cfg.get("ai_chain_order", [])]
        seg_rows = [{"label": getattr(obs.segments[k], "label", k), "kind": "segment", "key": k, "sign": expect} for k in order if k in obs.segments]
        assets = _stage("assets", {"label": "AI VALUE CHAIN", "checks": seg_rows[:4]}, obs, confirm=confirm, partial=partial, explain=_ex("assets") or "AI 밸류체인 상위 세그먼트 — Nasdaq 대비 상대강도")
        themes = _stage("themes", {"label": "SEGMENTS", "checks": seg_rows}, obs, confirm=confirm, partial=partial, explain=_ex("themes") or "세그먼트 전체 — 전이 순서대로")
        tiers_cfg = cfg.get("ai_chain_tiers") or {}
        by_seg: dict[str, list[str]] = {}
        for st in (getattr(ai_regime, "stocks", None) or []):
            for sg in (getattr(st, "segments", None) or [])[:1]:
                by_seg.setdefault(str(sg), []).append(str(st.id))
        tiers = []
        for tname, segs in (("DIRECT", tiers_cfg.get("direct", [])), ("SECONDARY", tiers_cfg.get("secondary", [])), ("TERTIARY", tiers_cfg.get("tertiary", []))):
            ids = [sid for sg in segs for sid in by_seg.get(str(sg), [])]
            ids = sorted(dict.fromkeys(ids), key=lambda i: (0 if i in radar_ids else 1))
            tiers.append(_tier(tname, ids, expect, obs, radar_ids, confirm=confirm, partial=partial, trigger_ko=trigger_ko))
    else:
        assets = _stage("assets", {"label": "ASSET IMPACT", "checks": spec.get("assets", [])}, obs, confirm=confirm, partial=partial, explain=_ex("assets"))
        themes = _stage("themes", {"label": "THEME / INDUSTRY", "checks": spec.get("themes", [])}, obs, confirm=confirm, partial=partial, explain=_ex("themes"))
        tiers = []
        for tname, key in (("DIRECT", "direct"), ("SECONDARY", "secondary"), ("TERTIARY", "tertiary")):
            t = (spec.get("stocks") or {}).get(key) or []
            if isinstance(t, Mapping):
                ids, sgn = [str(x) for x in t.get("ids", [])], int(t.get("sign", expect))
            else:
                ids, sgn = [str(x) for x in t], expect
            tiers.append(_tier(tname, ids, sgn, obs, radar_ids, confirm=confirm, partial=partial, trigger_ko=trigger_ko))
    tiers = [t for t in tiers if t.stocks]
    conf = [_check(r, obs, confirm=confirm, partial=partial) for r in (spec.get("confirm") or [])]
    n_conf = sum(1 for c in conf if c.status == "CONFIRMED")

    # OBSERVED 요약: 테마 단계에서 기대 방향으로 움직인 것 / 반대로 버티는 것
    weak = [c.label for c in themes.checks if c.status in ("CONFIRMED", "PARTIAL")]
    resilient = [c.label for c in themes.checks if c.status == "CONTRADICTED"]
    missing = [c.label for c in themes.checks if c.status == "DATA MISSING"]
    obs_parts = []
    if weak: obs_parts.append(" · ".join(weak) + (" → WEAK" if expect < 0 else " → CONFIRMED"))
    if resilient: obs_parts.append(" · ".join(resilient) + (" → RESILIENT" if expect < 0 else " → CONTRADICTED"))
    if missing: obs_parts.append(" · ".join(missing) + " → DATA MISSING")
    observed = "; ".join(obs_parts) if obs_parts else "관측 없음"
    dl = driver_label or trigger.label
    if weak and resilient:
        conclusion = f"{dl} 부담은 존재하지만 현재 압력은 {' · '.join(weak)}에 더 집중되고 {' · '.join(resilient)}는 상대적으로 견조하다." if expect < 0 else \
                     f"{dl} 효과가 {' · '.join(weak)}에서는 관측되지만 {' · '.join(resilient)}는 아직 반대로 움직인다."
    elif weak and not resilient:
        conclusion = f"예상 전파가 관측된다 — {' · '.join(weak)}. 트리거가 더 진행되면 아래 tier 순으로 번질 수 있다."
    elif resilient and not weak:
        conclusion = f"트리거에도 {' · '.join(resilient)}가 반대로 움직인다 — 예상 전파가 아직 시장에서 확인되지 않는다."
    else:
        conclusion = "예상 경로는 있지만 테마 단계의 관측 데이터가 없거나 움직임이 없다 — 전파 미확인."
    tstat = aggregate([trigger.status, first.status, assets.status, themes.status])
    if tstat == "PARTIAL" and not weak and not resilient:
        conclusion = "Transmission: PARTIAL — 트리거는 움직였지만 다음 단계로 아직 전달되지 않았다. " + conclusion
    # SUMMARY — 상세보다 먼저 보이는 것: 주요 영향 체인 · 단계 확인 수 · 가장 노출된 곳 · 상대적 예외
    stages = [trigger, first, assets, themes]
    n_stage_ok = sum(1 for st in stages if st.status == "CONFIRMED"); n_stage_part = sum(1 for st in stages if st.status == "PARTIAL")
    chain = [x for x in [trigger.label, first.label, (" / ".join(c.label for c in themes.checks[:2]) + (" ↓" if expect < 0 else " ↑")) if themes.checks else ""] if x]
    exposed = [c.label for c in themes.checks if c.status == "CONFIRMED"] or weak
    obs_read = ("" if not themes.checks else
                (f"{dl} 부담은 나타나고 있지만 모든 자산이 동일하게 반응하는 것은 아닙니다. 현재 {' · '.join(weak[:2])} 약세가 더 뚜렷합니다." if expect < 0 and weak and resilient else
                 f"{dl} 효과가 {' · '.join(weak[:2])}에서 먼저 나타나고 {' · '.join(resilient[:2])}는 아직 반대입니다." if weak and resilient else
                 f"예상한 반응이 {' · '.join(weak[:3])}에서 실제로 관측됩니다." if weak else
                 f"예상과 달리 {' · '.join(resilient[:2])}가 반대로 움직입니다 — 다른 driver 가 더 강할 가능성." if resilient else "테마 단계의 관측이 아직 없습니다."))
    ok_labels = [c.label for c in conf if c.status == "CONFIRMED"]; part_labels = [c.label for c in conf if c.status in ("PARTIAL", "UNCONFIRMED", "CONTRADICTED")]
    miss_labels = [c.label for c in conf if c.status == "DATA MISSING"]
    confirm_read = ("" if not conf else
                    (f"{' · '.join(ok_labels)} 조건은 충족. " if ok_labels else "충족된 조건이 아직 없습니다. ") +
                    (f"{' · '.join(part_labels[:2])}이(가) 더 나타나면 이 시나리오가 강해집니다." if part_labels else "") +
                    (f" {' · '.join(miss_labels[:2])}은(는) 데이터가 없어 판단하지 않습니다." if miss_labels else "") +
                    ("모든 조건이 충족돼 시나리오가 강하게 확인됩니다." if ok_labels and len(ok_labels) == len(conf) else ""))
    summary = PathSummary(main_impact=chain, stages_confirmed=n_stage_ok, stages_total=len(stages),
                          stages_text=f"{len(stages)}개 주요 전파 단계 중 {n_stage_ok}개가 현재 시장에서 확인" + (f", {n_stage_part}개는 일부만 확인" if n_stage_part else ""),
                          most_exposed=exposed[:3], exception=resilient[:3], observed_read=obs_read, confirm_read=confirm_read)
    tier_show = {str(k): int(v) for k, v in (ex.get("tier_show") or {}).items()} or {"DIRECT": tier_max, "SECONDARY": tier_max, "TERTIARY": 0}
    return IssuePath(trigger=trigger, first_order=first, assets=assets, themes=themes, tiers=tiers, tier_max=tier_max, expected=str(spec.get("expected", "")),
                     observed=observed, conclusion=conclusion, confirm=conf, confirm_count=n_conf, source=source, summary=summary, tier_show=tier_show)  # type: ignore[arg-type]
