"""Daily Snapshot 한 날짜 재구성 — 그 날짜 07:30 KST cutoff(historical_backfill 규칙). 오늘 날짜여도 '지금 데이터' 저장이 아니다.

    python tools/daily_snapshot/build_day.py 2026-11-11 <inputs_dir> status    # 입력 상태만(OK · STALE · MISSING, FULL / PARTIAL 판정) — 아무것도 쓰지 않는다
    python tools/daily_snapshot/build_day.py 2026-11-11 <inputs_dir> context   # 컨텍스트만(history 복사본 위, 저장 안 함) — 해석 세션본 작성용
    python tools/daily_snapshot/build_day.py 2026-11-11 <inputs_dir> full      # 확정 저장(archive · history 행 · 캡처). 판정이 PARTIAL 이면 거절(종료 코드 3)
    python tools/daily_snapshot/build_day.py 2026-11-11 <inputs_dir> partial   # PARTIAL 저장(archive/partial · 캡처 <날짜>-partial). history · regime 상태는 쓰지 않는다

2026-11-25~: 입력 상태 판정(marketpulse/archive/input_status.py · config/collection.yaml)을 먼저 본다.
  · 마지막 봉이 빠진 계열(STALE)은 계산에서 뺀다 — 전날 종가를 오늘 종가처럼 쓰지 않는다.
  · 핵심 계열이 모자라면 PARTIAL: 공식 regime 판정을 보류하고 따로 저장한다. 정상 입력을 받은 뒤 full 로 확정본을 만든다.
캡처 폴더 marketpulse/data/captures/<날짜>-backfill/ 에 manual_tags.json · *_session.json 이 있으면 쓴다.
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from marketpulse.archive.backfill import PartialInputsError, build_one, build_partial  # noqa: E402
from marketpulse.archive.input_status import assess  # noqa: E402
from marketpulse.archive.reconstruct import cutoff_for  # noqa: E402
from marketpulse.archive.service import DailyArchiveService  # noqa: E402
from marketpulse.archive.store import ArchiveStore  # noqa: E402
from marketpulse.config.settings import get_settings  # noqa: E402

d = date.fromisoformat(sys.argv[1])
inputs = Path(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else "context"
if mode not in ("status", "context", "full", "partial"):
    raise SystemExit(f"모드는 status · context · full · partial 중 하나다: {mode}")
svc = DailyArchiveService(ArchiveStore(get_settings().archive_dir))
cut = cutoff_for(d, str(svc.cfg.get("cutoff_time", "07:30")))
print("cutoff", cut.isoformat())

st = assess(inputs, cut)
gate = st["gate"]
print("입력 상태", json.dumps(st["counts"], ensure_ascii=False))
for g in ("base", "universe", "basket"):
    if st["stale"][g]:
        print(f"  STALE {g}({len(st['stale'][g])}) — 계산에서 뺀다:", ", ".join(f"{i}[{(st['series'][g][i].get('last_bar') or '')[:10]}]" for i in st["stale"][g]))
    if st["missing"][g]:
        print(f"  MISSING {g}({len(st['missing'][g])}):", ", ".join(st["missing"][g]))
if st["closed_suspect"]:
    print("  휴장으로 본 시장(확인 필요):", st["closed_suspect"])
print("판정", gate["verdict"], "· 핵심", f"{gate['core_ok_ratio']:.0%}", *(["—", " · ".join(gate["reasons"])] if gate["reasons"] else []))
if mode == "status":
    raise SystemExit(0 if gate["verdict"] == "FULL" else 3)

if mode == "partial":
    if gate["verdict"] == "FULL":
        raise SystemExit("입력 판정이 FULL 이다 — partial 이 아니라 full 로 저장한다")
    res, info = build_partial(svc, d, inputs=inputs, cutoff=cut, input_status=st)
    print("PARTIAL 저장", info["path"], "· 이전 PARTIAL", info["replaced"], "· 빠진 섹션", sorted(info["errors"]))
else:
    try:
        res, cap = build_one(svc, d, inputs=inputs, cutoff=cut, latest=False, context_only=mode == "context", input_status=st)
    except PartialInputsError as exc:
        print("거절:", exc)
        print("→ 받은 데이터로 PARTIAL 저장:  build_day.py", d, inputs, "partial   (공식 regime 판정 보류 · history 는 쓰지 않는다)")
        raise SystemExit(3)
    print("CONTEXT ONLY" + (" (판정 PARTIAL — 이 컨텍스트로 확정 저장은 하지 않는다)" if gate["verdict"] != "FULL" else "") if cap is None else cap.line())
print(json.dumps({k: res.summary.get(k) for k in ("market", "ai", "rates", "oil", "news", "semiconductor_cycle", "cockpit")}, ensure_ascii=False, default=str))
