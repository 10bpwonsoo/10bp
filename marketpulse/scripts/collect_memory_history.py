"""
메모리 가격 과거 DB 수집(2026-10-23) — data/memory_history/ 에 RAW 관측만 저장한다. 일별 state · premium 은 엔진이 만든다.

    python -m marketpulse.scripts.collect_memory_history daily-express --from-id 12430 --to-id 12960 [--cache DIR]
    python -m marketpulse.scripts.collect_memory_history trendforce-weekly          # 러너에서(이 세션은 trendforce.com 차단)
    python -m marketpulse.scripts.collect_memory_history validate

저장 구조(데일리 아카이브와 섞지 않는다):
    data/memory_history/dram/<ID>.csv · nand/<ID>.csv   현물 RAW 관측 — product,date,price,unit,source,source_date,published_at,collected_at,frequency,quality,is_proxy,source_url,quote
    data/memory_history/contract/<ID>.csv               계약가 — product,reference_period,published_at,price,unit,source,comparability,reported_change_pct,quality,source_url,note
    data/memory_history/validation.json                  제품별 첫·마지막 날짜 · RAW 수 · 빈 구간 · 중복 · 이상치
같은 (관측일, source) 행은 다시 쓰지 않는다(append-only). 값이 다르면 덮어쓰지 않고 validation 에 conflict 로 남긴다.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..adapters.alternative.memory_history import is_weekly_article_url, now_iso, parse_daily_express, parse_trendforce_weekly
from ..config.settings import PACKAGE_ROOT

ROOT = PACKAGE_ROOT / "data" / "memory_history"
SPOT_FIELDS = ["product", "date", "price", "unit", "source", "source_date", "published_at", "collected_at", "frequency", "quality", "is_proxy", "source_url", "quote"]
CONTRACT_FIELDS = ["product", "reference_period", "published_at", "price", "unit", "source", "comparability", "reported_change_pct", "quality", "source_url", "note"]
FAMILY = {"DDR4_8G_SPOT": "dram", "DDR4_8G_ETT_SPOT": "dram", "NAND_512G_TLC_WAFER": "nand"}
UNIT = {"DDR4_8G_SPOT": "USD/chip", "DDR4_8G_ETT_SPOT": "USD/chip", "NAND_512G_TLC_WAFER": "USD/wafer-equivalent (512Gb TLC)"}
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TPE = timezone(timedelta(hours=8))


def _get(url: str, timeout: float = 40.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001 — 수집 실패는 그 글만 건너뛴다
        return getattr(e, "code", 0) or 0, ""


def spot_path(pid: str, root: Path = ROOT) -> Path:
    return root / FAMILY.get(pid, "dram") / f"{pid}.csv"


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def merge_rows(path: Path, fields: list[str], new: list[dict], key: tuple[str, ...]) -> tuple[int, list[dict]]:
    """append-only. 같은 key 가 이미 있으면 그대로 두고, 값이 다르면 conflict 로 돌려준다."""
    old = read_rows(path)
    have = {tuple(r[k] for k in key): r for r in old}
    added, conflicts = 0, []
    for r in new:
        k = tuple(str(r[x]) for x in key)
        if k in have:
            if abs(float(have[k]["price"]) - float(r["price"])) > 1e-9:
                conflicts.append({"key": k, "stored": have[k]["price"], "new": r["price"]})
            continue
        have[k] = {f: r.get(f, "") for f in fields}
        added += 1
    rows = sorted(have.values(), key=lambda r: tuple(r[x] for x in key))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return added, conflicts


# ── Daily Express ─────────────────────────────────────────
def collect_daily_express(id_from: int, id_to: int, *, cache: Path | None = None, root: Path = ROOT, sleep: float = 0.3) -> dict:
    """글 번호 범위를 순서대로 읽는다. 발행일이 앞 글보다 30일 넘게 이르면(연도 오기 — 예: 2026-01-02 글이 2025-01-02 로 표기) 빼고 기록한다."""
    collected = now_iso()
    rows: dict[str, list[dict]] = {}
    suspect, seen, pages = [], {}, 0
    last_pub: date | None = None
    for i in range(id_from, id_to + 1):
        f = cache / f"{i}.html" if cache else None
        if f is not None and f.is_file():
            page = f.read_text(encoding="utf-8", errors="ignore")
        else:
            st, page = _get(f"https://dramexchange.com/WeeklyResearch/PrinterFriendly/3/{i}.html")
            time.sleep(sleep)
            if st != 200:
                continue
            if f is not None:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(page, encoding="utf-8")
        r = parse_daily_express(page)
        if r is None:
            continue
        pages += 1
        pub = r["published"]
        if last_pub is not None and (last_pub - pub).days > 30:
            suspect.append({"id": i, "published": pub.isoformat(), "previous": last_pub.isoformat(), "items": {k: v["price"] for k, v in r["items"].items()}})
            continue
        if pub in seen:
            suspect.append({"id": i, "published": pub.isoformat(), "duplicate_of": seen[pub]})
            continue
        seen[pub] = i
        last_pub = max(pub, last_pub or pub)
        for pid, it in r["items"].items():
            rows.setdefault(pid, []).append({
                "product": pid, "date": pub.isoformat(), "price": f"{it['price']:.3f}", "unit": UNIT[pid], "source": "dramexchange_daily_express",
                "source_date": pub.isoformat(), "published_at": datetime(pub.year, pub.month, pub.day, 23, 59, tzinfo=TPE).isoformat(),
                "collected_at": collected, "frequency": "daily", "quality": "PRIMARY", "is_proxy": "false",
                "source_url": f"https://dramexchange.com/WeeklyResearch/PrinterFriendly/3/{i}.html", "quote": it["quote"]})
    report = {"pages": pages, "suspect": suspect, "added": {}, "conflicts": {}}
    for pid, rs in rows.items():
        a, c = merge_rows(spot_path(pid, root), SPOT_FIELDS, rs, ("date", "source"))
        report["added"][pid] = a
        report["conflicts"][pid] = c
    _append_log(root, "daily_express", report)
    return report


def last_daily_express_id(root: Path = ROOT) -> int:
    ids = [int(m.group(1)) for r in read_rows(spot_path("DDR4_8G_SPOT", root)) if (m := re.search(r"/3/(\d+)\.html", r.get("source_url", "")))]
    return max(ids) if ids else 12430


# ── TrendForce 주간 기사 ─────────────────────────────────
LISTINGS = ([f"https://www.trendforce.com/news/?s=Memory+Spot+Price+Update&paged={p}" for p in range(1, 15)]
            + [f"https://www.trendforce.com/news/tag/{t}/page/{p}/" for t in ("ddr4", "nand-flash", "dram") for p in range(1, 21)])


def collect_trendforce_weekly(*, since: date = date(2025, 8, 1), root: Path = ROOT, sleep: float = 0.5) -> dict:
    collected = now_iso()
    links: set[str] = set()
    for u in LISTINGS:
        st, b = _get(u)
        links |= {m.group(0).rstrip("/") + "/" for m in re.finditer(r"https://www\.trendforce\.com/news/20\d\d/\d\d/\d\d/insights-memory-spot-price-update[^\"'#? ]*", b)}
        time.sleep(sleep)
    arts = sorted((d, u) for u in links if (d := is_weekly_article_url(u)) and d >= since)
    rows: dict[str, list[dict]] = {}
    for d, u in arts:
        st, b = _get(u)
        time.sleep(sleep)
        if st != 200:
            continue
        for pid, it in parse_trendforce_weekly(b, d).items():
            rows.setdefault(pid, []).append({
                "product": pid, "date": it["obs_date"].isoformat(), "price": f"{it['price']:.3f}", "unit": UNIT[pid], "source": "trendforce_weekly",
                "source_date": d.isoformat(), "published_at": datetime(d.year, d.month, d.day, 23, 59, tzinfo=TPE).isoformat(), "collected_at": collected,
                "frequency": "weekly", "quality": "PRIMARY" if it["obs_date_basis"] == "TEXT" else "PRIMARY_OBS_DATE=ARTICLE_DATE", "is_proxy": "false",
                "source_url": u, "quote": it["quote"]})
    report = {"articles": len(arts), "first": arts[0][0].isoformat() if arts else None, "last": arts[-1][0].isoformat() if arts else None, "added": {}, "conflicts": {}}
    for pid, rs in rows.items():
        a, c = merge_rows(spot_path(pid, root), SPOT_FIELDS, rs, ("date", "source"))
        report["added"][pid] = a
        report["conflicts"][pid] = c
    _append_log(root, "trendforce_weekly", report)
    return report


def _append_log(root: Path, kind: str, report: dict) -> None:
    p = root / "collect_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_iso(), "kind": kind, **{k: v for k, v in report.items() if k != "suspect"}, "suspect": len(report.get("suspect", []))}, ensure_ascii=False) + "\n")


# ── 검증 ─────────────────────────────────────────────────
def validate(root: Path = ROOT) -> dict:
    """제품·source 별 첫/마지막 날짜, RAW 수, 7일 넘는 빈 구간(일간)·14일 넘는(주간), 같은 날 중복, 직전 대비 ×3 · ÷3 이상 급변(단위 의심)."""
    out: dict = {"generated_at": now_iso(), "spot": {}, "contract": {}}
    for f in sorted((root).glob("*/*.csv")):
        rows = read_rows(f)
        if not rows:
            continue
        kind = "contract" if f.parent.name == "contract" else "spot"
        if kind == "contract":
            per = sorted(rows, key=lambda r: r["reference_period"])
            jumps = [(a["reference_period"], b["reference_period"], a["price"], b["price"]) for a, b in zip(per, per[1:]) if float(a["price"]) and not (1 / 3 <= float(b["price"]) / float(a["price"]) <= 3)]
            out["contract"][f.stem] = {"first": per[0]["reference_period"], "last": per[-1]["reference_period"], "obs": len(per), "outliers": jumps,
                                       "duplicates": len(per) - len({r["reference_period"] for r in per})}
            continue
        res = {}
        for src in sorted({r["source"] for r in rows}):
            rs = sorted((r for r in rows if r["source"] == src), key=lambda r: r["date"])
            ds = [date.fromisoformat(r["date"]) for r in rs]
            lim = 14 if rs[0]["frequency"] == "weekly" else 7
            gaps = [(a.isoformat(), b.isoformat(), (b - a).days) for a, b in zip(ds, ds[1:]) if (b - a).days > lim]
            jumps = [(a["date"], b["date"], a["price"], b["price"]) for a, b in zip(rs, rs[1:]) if not (1 / 3 <= float(b["price"]) / float(a["price"]) <= 3)]
            res[src] = {"first": ds[0].isoformat(), "last": ds[-1].isoformat(), "obs": len(rs), "duplicates": len(ds) - len(set(ds)), "gaps": gaps, "outliers": jumps,
                        "frequency": rs[0]["frequency"]}
        out["spot"][f.stem] = res
    (root / "validation.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    de = sub.add_parser("daily-express")
    de.add_argument("--from-id", type=int, default=None)
    de.add_argument("--to-id", type=int, default=None)
    de.add_argument("--latest", action="store_true", help="저장된 마지막 글 번호 다음부터 --ahead 개를 읽는다(매일 수집)")
    de.add_argument("--ahead", type=int, default=15)
    de.add_argument("--cache", type=Path, default=None)
    sub.add_parser("trendforce-weekly").add_argument("--since", default="2025-08-01")
    sub.add_parser("validate")
    a = ap.parse_args(argv)
    if a.cmd == "daily-express":
        lo, hi = a.from_id, a.to_id
        if a.latest:
            last = last_daily_express_id()
            lo, hi = last + 1, last + a.ahead
        if lo is None or hi is None:
            ap.error("--from-id/--to-id 또는 --latest")
        rep = collect_daily_express(lo, hi, cache=a.cache)
    elif a.cmd == "trendforce-weekly":
        rep = collect_trendforce_weekly(since=date.fromisoformat(a.since))
    else:
        rep = validate()
    print(json.dumps(rep, ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
