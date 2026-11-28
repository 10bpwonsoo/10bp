"""RSS 만 지금 다시 받아 앞서 받은 기사 파일들과 id 로 합친다 — 가격 수집(07:00)이 기준 시각(07:30 KST)보다 먼저 끝나는 날,
07:30 이 지난 뒤 기사 창의 끝(…~ D 07:30)까지 채우는 데 쓴다. 기사 내용은 손대지 않는다. cutoff 뒤 기사는 재구성 코드가 자른다.

    python tools/daily_snapshot/fetch_news.py <out.json> [앞서 받은 news_rss.json ...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from marketpulse.adapters.registry import build_news_adapter  # noqa: E402
from marketpulse.config.settings import Settings  # noqa: E402
from marketpulse.models.common import utcnow  # noqa: E402

out = Path(sys.argv[1])
merged: dict[str, dict] = {}
counts = {}
for p in sys.argv[2:]:
    f = Path(p)
    if not f.exists():
        counts[f.name] = "없음"
        continue
    items = json.loads(f.read_text(encoding="utf-8"))
    counts[f"{f.parent.name}/{f.name}"] = len(items)
    for it in items:
        merged.setdefault(str(it.get("id")), it)
now = utcnow()
fresh = [i.model_dump(mode="json") for i in build_news_adapter(Settings(data_mode="DELAYED", llm_enabled=False, news_search="off")).fetch_news(limit=500, as_of=now)]
new = 0
for it in fresh:
    if str(it.get("id")) not in merged:
        new += 1
    merged[str(it.get("id"))] = it  # 같은 id 는 방금 받은 것으로
items = sorted(merged.values(), key=lambda x: str(x.get("published_at") or ""))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"fetched_at": now.isoformat(), "fresh": len(fresh), "new": new, "merged": len(items), "from": counts,
                  "first": items[0].get("published_at") if items else None, "last": items[-1].get("published_at") if items else None}, ensure_ascii=False))
