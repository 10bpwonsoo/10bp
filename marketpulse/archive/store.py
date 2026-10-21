"""
Full dashboard archive 저장소 — 날짜별 JSON 파일 하나, 생성 후 불변.

    {root}/YYYY/MM/YYYY-MM-DD.json     그날 화면 전체 (schema_version 포함)
    {root}/index.json                  날짜 · 상태 요약 (파일이 진실이고, index 는 다시 만들 수 있는 요약이다)
    {root}/superseded/                 명시적 correction 으로 교체된 이전 파일 (지우지 않는다)

쓰기는 `.tmp` 에 쓰고 다시 읽어 검증한 뒤 최종 이름으로 옮긴다. 최종 이름은 hard link 로 만들어
같은 날짜 파일이 이미 있으면 실패한다 — 정기 저장이 기존 저장본을 덮어쓸 길이 없다.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ArchiveExistsError(FileExistsError):
    """같은 날짜 저장본이 이미 있다. 정기 저장은 덮어쓰지 않는다 — correction 경로만 교체한다."""


class ArchiveNotFoundError(FileNotFoundError):
    pass


def parse_date(text: str) -> date:
    if not DATE_RE.match(text or ""):
        raise ValueError(f"날짜 형식은 YYYY-MM-DD 다: {text!r}")
    return date.fromisoformat(text)


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


class ArchiveStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    # ── 경로 ──────────────────────────────────────────────
    def path_for(self, d: date) -> Path:
        return self.root / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.isoformat()}.json"

    def exists(self, d: date) -> bool:
        return self.path_for(d).is_file()

    # ── 읽기 ──────────────────────────────────────────────
    def dates(self) -> list[date]:
        """저장된 날짜, 최신순. 파일을 직접 훑는다(index 가 깨져도 목록은 맞다)."""
        if not self.root.is_dir():
            return []
        out = []
        for p in self.root.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/*.json"):
            stem = p.name[:-5]
            if DATE_RE.match(stem):
                out.append(date.fromisoformat(stem))
        return sorted(set(out), reverse=True)

    def read(self, d: date) -> dict[str, Any]:
        p = self.path_for(d)
        if not p.is_file():
            raise ArchiveNotFoundError(f"{d.isoformat()} 저장 화면이 없습니다")
        return json.loads(p.read_text(encoding="utf-8"))

    def index(self) -> list[dict[str, Any]]:
        """날짜별 요약(최신순). index.json 이 없거나 파일과 어긋나면 파일에서 다시 만든다."""
        want = [d.isoformat() for d in self.dates()]
        p = self.root / "index.json"
        try:
            rows = json.loads(p.read_text(encoding="utf-8")).get("dates", [])
            if [r.get("date") for r in rows] == want:
                return rows
        except (OSError, ValueError, AttributeError):
            pass
        return self.rebuild_index()

    # ── 쓰기 ──────────────────────────────────────────────
    def write_new(self, d: date, payload: dict[str, Any]) -> Path:
        """새 날짜만 쓴다. 이미 있으면 ArchiveExistsError — 기존 파일은 그대로."""
        final = self.path_for(d)
        if final.exists():
            raise ArchiveExistsError(f"{d.isoformat()} 저장본이 이미 있습니다: {final}")
        tmp = self._write_tmp(final, payload)
        try:
            try:
                os.link(tmp, final)  # 원자적이고, 최종 파일이 이미 있으면 실패한다(덮어쓰지 않는다)
            except FileExistsError as exc:
                raise ArchiveExistsError(f"{d.isoformat()} 저장본이 이미 있습니다: {final}") from exc
            except OSError:
                if final.exists():  # hard link 를 못 쓰는 파일시스템 — 마지막으로 한 번 더 확인하고 rename
                    raise ArchiveExistsError(f"{d.isoformat()} 저장본이 이미 있습니다: {final}")
                os.replace(tmp, final)
        finally:
            if tmp.exists():
                tmp.unlink()
        self.rebuild_index()
        return final

    def replace_for_correction(self, d: date, payload: dict[str, Any]) -> tuple[Path, Path]:
        """명시적 correction 전용. 이전 파일은 superseded/ 로 옮겨 남긴다."""
        final = self.path_for(d)
        if not final.exists():
            raise ArchiveNotFoundError(f"{d.isoformat()} 저장본이 없어 correction 할 수 없습니다")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        keep = self.root / "superseded" / f"{d.isoformat()}.{stamp}.json"
        keep.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._write_tmp(final, payload)
        os.replace(final, keep)
        os.replace(tmp, final)
        self.rebuild_index()
        return final, keep

    def rebuild_index(self) -> list[dict[str, Any]]:
        rows = []
        for d in self.dates():
            try:
                a = json.loads(self.path_for(d).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                rows.append({"date": d.isoformat(), "archive_status": "UNREADABLE"})
                continue
            meta = a.get("meta") or {}
            rows.append({
                "date": d.isoformat(),
                "archive_status": a.get("archive_status"),
                "schema_version": a.get("schema_version"),
                "generated_at": a.get("generated_at"),
                "source_asof": meta.get("source_asof"),
                "data_mode": meta.get("data_mode"),
                "created_by": meta.get("created_by"),
                "missing": sorted((a.get("errors") or {}).keys()),
            })
        if self.root.is_dir():
            p = self.root / "index.json"
            tmp = p.with_name("index.json.tmp")
            tmp.write_text(json.dumps({"schema_version": "1", "dates": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, p)
        return rows

    def _write_tmp(self, final: Path, payload: dict[str, Any]) -> Path:
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.with_name(final.name + ".tmp")
        text = _dumps(payload)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # 다시 읽어 검증한다 — 잘린 파일이 최종 이름으로 가지 않게
        back = json.loads(tmp.read_text(encoding="utf-8"))
        if back.get("snapshot_date") != final.name[:-5] or not back.get("schema_version"):
            tmp.unlink()
            raise ValueError("archive 검증 실패: snapshot_date · schema_version 이 맞지 않는다")
        return tmp
