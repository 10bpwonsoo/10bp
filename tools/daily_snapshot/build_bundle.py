"""정적 배포본 빌더 (2026-10-12 복원판, 2026-11-11 저장소로 이동).

컨테이너 재시작으로 원래 빌더가 지워져, 마지막으로 발행된 배포본(V66)에서 틀(dash_template.html)을 뽑아 다시 만들었다.
아티팩트 CSP 가 같은 출처의 하위 리소스를 막으므로 JS·CSS 를 한 파일 안에 인라인하고, 백엔드 대신 window.fetch 를
가로채 캡처한 스냅샷을 돌려준다. 숫자는 전부 캡처 파일 그대로다 — 화면용으로 손대지 않는다.

사용: python tools/daily_snapshot/build_bundle.py <capture_dir> "<배포본 메모 문장>" [<out.html>]
      (먼저 cd frontend && npm run build — frontend/dist/assets 의 JS · CSS 를 인라인한다)
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DIST = ROOT / "frontend" / "dist" / "assets"
CAP = pathlib.Path(sys.argv[1])
NOTE = sys.argv[2]

css = next(DIST.glob("*.css")).read_text(encoding="utf-8").rstrip("\n")
js = next(DIST.glob("*.js")).read_text(encoding="utf-8").rstrip("\n")
rd = lambda n: json.loads((CAP / n).read_text(encoding="utf-8"))

DATA = {
    "snapshots": {"live": rd("live.json")},
    "news": {"live": rd("news_live.json")},
    "investment": {"live": rd("investment.json")},
    "history": {"live": rd("state_history.json")},
    "scenario_check": {"live": rd("scenario_check.json")},
    "oil_regime": {"live": rd("oil_regime.json")},
    "rates_regime": {"live": rd("rates_regime.json")},
    "ai_regime": {"live": rd("ai_regime.json")},
    "cockpit": {"live": rd("cockpit.json")},
    "analyst_views": {"live": rd("analyst_views.json")},
    "daily_history": {"live": rd("daily_history.json")},
    # 반도체 사이클 탭(2026-10-23~) — 캡처에 없으면 null → 화면은 '받지 못했다' (지금 값으로 메우지 않는다)
    "semiconductor_cycle": {"live": rd("semiconductor_cycle.json") if (CAP / "semiconductor_cycle.json").exists() else None},
    # MARKET OVERVIEW(2026-11-12~) — LLM 시장 종합. 캡처에 없으면 null → 화면은 '저장되지 않음'
    "market_overview": {"live": rd("market_overview.json") if (CAP / "market_overview.json").exists() else None},
}
# History 는 저장 당시 그대로(저장 키 기준) — KST view 로 저장된 섹션(10/22)만 API 와 같은 storage_view 로 다시 조립한다(2026-10-22). 파일은 그대로.
sys.path.insert(0, str(ROOT))
from datetime import datetime as _dt
from marketpulse.history.storage_view import doc_as_of, storage_view
from marketpulse.history.manager import DailySnapshotManager
from marketpulse.history.store import JsonDirStore
_mgr = DailySnapshotManager(JsonDirStore(ROOT / "marketpulse" / "data" / "history"))
_live_doc = {"cockpit": DATA["cockpit"]["live"], "market_state_history": DATA["history"]["live"], "daily_history": DATA["daily_history"]["live"], "ai_regime": DATA["ai_regime"]["live"]}
_lv = storage_view(_live_doc, as_of=_dt.fromisoformat(DATA["snapshots"]["live"]["as_of"].replace("Z", "+00:00")), manager=_mgr)
DATA["cockpit"]["live"], DATA["history"]["live"], DATA["daily_history"]["live"], DATA["ai_regime"]["live"] = _lv["cockpit"], _lv["market_state_history"], _lv["daily_history"], _lv["ai_regime"]

# Daily Full Dashboard Archive — 저장소의 최근 저장본을 함께 넣는다(아티팩트 한도 16MB 라 config 의 bundle_max_dates 개).
import yaml
ARCH = ROOT / "marketpulse" / "data" / "archive"
acfg = yaml.safe_load((ROOT / "marketpulse" / "config" / "archive.yaml").read_text(encoding="utf-8"))
_ix = json.loads((ARCH / "index.json").read_text(encoding="utf-8")) if (ARCH / "index.json").exists() else {}
aidx = _ix.get("entries") or [r for r in _ix.get("dates", []) if isinstance(r, dict)]
# 2026-11-04~: 날짜별 저장본을 gzip+base64 로 넣고 화면이 고른 날짜만 브라우저에서 푼다(DecompressionStream).
# bundle_max_dates 0 = 전부. 내용은 저장본 그대로(storage_view 조립만 — 이전과 같다), 담는 방식만 압축.
import gzip, base64
_maxd = int(acfg.get("bundle_max_dates", 0))
if _maxd > 0:
    aidx = aidx[:_maxd]
adocs = {r["date"]: json.loads((ARCH / r["date"][:4] / r["date"][5:7] / f"{r['date']}.json").read_text(encoding="utf-8")) for r in aidx}
adocs = {k: storage_view(v, as_of=doc_as_of(v), manager=_mgr) for k, v in adocs.items()}
_raw = {k: json.dumps(v, ensure_ascii=False, separators=(",", ":")).encode("utf-8") for k, v in adocs.items()}
azip = {k: base64.b64encode(gzip.compress(b, compresslevel=9, mtime=0)).decode("ascii") for k, b in _raw.items()}
print("archive raw", sum(len(b) for b in _raw.values()) // 1024, "KB → gzip+b64", sum(len(z) for z in azip.values()) // 1024, "KB")
archive_js = json.dumps({"index": aidx, "z": azip}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
data_js = json.dumps(DATA, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")  # </script> 조기 종료 방지
note_html = NOTE.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\\", "\\\\").replace("'", "\\'")

tpl = (HERE / "dash_template.html").read_text(encoding="utf-8")
html = (tpl.replace("@@CSS@@", css)
           .replace("@@NOTE_JSON@@", json.dumps(NOTE, ensure_ascii=False))
           .replace("@@NOTE_HTML@@", note_html)
           .replace("@@DATA@@", data_js)
           .replace("@@ARCHIVE@@", archive_js)
           .replace("@@JS@@", js.replace("</script", "<\\/script")))
for k in ("@@CSS@@", "@@DATA@@", "@@ARCHIVE@@", "@@JS@@", "@@NOTE_JSON@@", "@@NOTE_HTML@@"):
    assert k not in html, k
out = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "frontend" / "dist-bundle" / "index.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html, encoding="utf-8")
live = DATA["snapshots"]["live"]
print(out, f"{out.stat().st_size // 1024} KB")
print("live as_of:", live["as_of"][:16], "| state:", live["market_state"]["primary_label"], "| conf:", round(live["market_state"]["confidence"], 1))
print("archive dates:", [r["date"] for r in aidx])
print("cockpit now:", DATA["cockpit"]["live"]["market_now"]["label_text"], "| tabs:", [c["title"].split(" — ")[0] for c in DATA["scenario_check"]["live"]])
