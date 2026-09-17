"""붙여넣기용 셀 — pm_engine 경로를 찾아서 sys.path 에 넣는다.

설치 경로를 손으로 적다가 틀리는 것을 막기 위한 것이다. 특히 압축을 두 번
풀어 `performance_monitor/performance_monitor/...` 처럼 중첩된 경우,
상대 경로로 적으면 노트북의 현재 폴더 기준이라 맞지 않는다.

이 파일 내용을 노트북 셀에 그대로 붙여넣고 실행하면 된다.
(파일로 옮길 수 없는 환경을 전제하므로 import 가 아니라 붙여넣기용이다.)
"""
# --- pm_engine 경로 자동 찾기 -------------------------------------------------
import sys
from pathlib import Path

_SKIP = {".git", "__pycache__", ".ipynb_checkpoints", "node_modules",
         "site-packages", ".venv", "venv", ".cache", ".local"}

def _find(base, depth=6):
    """base 아래에서 notebooks/pm_engine.py 를 찾는다 (깊이 제한)."""
    hits, queue = [], [(Path(base), 0)]
    while queue:
        folder, level = queue.pop(0)
        try:
            entries = list(folder.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_dir():
                if level < depth and entry.name not in _SKIP:
                    queue.append((entry, level + 1))
            elif entry.name == "pm_engine.py":
                hits.append(entry.parent)
    return hits

found = _find(Path.cwd()) or _find(Path.home())

if not found:
    print("pm_engine.py 를 못 찾았습니다.")
    print("현재 폴더:", Path.cwd())
    print("여기 있는 것:", sorted(p.name for p in Path.cwd().iterdir())[:30])
else:
    target = str(found[0].resolve())
    if len(found) > 1:
        print(f"후보가 {len(found)}개입니다. 첫 번째를 씁니다:")
        for p in found:
            print("   ", p.resolve())
    sys.path.insert(0, target)
    import pm_engine as pm
    print("OK  ", pm.__file__)
    print("경로  sys.path.insert(0, r'%s')" % target)
