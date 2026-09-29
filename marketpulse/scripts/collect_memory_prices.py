"""
메모리 가격 수집기 — DRAMeXchange 현물(오늘 값)과 Silicon Analysts HBM 앵커를 data/replay/alternative/*.csv 로.

  python -m marketpulse.scripts.collect_memory_prices            # 둘 다
  python -m marketpulse.scripts.collect_memory_prices --only dramx

DRAMeXchange 는 공개 이력이 없어 **하루 한 줄씩 쌓는다**(같은 날 두 번 돌리면 덮어쓴다). 키·비밀 없음.
개인 참고 용도의 표를 읽는 것이라 재배포하지 않는다. Silicon Analysts 는 무료 익명 API — 최신 조각만 온다.
CSV 는 CsvProvider 가 마지막 후보로 자동으로 읽으므로 sources.yaml 을 고칠 필요가 없다.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from ..adapters.alternative.memory_sources import hbm_rows, parse_dramexchange_home
from ..config.settings import PACKAGE_ROOT

logger = logging.getLogger("collect_memory_prices")
REPLAY = PACKAGE_ROOT / "data" / "replay" / "alternative"
DRAMX_URL = "https://dramexchange.com/"  # www. 는 다른 호스트로 취급되니 붙이지 않는다
SA_HBM_URL = "https://siliconanalysts.com/api/v1/market-data/hbm-pricing"
#: 화면 항목 → Silicon Analysts series_key. 계약가($/GB)만 쓴다 — per-stack 환산·TAM 역산 계열은 뺀다
HBM_SERIES = {"HBM3E_CONTRACT": ["hbm3e-contract"], "HBM4_CONTRACT": ["hbm4-contract"]}
UA = "Mozilla/5.0 (X11; Linux x86_64) marketpulse-collector"


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - 고정 URL
        return r.read()


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def collect_dramexchange(today: date | None = None, page: str | None = None) -> dict[str, dict]:
    page = page if page is not None else _get(DRAMX_URL).decode("utf-8", errors="ignore")
    parsed = parse_dramexchange_home(page)
    today = today or datetime.now(timezone.utc).date()
    fields = ["date", "close", "change_pct", "high", "low", "session_date", "source"]
    for iid, row in parsed.items():
        path = REPLAY / f"{iid}.csv"
        rows = [r for r in _read_csv(path) if r.get("date") != today.isoformat()]
        rows.append({"date": today.isoformat(), "close": f"{row['value']:.4f}", "change_pct": row.get("change_pct", ""),
                     "high": row.get("high", ""), "low": row.get("low", ""),
                     "session_date": row.get("session_date").isoformat() if row.get("session_date") else "", "source": "dramexchange.com home"})
        rows.sort(key=lambda r: r["date"])
        _write_csv(path, rows, fields)
        logger.info("%s %s=%s (%s행)", iid, row["item"], row["value"], len(rows))
    missing = [k for k in ("DRAM_SPOT", "DDR5_SPOT", "NAND_SPOT", "DXI") if k not in parsed]
    if missing:
        logger.warning("DRAMeXchange 에서 못 읽은 항목: %s — 페이지 구조가 바뀌었을 수 있다", missing)
    return parsed


def collect_hbm(doc: dict | None = None) -> dict[str, int]:
    doc = doc if doc is not None else json.loads(_get(SA_HBM_URL))
    pts = (doc.get("data") or {}).get("dataPoints") or []
    fields = ["date", "close", "low", "high", "series", "data_type", "confidence", "source", "source_date", "period"]
    out: dict[str, int] = {}
    for iid, keys in HBM_SERIES.items():
        rows = hbm_rows(pts, keys)
        if not rows:
            logger.warning("%s: 해당 series 앵커가 없다 (익명 호출은 최신 조각만 준다)", iid)
            continue
        _write_csv(REPLAY / f"{iid}.csv", rows, fields)
        out[iid] = len(rows)
        logger.info("%s %d행, 마지막 %s = %s $/GB (%s, %s)", iid, len(rows), rows[-1]["date"], rows[-1]["close"], rows[-1]["data_type"], rows[-1]["confidence"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--only", choices=["dramx", "hbm"], default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    rc = 0
    if args.only in (None, "dramx"):
        try:
            got = collect_dramexchange()
            print("dramexchange:", {k: v["value"] for k, v in got.items()})
        except Exception as exc:  # noqa: BLE001
            logger.error("DRAMeXchange 수집 실패: %s", exc); rc = 1
    if args.only in (None, "hbm"):
        try:
            print("hbm:", collect_hbm())
        except Exception as exc:  # noqa: BLE001
            logger.error("Silicon Analysts 수집 실패: %s", exc); rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
