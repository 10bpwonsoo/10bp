"""
메모리 가격 수집기 — DRAMeXchange 현물(오늘 값)과 Silicon Analysts HBM 앵커를 data/replay/alternative/*.csv 로.

  python -m marketpulse.scripts.collect_memory_prices            # 둘 다
  python -m marketpulse.scripts.collect_memory_prices --only dramx
  python -m marketpulse.scripts.collect_memory_prices --only semi    # 반도체 사이클 탭 저장소만 (2026-10-23)

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

from ..adapters.alternative.memory_sources import hbm_rows, parse_contract_json, parse_dramexchange_home, parse_dramexchange_tables
from ..config.settings import PACKAGE_ROOT

logger = logging.getLogger("collect_memory_prices")
REPLAY = PACKAGE_ROOT / "data" / "replay" / "alternative"
#: 반도체 사이클 탭 저장소(2026-10-23) — 다른 탭이 읽는 replay CSV 와 섞지 않는다. 제품·계약가마다 한 파일, 공개 시각(updated_at) 한 줄.
SEMI = PACKAGE_ROOT / "data" / "semiconductor"
CONTRACT_URLS = {"dram": "https://dramexchange.com/Home/HomePrice?Source=NationalDramContract", "flash": "https://dramexchange.com/Home/HomePrice?Source=NationalFlashContract"}
#: 계약가 표의 이름 → 저장 id. 표에 없는 제품(DDR5 칩 · TLC NAND)은 만들지 않는다
CONTRACT_IDS = {"DDR4 16Gb 2Gx8": "DDR4_16G_CONTRACT", "DDR4 8Gb 1Gx8": "DDR4_8G_CONTRACT", "DDR4 4Gb 256Mx16": "DDR4_4G_CONTRACT", "DDR3 4Gb 256Mx16": "DDR3_4G_CONTRACT",
                "DDR5 8GB SO-DIMM": "DDR5_8GB_SODIMM_CONTRACT", "DDR4 16GB SO-DIMM": "DDR4_16GB_SODIMM_CONTRACT", "DDR4 8GB SO-DIMM": "DDR4_8GB_SODIMM_CONTRACT",
                "NAND 128Gb 16Gx8 Speedns": "NAND_MLC_128G_CONTRACT", "NAND 64Gb 8Gx8 Speedns": "NAND_MLC_64G_CONTRACT", "NAND 32Gb 4Gx8 Speedns": "NAND_MLC_32G_CONTRACT"}
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


def collect_semiconductor(page: str | None = None, contracts: dict[str, list] | None = None, collected: datetime | None = None) -> dict[str, int]:
    """반도체 사이클 탭: 현물 전 제품 + DRAM·NAND 계약가 → data/semiconductor/{spot,contract}/<id>.csv.
    한 줄 = 공개 시각(updated_at) 하나. 같은 공개 시각이 다시 오면(갱신 전 재수집) 덮어쓰지 않고 그대로 둔다."""
    page = page if page is not None else _get(DRAMX_URL).decode("utf-8", errors="ignore")
    collected = collected or datetime.now(timezone.utc)
    out: dict[str, int] = {}
    fields = ["updated_at", "close", "change_pct", "high", "low", "item", "collected_at", "source"]
    for iid, row in parse_dramexchange_tables(page).items():
        if row.get("updated_at") is None:
            logger.warning("%s: 갱신 시각을 못 읽어 저장하지 않는다", iid); continue
        path = SEMI / "spot" / f"{iid}.csv"
        rows = _read_csv(path); stamp = row["updated_at"].isoformat()
        if not any(r.get("updated_at") == stamp for r in rows):
            rows.append({"updated_at": stamp, "close": f"{row['value']:.4f}", "change_pct": row["change_pct"], "high": row["high"], "low": row["low"], "item": row["item"],
                         "collected_at": collected.isoformat(timespec="seconds"), "source": "dramexchange.com home"})
        rows.sort(key=lambda r: r["updated_at"])
        _write_csv(path, rows, fields); out[iid] = len(rows)
    cfields = ["updated_at", "avg", "high", "low", "avg_change_pct", "item", "collected_at", "source"]
    for kind, url in CONTRACT_URLS.items():
        doc = (contracts or {}).get(kind)
        if doc is None:
            try:
                doc = json.loads(_get(url))
            except Exception as exc:  # noqa: BLE001
                logger.warning("계약가(%s) 수집 실패: %s", kind, exc); continue
        for name, row in parse_contract_json(doc).items():
            iid = CONTRACT_IDS.get(name)
            if iid is None:
                continue
            path = SEMI / "contract" / f"{iid}.csv"
            rows = _read_csv(path); stamp = row["updated_at"].isoformat()
            if not any(r.get("updated_at") == stamp for r in rows):
                rows.append({"updated_at": stamp, "avg": row["avg"], "high": row["high"], "low": row["low"], "avg_change_pct": row["avg_change_pct"], "item": name,
                             "collected_at": collected.isoformat(timespec="seconds"), "source": f"dramexchange.com {kind} contract"})
            rows.sort(key=lambda r: r["updated_at"])
            _write_csv(path, rows, cfields); out[iid] = len(rows)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--only", choices=["dramx", "hbm", "semi"], default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    rc = 0
    if args.only in (None, "dramx"):
        try:
            got = collect_dramexchange()
            print("dramexchange:", {k: v["value"] for k, v in got.items()})
        except Exception as exc:  # noqa: BLE001
            logger.error("DRAMeXchange 수집 실패: %s", exc); rc = 1
    if args.only in (None, "semi"):
        try:
            print("semiconductor:", collect_semiconductor())
        except Exception as exc:  # noqa: BLE001
            logger.error("반도체 사이클 수집 실패: %s", exc); rc = 1
    if args.only in (None, "hbm"):
        try:
            print("hbm:", collect_hbm())
        except Exception as exc:  # noqa: BLE001
            logger.error("Silicon Analysts 수집 실패: %s", exc); rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
