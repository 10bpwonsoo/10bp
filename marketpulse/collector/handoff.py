"""
수집 결과 전달 — 수집기가 도는 곳(PC · 서버)과 분석이 도는 곳(Claude 세션)이 달라도 되게 한다 (2026-11-25).

전달 통로는 git 가지 하나다(기본 `collector-inputs`). 수집 폴더를 그 가지의 `inputs/<날짜>/` 로 올리고, 읽는 쪽은 그 가지를
받아 `marketpulse/data/inputs/<날짜>/` 로 푼다. 가지는 **항상 커밋 하나짜리**다(매번 새 뿌리 커밋으로 덮어쓴다) — 하루 2~3MB
입력이 저장소 이력에 쌓이지 않는다. 작업 가지 · 작업 폴더 · 스테이징은 건드리지 않는다(별도 index 파일을 쓴다).

키 · 토큰은 다루지 않는다. push 권한은 그 PC 의 git 설정(자격 증명 관리자 · SSH 키)이 가진 것을 그대로 쓴다.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BRANCH = "collector-inputs"
FILES = ("series_base.json", "series_universe.json", "series_basket.json", "news_rss.json", "collect_status.json", "input_status.json", "fetch_report.json")


def _git(args: list[str], *, repo: Path, env: dict | None = None, text_in: str | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=repo, env={**os.environ, **(env or {})}, input=text_in, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} 실패: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def make_commit(src: Path, day: str, *, repo: Path = REPO) -> str:
    """수집 폴더의 결과 파일만 담은 뿌리 커밋을 만든다(가지 · 작업 폴더는 그대로). 커밋 해시를 돌려준다."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        n = 0
        for name in FILES:
            f = src / name
            if not f.is_file():
                continue
            blob = _git(["hash-object", "-w", str(f)], repo=repo)
            _git(["update-index", "--add", "--cacheinfo", f"100644,{blob},inputs/{day}/{name}"], repo=repo, env=env)
            n += 1
        if n == 0:
            raise RuntimeError(f"{src} 에 올릴 수집 결과가 없다")
        tree = _git(["write-tree"], repo=repo, env=env)
    ident = {"GIT_AUTHOR_NAME": os.environ.get("GIT_AUTHOR_NAME") or "marketpulse-collector", "GIT_AUTHOR_EMAIL": os.environ.get("GIT_AUTHOR_EMAIL") or "collector@localhost",
             "GIT_COMMITTER_NAME": os.environ.get("GIT_COMMITTER_NAME") or "marketpulse-collector", "GIT_COMMITTER_EMAIL": os.environ.get("GIT_COMMITTER_EMAIL") or "collector@localhost"}
    return _git(["commit-tree", tree, "-m", f"inputs: {day}"], repo=repo, env=ident)


def publish(src: Path, day: str, *, branch: str = DEFAULT_BRANCH, remote: str = "origin", repo: Path = REPO) -> str:
    """수집 폴더를 remote 의 전달 가지로 올린다. 그 가지는 이 커밋 하나로 바뀐다(이력을 쌓지 않는다)."""
    commit = make_commit(src, day, repo=repo)
    _git(["push", "--force", remote, f"{commit}:refs/heads/{branch}"], repo=repo)
    return commit


def pull(day: str, dest: Path, *, branch: str = DEFAULT_BRANCH, remote: str = "origin", repo: Path = REPO) -> list[str]:
    """전달 가지에서 그 날짜 수집 결과를 dest 로 꺼낸다. 그 날짜가 없으면 빈 목록(다른 날짜 것을 대신 쓰지 않는다)."""
    try:
        _git(["fetch", "--quiet", remote, branch], repo=repo)
    except RuntimeError as exc:
        if "couldn't find remote ref" in str(exc):
            return []  # 전달 가지가 아직 없다 — 다른 기기에서 올린 적이 없는 것이다
        raise
    try:
        names = _git(["ls-tree", "--name-only", "FETCH_HEAD", f"inputs/{day}/"], repo=repo).splitlines()
    except RuntimeError:
        return []
    out: list[str] = []
    dest.mkdir(parents=True, exist_ok=True)
    for path in names:
        name = path.rsplit("/", 1)[-1]
        if name not in FILES:
            continue
        r = subprocess.run(["git", "show", f"FETCH_HEAD:{path}"], cwd=repo, capture_output=True)
        if r.returncode == 0:
            (dest / name).write_bytes(r.stdout)
            out.append(name)
    return out
