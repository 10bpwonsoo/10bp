"""
Why Did This Stock Move? (2026-09-16 신설)

종목 움직임의 **원인 후보**를 근거와 함께 모은다. 확정하지 않는다. 후보마다
종류(CONFIRMED_DATA / CONFIRMED_NEWS / ANALYST_VIEW / MARKET_INFERENCE /
CLAUDE_INTERPRETATION / UNKNOWN)와 확신(HIGH/MEDIUM/LOW)이 붙는다.

문장 규칙: "X 때문에 올랐다" 가 아니라 "상승과 함께 X 가 동반됐다" 다.
같이 움직였다는 사실과 원인이라는 주장은 다른 문장이다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from ..models.intelligence import (
    AltDataPoint, AnalystSnapshot, CauseCandidate, Commentary, Evidence, StockExplanation, StockFeature,
    StockImpact, StockMeta,
)
from ..models.news import NewsEvent

ENGINE_VERSION = "0.1.0"


def _conf(strength: float) -> str:
    return "HIGH" if strength >= 1.5 else "MEDIUM" if strength >= 0.8 else "LOW"


def _same_sign(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and (a > 0) == (b > 0) and abs(a) > 1e-9 and abs(b) > 1e-9


def explain_stock(
    meta: StockMeta,
    feature: StockFeature,
    *,
    as_of: datetime,
    market_ret: float | None,
    market_z: float | None,
    impacts: Sequence[StockImpact],
    driver_points: Mapping[str, AltDataPoint],
    peer_points: Sequence[AltDataPoint],
    news: Sequence[NewsEvent],
    analyst: AnalystSnapshot | None,
    commentary: Commentary | None,
) -> StockExplanation:
    ret, z = feature.price.ret_1d, feature.price.z_1d
    causes: list[CauseCandidate] = []

    # 1. 시장 전체 (CONFIRMED_DATA)
    if _same_sign(ret, market_ret) and market_z is not None and abs(market_z) >= 0.8:
        causes.append(CauseCandidate(
            kind="CONFIRMED_DATA", confidence=_conf(abs(market_z)),
            text=f"시장 전체가 같은 방향으로 움직였다 (KOSPI {market_ret:+.2f}%, {market_z:+.1f}σ). 종목의 시장 대비 초과분은 {feature.relative_return_1d:+.2f}%p 다." if feature.relative_return_1d is not None else f"시장 전체가 같은 방향으로 움직였다 (KOSPI {market_ret:+.2f}%).",
            evidence=[Evidence(key="KOSPI", label="시장 수익률", value=market_ret, display=f"{market_ret:+.2f}%", source="market"),
                      Evidence(key="relative", label="상대 수익률", value=feature.relative_return_1d, display=f"{feature.relative_return_1d:+.2f}%p" if feature.relative_return_1d is not None else "–")],
            weight=abs(market_z),
        ))
    # 2. 업종 (CONFIRMED_DATA)
    if feature.sector_return_1d is not None and _same_sign(ret, feature.sector_return_1d) and abs(feature.sector_return_1d) >= 0.8:
        causes.append(CauseCandidate(
            kind="CONFIRMED_DATA", confidence="MEDIUM",
            text=f"같은 업종({meta.sector}) 종목들이 평균 {feature.sector_return_1d:+.2f}% 로 같은 방향이다 — 종목 고유 요인보다 업종 요인일 가능성.",
            evidence=[Evidence(key="sector", label="업종 평균", value=feature.sector_return_1d, display=f"{feature.sector_return_1d:+.2f}%")],
            weight=abs(feature.sector_return_1d) / 1.5,
        ))
    # 3. 드라이버 충격 (MARKET_INFERENCE)
    for imp in sorted((i for i in impacts if i.stock_id == meta.id), key=lambda i: -i.score)[:3]:
        consistent = (imp.direction == "up" and (ret or 0) > 0) or (imp.direction == "down" and (ret or 0) < 0)
        dp = driver_points.get(imp.driver_id)
        disp = dp.change_1d if dp else None
        causes.append(CauseCandidate(
            kind="MARKET_INFERENCE", confidence=_conf(imp.score / 40.0) if consistent else "LOW",
            text=(f"{imp.driver_label} {imp.shock_z:+.1f}σ 움직임이 이 종목의 노출({imp.rationale})과 "
                  + ("같은 방향이다." if consistent else "반대 방향이다 — 다른 요인이 덮었을 수 있다.")
                  + (" 통계 부호와 사업 부호가 상충한다." if imp.sign_conflict else "")),
            evidence=[Evidence(key=imp.driver_id, label=imp.driver_label, value=imp.shock_z, display=f"{imp.shock_z:+.1f}σ" + (f" ({disp:+.2f}%)" if disp is not None else ""), source="driver"),
                      Evidence(key="impact", label="영향 점수", value=imp.score, display=f"{imp.score:.0f}")],
            weight=imp.score / 30.0 if consistent else imp.score / 90.0,
        ))
    # 4. 글로벌 peer (CONFIRMED_DATA) — 직전 미국 세션
    same = [p for p in peer_points if p.z is not None and _same_sign(p.change_1d, ret) and abs(p.z) >= 0.8]
    if same:
        names = ", ".join(f"{p.label} {p.change_1d:+.1f}%" for p in same[:3])
        causes.append(CauseCandidate(
            kind="CONFIRMED_DATA", confidence="MEDIUM" if len(same) >= 2 else "LOW",
            text=f"글로벌 peer 가 직전 세션에 같은 방향이었다: {names}.",
            evidence=[Evidence(key=p.id, label=p.label, value=p.change_1d, display=f"{p.change_1d:+.2f}%", source=p.source or "") for p in same[:4]],
            weight=0.6 * len(same),
        ))
    # 5. 뉴스 (CONFIRMED_NEWS)
    tagged = [e for e in news if any(t in e.themes for t in meta.themes)]
    aligned = [e for e in tagged if _same_sign(float(e.sentiment), ret)]
    if tagged:
        top = sorted(aligned or tagged, key=lambda e: -e.impact_score)[:3]
        causes.append(CauseCandidate(
            kind="CONFIRMED_NEWS", confidence="MEDIUM" if aligned else "LOW",
            text=(f"관련 테마 기사 {len(tagged)}건 중 {len(aligned)}건이 같은 방향의 톤이다. " if aligned else f"관련 테마 기사 {len(tagged)}건이 있으나 톤은 가격과 다른 방향이다. ")
                 + "기사는 종목이 아니라 테마에 태그된 것이라 종목 고유 뉴스인지는 확인이 필요하다.",
            evidence=[Evidence(key=e.id, label=e.event[:60], value=float(e.sentiment), display=f"감성 {e.sentiment:+d} · 영향 {e.impact_score}", source=e.source) for e in top],
            weight=0.5 * len(aligned),
        ))
    # 6. 애널리스트 (ANALYST_VIEW)
    if analyst and analyst.available and analyst.eps_revision_1m is not None and abs(analyst.eps_revision_1m) >= 2.0:
        consistent = _same_sign(analyst.eps_revision_1m, ret)
        causes.append(CauseCandidate(
            kind="ANALYST_VIEW", confidence="MEDIUM" if consistent else "LOW",
            text=f"1개월 EPS 컨센서스 {analyst.eps_revision_1m:+.1f}% " + ("— 가격과 같은 방향이다." if consistent else "— 가격과 반대다. 괴리 패널 참조."),
            evidence=[Evidence(key="eps_1m", label="EPS 리비전 1M", value=analyst.eps_revision_1m, display=f"{analyst.eps_revision_1m:+.1f}%", source=analyst.source or "")],
            weight=0.7 if consistent else 0.2,
        ))
    # 7. 수기 해설 (CLAUDE_INTERPRETATION)
    if commentary and commentary.sections.interpretation:
        causes.append(CauseCandidate(
            kind="CLAUDE_INTERPRETATION", confidence=commentary.confidence,
            text=commentary.sections.interpretation[0],
            evidence=list(commentary.evidence[:4]), weight=0.5,
        ))

    causes.sort(key=lambda c: -c.weight)
    unexplained = not causes
    if unexplained:
        causes.append(CauseCandidate(
            kind="UNKNOWN", confidence="LOW",
            text="시장·업종·드라이버·peer·뉴스·컨센서스 어느 것도 이 움직임과 같은 방향이 아니다. 종목 고유 요인이거나 수급인데, 수급 데이터가 없어 확인할 수 없다.",
            weight=0.0,
        ))
    head = f"{meta.name} {ret:+.2f}%" if ret is not None else meta.name
    if z is not None:
        head += f" ({z:+.1f}σ)"
    if feature.volume_z is not None:
        head += f", 거래량 {feature.volume_z:+.1f}σ"
    summary = head + ". " + causes[0].text
    return StockExplanation(
        stock_id=meta.id, stock_name=meta.name, as_of=as_of, return_1d=ret, return_z=z, volume_z=feature.volume_z,
        market_return_1d=market_ret, sector_return_1d=feature.sector_return_1d, relative_return_1d=feature.relative_return_1d,
        causes=causes, unexplained=unexplained, summary=summary,
    )
