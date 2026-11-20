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
    # 한 문장 안에서 찾는다(문장 안의 소수점 '1.69%' 때문에 [^.] 로 자르지 않는다)
    "NAND_512G_TLC_WAFER": r"512Gb(?: TLC)?(?: NAND)?(?: wafers?)?\b.*?(?:arriving at|to|reaching|exceeding)\D{0,40}?US\$+\s*([\d]+(?:\.\d+)?)",
    "DDR4_8G_SPOT": r"DDR4 1Gx8 3200+MT/s\)?.*?(?:to|at)\s+US\$\s*([\d]+(?:\.\d+)?)\s*(?:this week|\(|\))",
}
_SENT = re.compile(r"(?<=[.])\s+(?=[A-Z\[])")


def _obs_date(fragment: str, article: date) -> date | None:
    """'(October 19)' · '(Oct.19)' · '(Sept. 7)' · '(10/19)' → 날짜. 연도는 기사 날짜에서(1월 기사의 12월 관측은 전년)."""
    found = []
    for m in re.finditer(r"\(\s*([A-Za-z]{3,9})\.?\s*(\d{1,2})\s*\)", fragment):
        if m.group(1)[:3].lower() in _MONTHS:
            found.append((_MONTHS[m.group(1)[:3].lower()], int(m.group(2))))
    for m in re.finditer(r"\(\s*(\d{1,2})/(\d{1,2})\s*\)", fragment):
        found.append((int(m.group(1)), int(m.group(2))))
    if not found:
        return None
    mo, d = found[-1]
    y = article.year - (1 if mo > article.month + 1 else 0)
    try:
        od = date(y, mo, d)
    except ValueError:
        return None
    return od if 0 <= (article - od).days <= 14 else None


def parse_trendforce_weekly(page: str, article: date) -> dict:
    """{id: {price, obs_date, obs_date_basis, quote}} — 이번 주 값만(지난주 값은 다시 세지 않는다). 처음 맞는 문장을 쓴다."""
    x = page_text(page)
    sents = _SENT.split(x)
    out = {}
    for pid, rx in TF_ITEMS.items():
        hits = []
        for k, sent in enumerate(sents):
            mm = re.search(rx, sent)
            if not mm:
                continue
            # 관측일 괄호는 값 바로 뒤(this week (October 19)) 또는 문장 끝에 온다. 'Dec.' 처럼 문장이 잘린 경우 다음 조각까지 본다
            tail = sent[mm.start(): mm.end() + 40] + (" " + sents[k + 1][:20] if k + 1 < len(sents) else "")
            od = _obs_date(tail, article)
            hits.append({"price": float(mm.group(1)), "obs_date": od or article, "obs_date_basis": "TEXT" if od else "ARTICLE_DATE", "quote": sent.strip()[:260]})
        if hits:
            # 관측일이 적힌 문장을 우선(같은 값을 요약 문장 · 본문 문장에서 두 번 말하는 기사)
            out[pid] = next((h for h in hits if h["obs_date_basis"] == "TEXT"), hits[0])
    return out


def is_weekly_article_url(url: str) -> date | None:
    m = re.search(r"trendforce\.com/news/(20\d\d)/(\d\d)/(\d\d)/insights-memory-spot-price-update", url)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 공개 가격 페이지 스냅샷(현재 · Internet Archive 보존본) ───────────────
# DRAMeXchange 공개 홈과 TrendForce 공개 가격 페이지(price/dram/dram_spot · price/flash/wafer_spot)는 같은 표 형식이다:
#   품목 | Daily High | Daily Low | Session High | Session Low | Session Average | Session Change
# 행의 공개 시각 = 그 행 앞에 가장 가까이 있는 'Last Update' 시각(표마다 하나). 시각을 못 읽은 행은 버린다(값을 만들지 않는다).
SNAPSHOT_ITEMS = {
    # 해마다 표기 차이(16G/16Gb)가 있어 정규식으로 맞춘다. 다른 등급(eTT)·다른 칩과는 섞이지 않게 끝까지 맞춘다
    "DDR5_16G_SPOT": r"DDR5 16Gb? \(2Gx8\) 4800/5600",
    "DDR5_16G_ETT_SPOT": r"DDR5 16Gb? \(2Gx8\) eTT",
    "DDR4_16G_SPOT": r"DDR4 16Gb? \(2Gx8\) 3200",
    "DDR4_8G_SPOT": r"DDR4 8Gb? \(1Gx8\) 3200",
    "NAND_512G_TLC_WAFER": r"512Gb TLC(?: Wafer)?",
    "NAND_256G_TLC_WAFER": r"256Gb TLC(?: Wafer)?",
    "NAND_128G_TLC_WAFER": r"128Gb TLC(?: Wafer)?",
}
_STAMP = re.compile(r"Last Update:?\s*(?:(?P<mon>[A-Z][a-z]{2})\.\s?(?P<d>\d{1,2})\s+(?P<y>\d{4})|(?P<iso>\d{4}-\d{2}-\d{2}))\s+(?P<hh>\d{2}):(?P<mm>\d{2})\s*\(GMT\+8\)")
_MON3 = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _num(s: str) -> float | None:
    s = s.replace(",", "").replace("%", "").replace("▲", "").replace("▼", "-").replace("—", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_price_snapshot(page: str) -> dict:
    """{id: {item, value(session avg), high, low, change_pct, stamp(datetime +08:00)}}."""
    from datetime import timedelta, timezone
    tz8 = timezone(timedelta(hours=8))
    body = _JUNK.sub(" ", page)
    stamps = []
    # 위치를 맞추려고 원문(태그 포함)에서 직접 찾는다 — 태그 사이 공백·&nbsp; 를 허용
    flat = re.sub(r"<[^>]+>", lambda t: " " * len(t.group(0)), body).replace("&nbsp;", "      ")
    for m in _STAMP.finditer(flat):
        try:
            if m.group("iso"):
                y, mo, d = (int(x) for x in m.group("iso").split("-"))
            else:
                y, mo, d = int(m.group("y")), _MON3[m.group("mon")], int(m.group("d"))
            stamps.append((m.start(), datetime(y, mo, d, int(m.group("hh")), int(m.group("mm")), tzinfo=tz8)))
        except (KeyError, ValueError):
            continue
    out: dict = {}
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S):
        cells = [" ".join(html.unescape(_TAGS.sub(" ", c)).split()) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr.group(1), flags=re.S)]
        cells = [c for c in cells if c]
        if len(cells) < 7:
            continue
        pid = next((k for k, rx in SNAPSHOT_ITEMS.items() if re.fullmatch(rx, cells[0])), None)
        if pid is None or pid in out:
            continue
        vals = [_num(c) for c in cells[1:7]]
        if vals[4] is None:
            continue
        prior = [s for pos, s in stamps if pos < tr.start()]
        if not prior:
            continue
        out[pid] = {"item": cells[0], "value": vals[4], "high": vals[0], "low": vals[1], "change_pct": vals[5], "stamp": prior[-1]}
    return out
