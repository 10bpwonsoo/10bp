"""계열마다 마지막 봉이 가장 늦은 수집분을 고른다(같으면 봉이 많은 쪽). 값은 손대지 않는다."""
import json, sys
from pathlib import Path
out = Path(sys.argv[1]); srcs = [Path(p) for p in sys.argv[2:]]
out.mkdir(parents=True, exist_ok=True)
report = {"merged_from": [s.name for s in srcs], "pick": {}}
for n in ("series_base", "series_universe", "series_basket"):
    best = {}
    for s in srcs:
        f = s / f"{n}.json"
        if not f.exists():
            continue
        for k, v in json.loads(f.read_text()).items():
            ts = v.get("timestamps") or []
            key = (ts[-1] if ts else "", len(ts))
            if k not in best or key > best[k][0]:
                best[k] = (key, v, s.name)
    (out / f"{n}.json").write_text(json.dumps({k: b[1] for k, b in best.items()}))
    report["pick"][n] = {k: [b[2], b[0][0][:16]] for k, b in best.items()}
print(json.dumps({n: len(v) for n, v in report["pick"].items()}))
(out / "merge_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
