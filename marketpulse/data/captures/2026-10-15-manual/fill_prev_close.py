"""10/14 캡처 보정 — Yahoo 일봉에서 '오늘 바로 앞 거래일' 봉이 통째로 비었다(o·c 모두 null: ^KS11 · ^KQ11 · ^N225 · CL=F · DX-Y.NYB 등, 10/13).
같은 공급자(Yahoo)의 60분봉 응답 meta.previousClose 가 그 날 공식 종가다(코스피 6,035.35 — 보도 '6035 마감'과 일치).
규칙: 일봉 응답에서 마지막 봉(오늘) 바로 앞의 봉 하나만 null 이고, 그 앞 봉은 값이 있을 때만 그 날짜에 previousClose 를 넣는다.
두 개 이상 비었거나 previousClose 가 없으면 건드리지 않는다(결측은 결측). 키는 쓰지 않는다.
제외: ① 환율(=X) — Yahoo 가 FX 일봉을 전날 23:00 UTC 에 찍어 빈 봉이 '오늘 세션' 이다(previousClose 는 그 앞 봉의 값이라 넣으면 하루가 밀린다).
② previousClose 가 그 앞 봉 종가와 같으면 휴장일(예: 10/12 콜럼버스데이 채권시장 → MOVE)의 이월값이라 넣지 않는다."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from marketpulse.adapters.http import FetchError, HttpClient
from marketpulse.models.market import MarketSeries
OUT = Path(__file__).resolve().parent
raw = json.loads((OUT / "series_live.json").read_text(encoding="utf-8"))
h = HttpClient(timeout_sec=15.0, retries=1)
filled, skipped = [], []
for iid, v in raw.items():
    src = str((v.get("meta") or {}).get("source", ""))
    if not src.startswith("yahoo:"):
        continue
    sym = src.split(":", 1)[1]
    if sym.endswith("=X"):
        continue
    try:
        d = json.loads(h.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym)}", params={"range": "10d", "interval": "1d"}))["chart"]["result"][0]
    except (FetchError, KeyError, ValueError) as exc:
        skipped.append((iid, f"daily {exc}")); continue
    ts, closes = d.get("timestamp") or [], (d["indicators"]["quote"][0].get("close") or [])
    if len(ts) < 3 or closes[-1] is None or closes[-2] is not None or closes[-3] is None:
        continue  # 비어 있지 않거나, 둘 이상 비었거나, 패턴이 다르다
    try:
        m = json.loads(h.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym)}", params={"range": "5d", "interval": "60m"}))["chart"]["result"][0]["meta"]
    except (FetchError, KeyError, ValueError) as exc:
        skipped.append((iid, f"60m {exc}")); continue
    pc = m.get("previousClose")
    if pc is None:
        skipped.append((iid, "previousClose 없음")); continue
    if abs(float(pc) - float(closes[-3])) <= 1e-4 * abs(float(closes[-3])):
        skipped.append((iid, "previousClose = 앞 봉 종가(휴장 이월값)")); continue
    day = datetime.fromtimestamp(ts[-2], tz=timezone.utc)
    s = MarketSeries.model_validate(v)
    if any(t.date() == day.date() for t in s.timestamps):
        continue
    scale = 1.0
    pts = sorted(list(zip(s.timestamps, s.values)) + [(day, float(pc) * scale)])
    s = s.model_copy(update={"timestamps": [p[0] for p in pts], "values": [p[1] for p in pts]})
    raw[iid] = s.model_dump(mode="json")
    filled.append((iid, sym, day.date().isoformat(), round(float(pc), 2)))
print("filled", filled); print("skipped", skipped)
(OUT / "series_live.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
rep = json.loads((OUT / "fetch_report.json").read_text(encoding="utf-8")); rep["fill_prev_close"] = {"filled": filled, "skipped": skipped}
(OUT / "fetch_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
