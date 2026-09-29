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

from ..models.cockpit import IssuePath, PathCheck, PathStage, PathStock, PathTier

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


def _stage(key: str, spec: Mapping | None, obs: Observer, *, confirm: float, partial: float, rows_key: str = "checks") -> PathStage:
    spec = spec or {}
    checks = [_check(r, obs, confirm=confirm, partial=partial) for r in (spec.get(rows_key) or [])]
    return PathStage(key=key, label=str(spec.get("label", key.upper())), text=[str(t) for t in spec.get("text", [])], checks=checks, status=aggregate([c.status for c in checks]))


def _tier(name: str, ids: Sequence[str], expect: int, obs: Observer, radar_ids: set[str], *, confirm: float, partial: float) -> PathTier:
    stocks: list[PathStock] = []
    for sid in ids:
        st = obs.stock_of(sid)
        if st is None:
            continue  # 시스템에 없는 종목은 싣지 않는다
        nm, z, ch, seg = st
        stocks.append(PathStock(id=sid, name=nm, expect=expect, arrow="↑" if expect > 0 else "↓", z=None if z is None else round(z, 2), change_1d=None if ch is None else round(ch, 2),
                                status=status_of(z, expect, confirm=confirm, partial=partial), segment=seg, in_radar=sid in radar_ids))
    return PathTier(tier=name, stocks=stocks)  # type: ignore[arg-type]


def build_issue_path(spec: Mapping, cfg: Mapping, obs: Observer, *, radar_ids: set[str], ai_regime: object | None = None, driver_label: str = "") -> IssuePath:
    confirm = float(cfg.get("confirm_z", 0.5)); partial = float(cfg.get("partial_z", 0.25)); tier_max = int(cfg.get("tier_max", 5))
    expect = int(spec.get("expect", -1))
    trigger = _stage("trigger", spec.get("trigger"), obs, confirm=confirm, partial=partial)
    first = _stage("first_order", spec.get("first_order"), obs, confirm=confirm, partial=partial)
    source = "config"
    if spec.get("reuse_ai_value_chain") and ai_regime is not None:
        # AI 이슈: 기존 AI 센티 밸류체인을 그대로 단계·종목으로 쓴다
        source = "ai_value_chain"
        order = [str(k) for k in cfg.get("ai_chain_order", [])]
        seg_rows = [{"label": getattr(obs.segments[k], "label", k), "kind": "segment", "key": k, "sign": expect} for k in order if k in obs.segments]
        assets = _stage("assets", {"label": "AI VALUE CHAIN", "checks": seg_rows[:4]}, obs, confirm=confirm, partial=partial)
        themes = _stage("themes", {"label": "SEGMENTS", "checks": seg_rows}, obs, confirm=confirm, partial=partial)
        tiers_cfg = cfg.get("ai_chain_tiers") or {}
        by_seg: dict[str, list[str]] = {}
        for st in (getattr(ai_regime, "stocks", None) or []):
            for sg in (getattr(st, "segments", None) or [])[:1]:
                by_seg.setdefault(str(sg), []).append(str(st.id))
        tiers = []
        for tname, segs in (("DIRECT", tiers_cfg.get("direct", [])), ("SECONDARY", tiers_cfg.get("secondary", [])), ("TERTIARY", tiers_cfg.get("tertiary", []))):
            ids = [sid for sg in segs for sid in by_seg.get(str(sg), [])]
            ids = sorted(dict.fromkeys(ids), key=lambda i: (0 if i in radar_ids else 1))
            tiers.append(_tier(tname, ids, expect, obs, radar_ids, confirm=confirm, partial=partial))
    else:
        assets = _stage("assets", {"label": "ASSET IMPACT", "checks": spec.get("assets", [])}, obs, confirm=confirm, partial=partial)
        themes = _stage("themes", {"label": "THEME / INDUSTRY", "checks": spec.get("themes", [])}, obs, confirm=confirm, partial=partial)
        tiers = []
        for tname, key in (("DIRECT", "direct"), ("SECONDARY", "secondary"), ("TERTIARY", "tertiary")):
            t = (spec.get("stocks") or {}).get(key) or []
            if isinstance(t, Mapping):
                ids, sgn = [str(x) for x in t.get("ids", [])], int(t.get("sign", expect))
            else:
                ids, sgn = [str(x) for x in t], expect
            tiers.append(_tier(tname, ids, sgn, obs, radar_ids, confirm=confirm, partial=partial))
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
    return IssuePath(trigger=trigger, first_order=first, assets=assets, themes=themes, tiers=tiers, tier_max=tier_max, expected=str(spec.get("expected", "")),
                     observed=observed, conclusion=conclusion, confirm=conf, confirm_count=n_conf, source=source)  # type: ignore[arg-type]
