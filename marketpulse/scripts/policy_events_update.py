"""
정책·지표 이벤트 파일 매일 갱신(2026-11-04) — data/policy_events/YYYY-MM-DD.json(KST 날짜).

이 스크립트는 값을 만들지 않는다. 할 수 있는 일은 셋뿐이다.
  draft     직전 파일을 오늘 날짜 파일로 이어 쓴다(collected 만 바꾼다). 이미 있으면 그대로 둔다.
  due       지난 일정(upcoming 의 날짜가 지났는데 결과가 policy/releases 에 없는 것)을 보여준다 — 조사할 목록.
  validate  형식 · 날짜(look-ahead) · 금리 산술 · 출처를 검사하고, FRED 로 대조할 수 있는 숫자는 발표일 vintage 로 대조한다.
결과값 · 컨센서스 · 표결 · 톤 은 출처가 있는 보도로 사람이(또는 조사 세션이) 채운다. 확인 못 한 값은 null 로 둔다 — 0 이 아니다.

    python -m marketpulse.scripts.policy_events_update draft [--date 2026-11-05]
    python -m marketpulse.scripts.policy_events_update due [--date ...]
    python -m marketpulse.scripts.policy_events_update validate [--date ... | --file F] [--no-fred]

종료 코드: validate 가 오류를 찾으면 1. 키 값은 출력하지 않는다(FRED_API_KEY 는 env 에서만).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

PKG = Path(__file__).resolve().parents[1]
DATA_DIR = PKG / "data" / "policy_events"
KST = ZoneInfo("Asia/Seoul")

BANKS = {"FED", "ECB", "BOJ", "BOK"}
DECISIONS = {"HIKE", "HOLD", "CUT"}
TONES = {"", "hawkish", "neutral", "dovish"}
RELEASE_MEASURES = {
    "us_cpi": {"headline_yoy", "headline_mom", "core_mom", "core_yoy"},
    "us_pce": {"headline_yoy", "headline_mom", "core_mom", "core_yoy"},
    "us_nfp": {"payrolls", "unemployment", "ahe"},
}
#: upcoming kind → 결과가 들어가는 곳(due 판정용)
KIND_TO_POLICY = {"fomc": "FED", "ecb": "ECB", "boj": "BOJ", "bok": "BOK"}
KIND_TO_RELEASE = {"us_cpi", "us_pce", "us_nfp"}

#: FRED 대조 — (시리즈, 계산, 허용 오차). 보도 숫자는 반올림이라 0.1 단위면 ±0.05(+여유)까지 같다고 본다.
#: YoY 는 BLS 가 비계절조정 지수로 발표하므로 NSA, MoM 은 계절조정(SA). PCE 는 SA 로 둘 다.
FRED_CHECKS: dict[str, dict[str, tuple[str, str, float]]] = {
    "us_cpi": {"headline_yoy": ("CPIAUCNS", "yoy", 0.06), "headline_mom": ("CPIAUCSL", "mom", 0.06),
               "core_yoy": ("CPILFENS", "yoy", 0.06), "core_mom": ("CPILFESL", "mom", 0.06)},
    "us_pce": {"headline_yoy": ("PCEPI", "yoy", 0.06), "headline_mom": ("PCEPI", "mom", 0.06),
               "core_yoy": ("PCEPILFE", "yoy", 0.06), "core_mom": ("PCEPILFE", "mom", 0.06)},
    "us_nfp": {"payrolls": ("PAYEMS", "diff", 1.0), "unemployment": ("UNRATE", "level", 0.001)},
}
POLICY_FRED = {"FED": ("DFEDTARU", "upper"), "ECB": ("ECBDFR", "single")}


# ── 파일 ────────────────────────────────────────────────
def kst_today(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(KST).date()


def files(data_dir: Path = DATA_DIR) -> list[Path]:
    return sorted(p for p in data_dir.glob("*.json") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem))


def latest_before(d: date, data_dir: Path = DATA_DIR) -> Path | None:
    c = [p for p in files(data_dir) if p.stem < d.isoformat()]
    return c[-1] if c else None


def draft(d: date, data_dir: Path = DATA_DIR) -> tuple[Path, bool]:
    """오늘 파일이 없으면 직전 파일을 이어 쓴다(collected 만 오늘). (경로, 새로 만들었는가)."""
    target = data_dir / f"{d.isoformat()}.json"
    if target.exists():
        return target, False
    prev = latest_before(d, data_dir)
    if prev is None:
        raise SystemExit("이어 쓸 직전 파일이 없습니다")
    doc = json.loads(prev.read_text(encoding="utf-8"))
    doc["collected"] = d.isoformat()
    base = re.sub(r"^(\d{4}-\d{2}-\d{2} 이어 쓰기\([^)]*\)\. )+", "", str(doc.get("note", "")))
    doc["note"] = f"{d.isoformat()} 이어 쓰기({prev.stem} 파일에서 — 새로 확인한 결과가 있으면 더한다). " + base
    # 지난 일정 중 결과가 이미 들어갔거나 판정 항목이 없는 것은 뺀다. 결과를 아직 못 찾은 것은 남겨 due 에 계속 보인다.
    pending = {(x["date"], x["kind"]) for x in due(doc, d) if x["target"] != "note_only"}
    doc["upcoming"] = [u for u in doc.get("upcoming") or [] if str(u.get("date")) >= d.isoformat() or (str(u.get("date")), u.get("kind")) in pending]
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return target, True


# ── 조사할 목록 ─────────────────────────────────────────
def due(doc: Mapping[str, Any], d: date) -> list[dict[str, Any]]:
    """날짜가 지난 upcoming 중 결과가 파일에 없는 것. d 당일 일정은 아직 결과 전으로 본다(KST 아침 실행)."""
    have_policy = {(p.get("bank"), p.get("date")) for p in doc.get("policy") or []}
    have_rel = {(r.get("key"), r.get("date")) for r in doc.get("releases") or []}
    out = []
    for u in doc.get("upcoming") or []:
        ud = str(u.get("date") or "")
        if not ud or ud >= d.isoformat():
            continue
        kind = str(u.get("kind") or "")
        if kind in KIND_TO_POLICY:
            done = (KIND_TO_POLICY[kind], ud) in have_policy
        elif kind in KIND_TO_RELEASE:
            done = (kind, ud) in have_rel
        else:
            done = None  # 판정 항목이 없는 일정(PPI · 소매판매 등) — 메모만
        if done is not True:
            out.append({"date": ud, "kind": kind, "name": u.get("name"), "target": "policy" if kind in KIND_TO_POLICY else ("release" if kind in KIND_TO_RELEASE else "note_only")})
    return out


# ── 검사 ────────────────────────────────────────────────
def _num(s: Any) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(s or ""))]


def _srcs_ok(item: Mapping, where: str, errs: list[str]) -> None:
    ss = item.get("sources") or []
    if not ss:
        errs.append(f"{where}: 출처 없음")
    for s in ss:
        if not str(s.get("url", "")).startswith(("http://", "https://")) or not s.get("title"):
            errs.append(f"{where}: 출처 형식(title · url) 오류")


def validate_doc(doc: Mapping[str, Any], stem: str, *, prev: Mapping[str, Any] | None = None) -> tuple[list[str], list[str]]:
    """(오류, 경고). 오류가 있으면 쓰지 않는다."""
    errs: list[str] = []
    warns: list[str] = []
    for k in ("collected", "note", "policy", "releases", "upcoming"):
        if k not in doc:
            errs.append(f"키 없음: {k}")
    if errs:
        return errs, warns
    if doc["collected"] != stem:
        errs.append(f"collected({doc['collected']}) 가 파일 날짜({stem})와 다름")
    day = stem
    # 중앙은행 — 은행마다 최신 결정 하나
    seen: set[str] = set()
    for p in doc["policy"]:
        w = f"policy {p.get('bank')} {p.get('date')}"
        if p.get("bank") not in BANKS:
            errs.append(f"{w}: bank 값")
        if p.get("bank") in seen:
            errs.append(f"{w}: 같은 은행이 두 번")
        seen.add(str(p.get("bank")))
        if str(p.get("decision", "")).upper() not in DECISIONS:
            errs.append(f"{w}: decision 값")
        if str(p.get("guidance", "")).lower() not in TONES:
            errs.append(f"{w}: guidance 값")
        pd = str(p.get("date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pd):
            errs.append(f"{w}: date 형식")
        elif pd >= day:
            errs.append(f"{w}: 파일 날짜 이후(또는 당일) 결정 — look-ahead")
        nm = str(p.get("next_meeting") or "")
        if nm and pd and nm <= pd:
            errs.append(f"{w}: next_meeting 이 결정일보다 앞")
        # 금리 산술: 현재 − 이전 = change_bp (범위는 위쪽 끝)
        dec, bp = str(p.get("decision", "")).upper(), p.get("change_bp")
        a, b = _num(p.get("previous_rate")), _num(p.get("current_rate"))
        if a and b:
            diff = round((b[-1] - a[-1]) * 100)
            want = 0 if dec == "HOLD" else (abs(int(bp or 0)) * (1 if dec == "HIKE" else -1))
            if diff != want:
                errs.append(f"{w}: 금리 산술 불일치({p.get('previous_rate')} → {p.get('current_rate')} vs {dec} {bp}bp)")
        _srcs_ok(p, w, errs)
        if prev:
            old = next((q for q in prev.get("policy") or [] if q.get("bank") == p.get("bank")), None)
            if old and str(old.get("date")) > pd:
                errs.append(f"{w}: 직전 파일({old.get('date')})보다 오래된 결정으로 바뀜")
            if old and str(old.get("date")) < pd and _num(old.get("current_rate")) and a and _num(old.get("current_rate"))[-1] != a[-1]:
                warns.append(f"{w}: previous_rate 가 직전 파일 current_rate({old.get('current_rate')})와 다름")
    if prev:
        for q in prev.get("policy") or []:
            if q.get("bank") not in seen:
                errs.append(f"policy {q.get('bank')}: 직전 파일에 있던 은행이 빠짐")
    # 발표
    keys: set[tuple[str, str]] = set()
    for r in doc["releases"]:
        w = f"release {r.get('key')} {r.get('period')}"
        if r.get("key") not in RELEASE_MEASURES:
            errs.append(f"{w}: key 값(판정 항목이 있는 us_cpi · us_pce · us_nfp 만)")
            continue
        kp = (str(r.get("key")), str(r.get("period")))
        if kp in keys:
            errs.append(f"{w}: 같은 발표가 두 번")
        keys.add(kp)
        rd = str(r.get("date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rd):
            errs.append(f"{w}: date 형식")
        elif rd >= day:
            errs.append(f"{w}: 파일 날짜 이후(또는 당일) 발표 — look-ahead")
        if not re.fullmatch(r"\d{4}-\d{2}", str(r.get("period") or "")):
            errs.append(f"{w}: period 형식(YYYY-MM)")
        for m in r.get("measures") or []:
            if m.get("key") not in RELEASE_MEASURES[r["key"]]:
                errs.append(f"{w}: measure key {m.get('key')}")
            for f in ("actual", "consensus", "prior"):
                v = m.get(f)
                if v is not None and not isinstance(v, (int, float)):
                    errs.append(f"{w}: {m.get('key')}.{f} 는 숫자 또는 null")
        _srcs_ok(r, w, errs)
    if prev:
        for r in prev.get("releases") or []:
            if (str(r.get("key")), str(r.get("period"))) not in keys and r.get("key") in RELEASE_MEASURES:
                errs.append(f"release {r.get('key')} {r.get('period')}: 직전 파일에 있던 발표가 빠짐")
    # 일정
    for u in doc["upcoming"]:
        w = f"upcoming {u.get('kind')} {u.get('date')}"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(u.get("date") or "")) or not u.get("name") or not u.get("kind"):
            errs.append(f"{w}: date · kind · name 필요")
        _srcs_ok(u, w, errs)
    return errs, warns


# ── FRED 대조(발표일 vintage) ─────────────────────────
Fetch = Callable[[str, str], list[tuple[str, float | None]]]


def fred_fetcher(api_key: str | None) -> Fetch | None:
    if not api_key:
        return None
    sys.path.insert(0, str(PKG.parent))
    from marketpulse.adapters.http import HttpClient
    from marketpulse.adapters.macro_fred import _fred_api
    http = HttpClient(timeout_sec=20.0, retries=1)

    def get(sid: str, realtime: str) -> list[tuple[str, float | None]]:
        start = (date.fromisoformat(realtime) - timedelta(days=500)).isoformat()
        r = _fred_api(http, "https://api.stlouisfed.org/fred", sid, api_key, start, realtime)
        return [(d, v) for d, v in r["observations"]]
    return get


def _calc(obs: list[tuple[str, float | None]], period: str, how: str) -> float | None:
    by = {d[:7]: v for d, v in obs}
    y, m = map(int, period.split("-"))
    cur = by.get(period)
    pm = f"{y if m > 1 else y - 1}-{(m - 1) or 12:02d}"
    py = f"{y - 1}-{m:02d}"
    if cur is None:
        return None
    if how == "level":
        return cur
    if how == "diff":
        return None if by.get(pm) is None else cur - by[pm]
    base = by.get(pm if how == "mom" else py)
    return None if not base else (cur / base - 1) * 100


def fred_check(doc: Mapping[str, Any], fetch: Fetch) -> tuple[list[str], list[str]]:
    """보도 숫자(actual)를 발표일 vintage FRED 와 대조. 못 잰 것은 경고(값을 바꾸지 않는다)."""
    errs: list[str] = []
    warns: list[str] = []
    cache: dict[tuple[str, str], list] = {}

    def obs(sid: str, rt: str) -> list:
        if (sid, rt) not in cache:
            cache[(sid, rt)] = fetch(sid, rt)
        return cache[(sid, rt)]
    for r in doc.get("releases") or []:
        spec = FRED_CHECKS.get(str(r.get("key")))
        if not spec:
            continue
        for m in r.get("measures") or []:
            chk = spec.get(str(m.get("key")))
            if not chk or m.get("actual") is None:
                continue
            sid, how, tol = chk
            w = f"FRED {r['key']} {r.get('period')} {m['key']}"
            try:
                v = _calc(obs(sid, str(r["date"])), str(r["period"]), how)
            except Exception as exc:  # 네트워크 · 키 · 미발표 — 대조 못 함은 오류가 아니다
                warns.append(f"{w}: 대조 못 함({type(exc).__name__})")
                continue
            if v is None:
                warns.append(f"{w}: 그 vintage 에 값 없음")
            elif abs(v - float(m["actual"])) > tol:
                errs.append(f"{w}: 보도 {m['actual']} vs FRED {v:.3f}")
    for p in doc.get("policy") or []:
        spec = POLICY_FRED.get(str(p.get("bank")))
        nums = _num(p.get("current_rate"))
        if not spec or not nums:
            continue
        sid, how = spec
        eff = (date.fromisoformat(str(p["date"])) + timedelta(days=7)).isoformat()  # 적용일(FOMC 다음 날 · ECB 다음 주 수요일)을 지난 시점
        try:
            ob = [v for d, v in obs(sid, min(eff, doc["collected"])) if d <= eff and v is not None]
        except Exception as exc:
            warns.append(f"FRED {p['bank']} 정책금리: 대조 못 함({type(exc).__name__})")
            continue
        if not ob:
            warns.append(f"FRED {p['bank']} 정책금리: 값 없음")
        elif abs(ob[-1] - nums[-1]) > 0.001:
            errs.append(f"FRED {p['bank']} 정책금리: 파일 {p.get('current_rate')} vs FRED {ob[-1]}")
    return errs, warns


# ── CLI ─────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["draft", "due", "validate"])
    ap.add_argument("--date", help="KST 날짜(기본: 오늘 KST)")
    ap.add_argument("--file", help="validate 대상 파일(기본: --date 파일)")
    ap.add_argument("--no-fred", action="store_true")
    a = ap.parse_args(argv)
    d = date.fromisoformat(a.date) if a.date else kst_today()
    if a.cmd == "draft":
        path, new = draft(d)
        print(("새로 만듦: " if new else "이미 있음: ") + str(path))
        a.cmd = "due"
    path = Path(a.file) if a.file else DATA_DIR / f"{d.isoformat()}.json"
    if not path.exists():
        print(f"파일 없음: {path}", file=sys.stderr)
        return 1
    doc = json.loads(path.read_text(encoding="utf-8"))
    if a.cmd == "due":
        items = due(doc, d if a.date else date.fromisoformat(path.stem))
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return 0
    prev_p = latest_before(date.fromisoformat(path.stem), path.parent)
    prev = json.loads(prev_p.read_text(encoding="utf-8")) if prev_p else None
    errs, warns = validate_doc(doc, path.stem, prev=prev)
    if not a.no_fred:
        f = fred_fetcher(os.environ.get("FRED_API_KEY"))
        if f is None:
            warns.append("FRED_API_KEY 없음 — FRED 대조 생략")
        else:
            e2, w2 = fred_check(doc, f)
            errs += e2
            warns += w2
    for w in warns:
        print("WARN ", w)
    for e in errs:
        print("ERROR", e)
    print(f"{path.name}: {'OK' if not errs else 'FAIL'} · 오류 {len(errs)} · 경고 {len(warns)}")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
