"""
메모리 가격 과거 원천(2026-10-23) — 1년 이상 RAW 관측을 공개 원문에서 그대로 뽑는다(값을 만들지 않는다).

  DRAMeXchange Daily Express   dramexchange.com/WeeklyResearch/PrinterFriendly/3/<id>.html — 매 거래일 현물 시황.
                               'the average price of DDR4 8G (1Gx8) 3200 rises to USD 47.000' · eTT 'DDR4 1Gx8 ... USD 5.970'
  TrendForce 주간 스팟 기사     trendforce.com/news/YYYY/MM/DD/insights-memory-spot-price-update-... — 매주 수요일.
                               '512Gb TLC wafers ... arriving at US$18.592' (관측일 '(October 19)' 이 있으면 그 날짜)
DRAMeXchange 공식 과거 차트(chart.dramexchange.com)는 MI 회원 전용이라 쓰지 않는다.
파서는 순수 함수다 — 네트워크는 scripts/collect_memory_history.py 가 한다.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime

_TAGS = re.compile(r"<[^>]+>")
_JUNK = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)


def page_text(page: str) -> str:
    return " ".join(html.unescape(_TAGS.sub(" ", _JUNK.sub("", page))).split())


# ── Daily Express ─────────────────────────────────────────
DE_ITEMS = {
    # id: (정규식, 원문 품목 이름)
    "DDR4_8G_SPOT": (r"DDR4 8G \(1Gx8\) 3200\s+(?:\w+\s+){0,2}?(?:to|at)\s+USD\s*([\d.]+)", "DDR4 8G (1Gx8) 3200"),
    "DDR4_8G_ETT_SPOT": (r"eTT(?: category)?, the (?:average )?price of DDR4 1Gx8\s+(?:\w+\s+){0,2}?(?:to|at)\s+USD\s*([\d.]+)", "eTT DDR4 1Gx8"),
}


def parse_daily_express(page: str) -> dict | None:
    """{kind, published(date), items: {id: {price, quote}}}. Daily Express 가 아니거나 발행일이 없으면 None."""
    x = page_text(page)
    m = re.search(r"Weekly Research : (【[^】]+】).{0,80}?Published (\d{4}-\d{2}-\d{2})", x)
    if not m or m.group(1) != "【Daily Express】":
        return None
    items = {}
    for pid, (rx, _name) in DE_ITEMS.items():
        mm = re.search(rx, x)
        if mm:
            s = x.rfind(".", 0, mm.start()) + 1
            items[pid] = {"price": float(mm.group(1)), "quote": x[s:mm.end()].strip()[:240]}
    return {"kind": m.group(1), "published": date.fromisoformat(m.group(2)), "items": items}


# ── TrendForce 주간 기사 ─────────────────────────────────
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
TF_ITEMS = {
    "NAND_512G_TLC_WAFER": r"512Gb(?: TLC)?(?: NAND)?(?: wafer)?s?\b[^.]{0,160}?(?:arriving at|to|reaching|exceeding)[^$]{0,40}?US\$\s*\$?\s*([\d.]+)",
    "DDR4_8G_SPOT": r"DDR4 1Gx8 3200(?:0)?MT/s\)?[^.]{0,200}?(?:to|at)\s+US\$\s*([\d.]+)\s+this week",
}


def _obs_date(fragment: str, article: date) -> date | None:
    """'(October 19)' · '(Oct.19)' · '(Sept. 7)' · '(10/19)' → 날짜. 연도는 기사 날짜에서(1월 기사의 12월 관측은 전년)."""
    m = re.search(r"\(\s*([A-Za-z]{3,9})\.?\s*(\d{1,2})\s*\)", fragment)
    mo = d = None
    if m and m.group(1)[:3].lower() in _MONTHS:
        mo, d = _MONTHS[m.group(1)[:3].lower()], int(m.group(2))
    else:
        m = re.search(r"\(\s*(\d{1,2})/(\d{1,2})\s*\)", fragment)
        if m:
            mo, d = int(m.group(1)), int(m.group(2))
    if mo is None:
        return None
    y = article.year - (1 if mo > article.month + 1 else 0)
    try:
        od = date(y, mo, d)
    except ValueError:
        return None
    return od if (article - od).days in range(0, 15) else None


def parse_trendforce_weekly(page: str, article: date) -> dict:
    """{id: {price, obs_date, obs_date_basis, quote}} — 이번 주 값만(지난주 값은 다시 세지 않는다)."""
    x = page_text(page)
    out = {}
    for pid, rx in TF_ITEMS.items():
        for mm in re.finditer(rx, x):
            s = x.rfind(".", 0, mm.start()) + 1
            e = x.find(".", mm.end())
            frag = x[mm.end(): (e if e > 0 else mm.end() + 60) + 30]
            od = _obs_date(x[mm.start(): mm.end() + 40], article)
            out[pid] = {"price": float(mm.group(1)), "obs_date": od or article, "obs_date_basis": "TEXT" if od else "ARTICLE_DATE",
                        "quote": x[s:mm.end() + 30].strip()[:260]}
            break
    return out


def is_weekly_article_url(url: str) -> date | None:
    m = re.search(r"trendforce\.com/news/(20\d\d)/(\d\d)/(\d\d)/insights-memory-spot-price-update", url)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
