"""
메모리 가격 공개 출처 — 파서만 있다. 네트워크는 scripts/collect_memory_prices.py 가 한다.

  DRAMeXchange 홈페이지(dramexchange.com)  DRAM·NAND 현물 세션 평균, DXI. 공개 이력이 없어 오늘 값만 있다 —
                                          그래서 수집기가 날마다 CSV 에 한 줄씩 붙인다.
  Silicon Analysts 무료 API                HBM 계약가 $/GB 앵커(분기·비정기, 출처·신뢰도 포함). 익명 호출은 최신 조각만.

둘 다 시세가 아니라 '연구 자료' 급이다(source_type RESEARCH). 화면은 그렇게 표시한다.
"""

from __future__ import annotations

import html as _html
import re
from datetime import date
from typing import Iterable

#: 화면 항목 → DRAMeXchange 표의 행 이름(정확히 일치)
DRAMX_ITEMS: dict[str, str] = {
    "DRAM_SPOT": "DDR4 8Gb (1Gx8) 3200",
    "DDR5_SPOT": "DDR5 16Gb (2Gx8) 4800/5600",
    "NAND_SPOT": "512Gb TLC",
}
_MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _cells(row_html: str) -> list[str]:
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.S)
    return [_html.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in cells]


def parse_dramexchange_home(page: str) -> dict[str, dict]:
    """홈페이지 HTML → {항목 id: {value, change_pct, high, low, session_date}}.

    표의 열: Item · High · Low · Session High · Session Low · **Session Average** · Change · History.
    값은 세션 평균을 쓴다(개별 호가가 아니라 그날 거래의 평균). DXI 는 값·변화·시각을 따로 읽는다.
    못 읽은 항목은 결과에서 빠진다 — 0 으로 채우지 않는다.
    """
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    text = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))
    out: dict[str, dict] = {}
    # 갱신 시각 — "Last Update: Sep.29 2026 11:00 (GMT+8)". DRAM 표가 먼저, 다음이 모듈·NAND
    stamps = re.findall(r"Last Update:?\s*([A-Z][a-z]{2})\.(\d{1,2}) (\d{4}) (\d{2}:\d{2}) \(GMT\+8\)", text)
    stamp_dates = [date(int(y), _MON[m], int(d)) for m, d, y, _ in stamps if m in _MON]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S)
    for iid, item in DRAMX_ITEMS.items():
        for r in rows:
            c = [x for x in _cells(r) if x]
            if not c or c[0] != item or len(c) < 7:
                continue
            try:
                value = float(c[5].replace(",", ""))
                chg = float(c[6].replace("%", "").replace(",", "").strip())
                hi, lo = float(c[1].replace(",", "")), float(c[2].replace(",", ""))
            except ValueError:
                continue
            # NAND 표는 DRAM 표 다음의 두 번째(모듈) 또는 세 번째 시각을 쓴다 — 없으면 첫 시각
            which = 0 if iid != "NAND_SPOT" else min(2, len(stamp_dates) - 1)
            out[iid] = {"item": item, "value": value, "change_pct": chg, "high": hi, "low": lo,
                        "session_date": stamp_dates[which] if stamp_dates else None}
            break
    m = re.search(r"DXI\s*\|?\s*([A-Z][a-z]{2})\.(\d{1,2}),\s*(\d{2}:\d{2}) \(GMT\+8\)\s*\|?\s*([\d,]+\.\d+)\s*\|?\s*(-?[\d,]+\.\d+) \((-?\d+\.\d+) %\)", text)
    if m is None:
        m2 = re.search(r"DXI.{0,200}?([\d,]{6,}\.\d{2}).{0,40}?(-?[\d,]+\.\d+) \((-?\d+\.\d+) %\)", text)
        if m2:
            out["DXI"] = {"item": "DXI", "value": float(m2.group(1).replace(",", "")), "change_abs": float(m2.group(2).replace(",", "")),
                          "change_pct": float(m2.group(3)), "session_date": None}
    else:
        mon, dd, _hm, val, chg_abs, chg_pct = m.groups()
        # 연도는 표기되지 않는다 — DRAM 표의 연도를 빌린다(연말·연초 경계는 수집기가 보정)
        yr = stamp_dates[0].year if stamp_dates else date.today().year
        out["DXI"] = {"item": "DXI", "value": float(val.replace(",", "")), "change_abs": float(chg_abs.replace(",", "")),
                      "change_pct": float(chg_pct), "session_date": date(yr, _MON[mon], int(dd)) if mon in _MON else None}
    return out


_Q_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def period_to_date(period_label: str, source_date: str | None) -> date | None:
    """Silicon Analysts 의 기간 표기를 날짜로. 'Q1 2026' → 분기말, 'Nov 2025' → 월말, 'H1 2025' → 반기말,
    그 밖의 자유 서술('Agreed Nov 2025, SK Hynix …')은 출처 발표일(source_date)을 쓴다. 못 정하면 None."""
    s = period_label.strip()
    m = re.match(r"^Q([1-4])\s+(\d{4})$", s)
    if m:
        q, y = int(m.group(1)), int(m.group(2)); mo, dd = _Q_END[q]; return date(y, mo, dd)
    m = re.match(r"^H([12])\s+(\d{4})$", s)
    if m:
        h, y = int(m.group(1)), int(m.group(2)); return date(y, 6, 30) if h == 1 else date(y, 12, 31)
    m = re.match(r"^([A-Z][a-z]{2})\s+(\d{4})$", s)
    if m and m.group(1) in _MON:
        y, mo = int(m.group(2)), _MON[m.group(1)]
        nxt = date(y + (mo == 12), (mo % 12) + 1, 1)
        return date.fromordinal(nxt.toordinal() - 1)
    if source_date:
        for pat, fn in ((r"^([A-Z][a-z]{2})\.? (\d{1,2}), (\d{4})$", lambda g: date(int(g[2]), _MON[g[0]], int(g[1]))),
                        (r"^(\d{4})-(\d{2})-(\d{2})$", lambda g: date(int(g[0]), int(g[1]), int(g[2]))),
                        (r"^([A-Z][a-z]{2}) (\d{4})$", lambda g: date(int(g[1]), _MON[g[0]], 28))):
            mm = re.match(pat, source_date.strip())
            if mm and (mm.group(1) in _MON or pat.startswith(r"^(\d{4})")):
                try:
                    return fn(mm.groups())
                except (KeyError, ValueError):
                    return None
    return None


def hbm_rows(data_points: Iterable[dict], series_keys: Iterable[str]) -> list[dict]:
    """Silicon Analysts hbm-pricing 의 dataPoints 에서 지정 series 의 앵커만 골라 날짜순 행으로.
    같은 날짜가 둘이면 나중 것(발표일 기준)이 남는다. 값은 value_mid, 출처·신뢰도·유형을 같이 남긴다."""
    keys = set(series_keys)
    by_date: dict[date, dict] = {}
    for p in data_points:
        if p.get("series_key") not in keys or p.get("value_mid") is None:
            continue
        d = period_to_date(str(p.get("period_label", "")), p.get("source_date"))
        if d is None:
            continue
        by_date[d] = {"date": d.isoformat(), "close": float(p["value_mid"]), "low": p.get("value_low"), "high": p.get("value_high"),
                      "series": p.get("series_key"), "data_type": p.get("data_type"), "confidence": p.get("confidence"),
                      "source": p.get("source_name"), "source_date": p.get("source_date"), "period": p.get("period_label")}
    return [by_date[d] for d in sorted(by_date)]
