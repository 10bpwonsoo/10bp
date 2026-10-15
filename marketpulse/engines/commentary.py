"""
Claude Commentary 적재 (2026-09-16 신설).

Anthropic API 를 부르지 않는다. 수기 캡처(manual extractor)와 같은 방식으로
Claude Code 가 데이터를 읽고 쓴 해설을 data/commentary/<date>.json 에 넣으면
여기서 읽는다. 각 해설은 FACT / NEWS / ANALYST / INTERPRETATION / UNKNOWN 을
분리해 저장한다 (요구 27). as_of 로부터 max_age_hours 를 넘긴 해설은
stale=True 로 표시하되 버리지 않는다 — 언제 쓴 것인지 화면이 말한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from ..config.registry import get_intelligence_config
from ..models.intelligence import Commentary

ENGINE_VERSION = "0.1.0"


def load_commentary(directory: Path, as_of: datetime, *, config_dir=None) -> list[Commentary]:
    cfg = get_intelligence_config(config_dir).get("commentary", {})
    max_age = timedelta(hours=float(cfg.get("max_age_hours", 72)))
    if not directory.exists():
        return []
    out: list[Commentary] = []
    for path in sorted(directory.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for raw in doc.get("commentary", []) if isinstance(doc, dict) else doc:
            try:
                c = Commentary.model_validate(raw)
            except Exception:
                continue
            c_as_of = c.as_of if c.as_of.tzinfo else c.as_of.replace(tzinfo=timezone.utc)
            if c_as_of > as_of + timedelta(hours=1):
                continue  # 미래의 해설은 쓰지 않는다
            out.append(c.model_copy(update={"stale": (as_of - c_as_of) > max_age}))
    # 같은 entity 는 최신 것 하나만
    latest: dict[tuple[str, str], Commentary] = {}
    for c in out:
        key = (c.kind, c.entity)
        if key not in latest or c.as_of > latest[key].as_of:
            latest[key] = c
    return sorted(latest.values(), key=lambda c: (c.kind, c.entity))


def pick(commentary: Sequence[Commentary], kind: str, entity: str) -> Commentary | None:
    return next((c for c in commentary if c.kind == kind and c.entity == entity), None)
