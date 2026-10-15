"""
macro series 수집(2026-10-13) — FRED API(PRIMARY, 키 필요) → FRED 그래프 CSV(MIRROR, 키 불필요) 순서.

결과는 엔진(engines/macro_fallback.py)이 읽는 raw 형태로만 돌려준다. 실패는 숨기지 않고 error 에 남기며, 그때 엔진이
보도 확인 수기 파일(SECONDARY) → 대체 지표(PROXY) → UNAVAILABLE 로 내려간다. 키 값은 어디에도 출력·저장하지 않는다.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Mapping

from .http import FetchError, HttpClient


def _fred_api(http: HttpClient, base: str, sid: str, key: str, start: str, as_of: str) -> dict[str, Any]:
    obs = json.loads(http.get(f"{base}/series/observations", params={
        "series_id": sid, "api_key": key, "file_type": "json", "observation_start": start, "observation_end": as_of,
        "realtime_start": as_of, "realtime_end": as_of}))
    if "error_message" in obs:
        raise FetchError(f"FRED 오류: {obs['error_message']}", kind="api", permanent=True)
    rows = [[o["date"], None if o.get("value") in (None, "", ".") else float(o["value"])] for o in obs.get("observations") or []]
    if not rows:
        raise FetchError("관측치 없음", kind="empty", permanent=True)
    vintage = None
    try:
        v = json.loads(http.get(f"{base}/series/vintagedates", params={
            "series_id": sid, "api_key": key, "file_type": "json", "realtime_start": "1776-07-04", "realtime_end": as_of, "sort_order": "desc", "limit": 1}))
        dates = v.get("vintage_dates") or []
        vintage = dates[0] if dates else None
    except FetchError:
        vintage = None  # 발표일을 모르면 엔진이 기간 기준으로 신선도를 본다
    return {"path": "PRIMARY", "observations": rows, "vintage": vintage, "error": None}


def _fred_csv(http: HttpClient, url: str, sid: str, start: str) -> dict[str, Any]:
    text = http.get(url, params={"id": sid, "cosd": start}).decode("utf-8", "replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or len(header) < 2:
        raise FetchError("CSV 머리 없음", kind="parse", permanent=True)
    rows = []
    for r in reader:
        if len(r) < 2:
            continue
        try:
            rows.append([r[0], None if r[1] in ("", ".") else float(r[1])])
        except ValueError:
            continue
    if not rows:
        raise FetchError("관측치 없음", kind="empty", permanent=True)
    return {"path": "MIRROR", "observations": rows, "vintage": None, "error": None}


def fetch_macro_raw(cfg: Mapping, *, api_key: str | None, http: HttpClient | None = None, as_of: datetime) -> dict[str, dict[str, Any]]:
    """{fred id: raw}. 공급 경로마다 실패 사유를 남긴다."""
    http = http or HttpClient(timeout_sec=20.0, retries=1)
    paths = cfg.get("paths") or {}
    start = (as_of - timedelta(days=366 * int(paths.get("observation_years", 8)))).date().isoformat()
    # FRED 의 '오늘' 은 미국 중부시간 날짜다. UTC 날짜를 그대로 realtime 으로 주면 한국 오전(= 미국 전날 밤)에 미래 vintage 라며 400 을 돌려준다(2026-10-14)
    day = as_of.astimezone(ZoneInfo("America/Chicago")).date().isoformat()
    out: dict[str, dict[str, Any]] = {}
    for spec in (cfg.get("series") or {}).values():
        sid = str(spec.get("fred", ""))
        if not sid or sid in out:
            continue
        errors: list[str] = []
        if api_key:
            try:
                out[sid] = _fred_api(http, str(paths.get("fred_api", "https://api.stlouisfed.org/fred")), sid, api_key, start, day)
                continue
            except FetchError as exc:
                errors.append(f"API {exc.kind}")
        else:
            errors.append("API 키 없음")
        try:
            out[sid] = _fred_csv(http, str(paths.get("fred_mirror_csv", "https://fred.stlouisfed.org/graph/fredgraph.csv")), sid, start)
            out[sid]["error"] = None
            out[sid]["note"] = " · ".join(errors)
            continue
        except FetchError as exc:
            errors.append(f"미러 {exc.kind}")
        out[sid] = {"path": None, "observations": [], "vintage": None, "error": " · ".join(errors)}
    return out
