"""수집 대상 목록 — 계열마다 어느 공급처에서 어떤 심볼로 받는지, Yahoo 가 막히면 어디로 넘어가는지. `python -m marketpulse.collector inventory`."""

from __future__ import annotations

from typing import Mapping

from ..archive.input_status import market_of
from ..archive.pit import FRED, FUTURES, availability_lag

NOTE = {
    "yahoo": "Yahoo Finance 차트 API(키 없음)",
    "stooq": "Stooq CSV(키 없음)",
    "fred": "FRED(FRED_API_KEY)",
    "twelvedata": "Twelve Data(TWELVEDATA_API_KEY)",
    "krx": "KRX 정보데이터시스템(키 없음)",
    "github": "공개 GitHub CSV 미러(1~수 영업일 늦음)",
    "csv": "저장소의 수기 파일",
}


def _when(provider: str, symbol: str) -> str:
    lag = availability_lag(f"{provider}:{symbol}")
    if lag == FRED:
        return "관측일 다음 평일 22:00Z"
    if lag == FUTURES:
        return "그 거래일 뉴욕 17:00"
    return f"봉 시각 +{int(lag.total_seconds() // 3600)}h"


def rows(plans: Mapping[str, object]) -> list[dict]:
    out = []
    for g, plan in plans.items():
        for ins in plan.instruments:  # type: ignore[attr-defined]
            specs = plan.specs.get(ins.id) or []  # type: ignore[attr-defined]
            first = specs[0] if specs else {}
            alts = specs[1:]
            sym = str(first.get("symbol") or first.get("path") or first.get("dataset") or "")
            out.append({"group": g, "id": ins.id, "name": getattr(ins, "name", ins.id), "primary": str(first.get("provider") or "—"), "symbol": sym,
                        "market": market_of(f"{first.get('provider')}:{sym}") if first else "—",
                        "available": _when(str(first.get("provider")), sym) if first.get("provider") in ("yahoo", "stooq", "fred", "twelvedata") else "—",
                        "alternates": [f"{s.get('provider')}:{s.get('symbol') or str(s.get('path', '')).split('/')[-1] or s.get('dataset')}" for s in alts]})
        for ins in plan.derived:  # type: ignore[attr-defined]
            d = ins.derived_from
            out.append({"group": g, "id": ins.id, "name": getattr(ins, "name", ins.id), "primary": "derived", "symbol": f"{d.op}({d.a},{d.b})", "market": "DERIVED",
                        "available": "재료 계열 중 늦은 쪽", "alternates": []})
    return out


def render(plans: Mapping[str, object]) -> str:
    rs = rows(plans)
    yahoo = [r for r in rs if r["primary"] == "yahoo"]
    uniq = sorted({r["symbol"] for r in yahoo})
    with_alt = sorted({r["symbol"] for r in yahoo if r["alternates"]})
    lines = ["# 수집 대상 · 공급처 목록", "",
             "`python -m marketpulse.collector inventory --md docs/data-sources-inventory.md` 로 다시 만든다(설정에서 생성 — 손으로 고치지 않는다).", "",
             f"- 계열 {len(rs)}개(묶음 사이에 겹치는 것 포함) · 그중 Yahoo 가 첫 공급처인 계열 {len(yahoo)}개 = 서로 다른 Yahoo 심볼 {len(uniq)}개",
             f"- Yahoo 심볼 가운데 설정된 대체 경로가 있는 것 {len(with_alt)}개 · 없는 것 {len(uniq) - len(with_alt)}개(막히면 결측)",
             "- '공개 시각' 은 그 봉이 기준 시각(07:30 KST)에 쓸 수 있게 되는 때(archive/pit.py). 대체 공급처는 자기 규칙을 따른다.", ""]
    for g in ("base", "universe", "basket"):
        part = [r for r in rs if r["group"] == g]
        lines += [f"## {g} ({len(part)})", "", "| 계열 | 첫 공급처 | 심볼 | 시장 | 공개 시각 | 막히면 |", "|---|---|---|---|---|---|"]
        for r in part:
            lines.append(f"| {r['id']} | {r['primary']} | `{r['symbol'] or '—'}` | {r['market']} | {r['available']} | {', '.join(r['alternates']) or '없음(결측)'} |")
        lines.append("")
    lines += ["## 공급처", ""] + [f"- **{k}** — {v}" for k, v in NOTE.items()] + [""]
    return "\n".join(lines)
