"""수집한 계열의 단위 불연속 검사 — 최근 60봉에서 하루 |변화| > 35% 를 보여준다(2026-11-06 SOXX · ITA: 분할 조정이 섞인 공급자 응답).
값을 고치지 않는다. 불연속이 공급자 단위 문제면 그 계열을 그날 입력에서 빼고(결측) 캡처 폴더 input_merge_report.json 에 이유를 남긴다.

    python tools/daily_snapshot/scan_units.py <inputs_dir>
"""
import json
import sys
from pathlib import Path

KNOWN = {"VIX_RV_SPX", "HBM4_CONTRACT"}  # 원래 변동이 큰 파생 · 분기 앵커
p = Path(sys.argv[1])
for n in ("series_base", "series_universe", "series_basket"):
    f = p / f"{n}.json"
    if not f.exists():
        continue
    for k, v in json.loads(f.read_text()).items():
        x, t = v["values"][-60:], v["timestamps"][-60:]
        bad = [(t[i][:10], round(x[i] / x[i - 1] - 1, 3)) for i in range(1, len(x)) if x[i] and x[i - 1] and abs(x[i] / x[i - 1] - 1) > 0.35]
        if bad and k not in KNOWN:
            print(n, k, bad[:6])
