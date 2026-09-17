"""노트북에서 코드 업데이트 받기.

    import pm_engine as pm

    pm.check_github()          # 사내망에서 GitHub 가 열리는지 먼저 확인
    pm.update()                # 열리면 GitHub, 막히면 로컬 파일 안내
    pm.update('C:/temp/performance_monitor_win.zip')   # 반입한 파일로

**중요** — 업데이트는 코드만 바꾼다. 아래는 절대 건드리지 않는다.

    data/      스냅샷 (주간 성과 데이터)
    logs/      실행 로그
    .venv/     가상환경
    wheelhouse/ 오프라인 설치용 wheel

`config/` 는 사내 설정(DB 주소·모델 목록)이 들어 있으므로 **덮어쓰지 않는다**.
새 버전에서 내용이 달라졌으면 옆에 `.new` 로 남기고 알려 준다. 직접 비교해서
필요한 줄만 옮기십시오.

지운 파일은 따라서 지우지 않는다 (덧씌우기만 한다). 완전히 깨끗한 설치가
필요하면 새 폴더에 압축을 풀고 `data/` 만 옮기십시오.

git 이 없어도 된다. GitHub 경로는 zip(zipball)을 내려받는 방식이다.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

__all__ = ["check_github", "update", "update_from_github", "update_from_file",
           "current_version", "DEFAULT_REPO", "DEFAULT_BRANCH"]

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPO = "10bpwonsoo/10bp"
DEFAULT_BRANCH = "claude/quant-performance-dashboard-ho1mc6"

# 업데이트가 건드리지 않는 것 (운영 데이터·환경)
PROTECTED = {"data", "logs", ".venv", "venv", "wheelhouse", ".git", "__pycache__"}
# 사용자가 고쳐 쓰는 것 — 덮어쓰지 않고 새 버전을 .new 로 남긴다
KEEP_LOCAL = {"config"}


# ---------------------------------------------------------------------------
# 연결 확인
# ---------------------------------------------------------------------------
def check_github(repo: str = DEFAULT_REPO, timeout: float = 6.0,
                 verbose: bool = True) -> dict:
    """사내망에서 GitHub 에 닿는지 확인한다.

    데스크톱에서 막혀 있어도 노트북 서버는 프록시로 열려 있는 경우가 있어
    한 번 확인해 볼 가치가 있다.
    """
    result = {"reachable": False, "detail": "", "proxy": None, "url": None}

    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
    result["proxy"] = proxy

    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{DEFAULT_BRANCH}"
    result["url"] = url
    request = urllib.request.Request(url, method="HEAD")
    request.add_header("User-Agent", "performance-monitor-updater")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result["reachable"] = True
            result["detail"] = f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            result["reachable"] = True   # 망은 열렸고 권한/경로 문제
            result["detail"] = (f"HTTP {exc.code} — 네트워크는 열려 있으나 "
                                "저장소가 비공개이거나 브랜치명이 다릅니다. "
                                "토큰이 필요하면 token= 인자를 쓰십시오.")
        else:
            result["detail"] = f"HTTP {exc.code} {exc.reason}"
    except Exception as exc:  # noqa: BLE001 - 사내망은 온갖 방식으로 막힌다
        result["detail"] = f"{type(exc).__name__}: {exc}"

    if verbose:
        if result["reachable"]:
            print(f"✓ GitHub 연결 가능 ({result['detail']})")
            if proxy:
                print(f"  프록시: {proxy}")
            print("  → pm.update() 로 바로 받을 수 있습니다.")
        else:
            print(f"✗ GitHub 에 닿지 않습니다 ({result['detail']})")
            if not proxy:
                print("  프록시 환경변수가 없습니다. 사내 프록시가 있다면:")
                print("      import os")
                print("      os.environ['HTTPS_PROXY'] = 'http://프록시주소:포트'")
                print("      pm.check_github()")
            print("  → 반입한 파일로 업데이트하십시오:")
            print("      pm.update(r'C:\\temp\\performance_monitor_win.zip')")
    return result


# ---------------------------------------------------------------------------
# 버전
# ---------------------------------------------------------------------------
def current_version() -> dict:
    """설치된 코드의 버전 정보 (.pm_version.json)."""
    marker = ROOT / ".pm_version.json"
    if marker.exists():
        try:
            return json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"installed_at": "알 수 없음", "source": "알 수 없음"}


def _write_version(info: dict) -> None:
    info = dict(info)
    info["installed_at"] = datetime.now().isoformat(timespec="seconds")
    (ROOT / ".pm_version.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 적용
# ---------------------------------------------------------------------------
def _find_project_root(extracted: Path) -> Path:
    """압축 안에서 프로젝트 루트(app.py 가 있는 폴더)를 찾는다."""
    if (extracted / "app.py").exists():
        return extracted
    for candidate in sorted(extracted.rglob("app.py")):
        if (candidate.parent / "src").is_dir() and (candidate.parent / "config").is_dir():
            return candidate.parent
    raise FileNotFoundError(
        "압축 안에서 프로젝트를 찾지 못했습니다 (app.py + src/ + config/).")


def _sync(source: Path, target: Path, dry_run: bool = False) -> dict:
    """코드만 덮어쓴다. 데이터·로그·가상환경·설정은 건드리지 않는다."""
    changed, added, review = [], [], []

    for item in sorted(source.rglob("*")):
        rel = item.relative_to(source)
        if rel.parts[0] in PROTECTED or not item.is_file():
            continue

        destination = target / rel
        exists = destination.exists()
        if exists and destination.read_bytes() == item.read_bytes():
            continue

        # 설정은 사내에서 고쳐 쓰므로 덮어쓰지 않는다. 새 버전만 옆에 둔다.
        if exists and rel.parts[0] in KEEP_LOCAL:
            new_file = destination.with_suffix(destination.suffix + ".new")
            if not dry_run:
                shutil.copy2(item, new_file)
            review.append(str(rel))
            continue

        (added if not exists else changed).append(str(rel))
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)

    # 실제로 지켜 준 것 = 설치본에 존재하는 보호 폴더
    protected = sorted(name for name in PROTECTED
                       if name not in {".git", "__pycache__"}
                       and (target / name).exists())

    return {"added": added, "changed": changed, "review": review,
            "protected": protected}


def _report(result: dict, dry_run: bool) -> None:
    prefix = "[확인만]" if dry_run else "[적용]"
    print(f"\n{prefix} 신규 {len(result['added'])}개 / 변경 {len(result['changed'])}개")
    for name in result["added"][:15]:
        print(f"   + {name}")
    for name in result["changed"][:15]:
        print(f"   ~ {name}")
    total = len(result["added"]) + len(result["changed"])
    if total > 30:
        print(f"   ... 외 {total - 30}건")
    if not total:
        print("   이미 최신입니다.")

    if result["review"]:
        print("\n  설정이 새 버전과 다릅니다. 덮어쓰지 않고 .new 로 두었으니")
        print("  직접 비교해서 필요한 줄만 옮기십시오:")
        for name in result["review"]:
            print(f"   ! {name}  ->  {name}.new")

    print(f"\n  건드리지 않은 것: {', '.join(result['protected']) or '(없음)'}")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
def update_from_github(repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH,
                       token: str | None = None, dry_run: bool = False,
                       timeout: float = 60.0) -> dict:
    """GitHub 에서 zip 을 내려받아 코드를 갱신한다. git 이 없어도 된다."""
    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
    request = urllib.request.Request(url)
    request.add_header("User-Agent", "performance-monitor-updater")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    print(f"내려받는 중: {repo} @ {branch}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise RuntimeError(
                f"HTTP {exc.code} — 저장소가 비공개이거나 브랜치명이 다릅니다.\n"
                "  비공개면 개인 액세스 토큰이 필요합니다:\n"
                "      pm.update_from_github(token='ghp_...')\n"
                "  브랜치가 합쳐져 사라졌다면 기본 브랜치를 지정하십시오:\n"
                "      pm.update_from_github(branch='main')"
            ) from exc
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"GitHub 에 닿지 않습니다: {type(exc).__name__}: {exc}\n"
            "  사내망에서 막혀 있을 수 있습니다. pm.check_github() 로 확인하고,\n"
            "  막혀 있으면 반입한 파일로 업데이트하십시오:\n"
            "      pm.update(r'C:\\temp\\performance_monitor_win.zip')"
        ) from exc

    print(f"  {len(payload)/1024/1024:.1f} MB 받음")
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            archive.extractall(tmp)
        source = _find_project_root(Path(tmp))
        result = _sync(source, ROOT, dry_run)

    _report(result, dry_run)
    if not dry_run:
        _write_version({"source": f"github:{repo}@{branch}"})
        print("\n  ⚠ 노트북 커널을 재시작해야 바뀐 코드가 반영됩니다.")
    return result


def update_from_file(path: str | Path, dry_run: bool = False) -> dict:
    """반입한 파일로 갱신한다. ``.zip`` / ``.tar.gz`` / 폴더를 받는다."""
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {source_path}")

    print(f"읽는 중: {source_path}")
    with tempfile.TemporaryDirectory() as tmp:
        if source_path.is_dir():
            source = _find_project_root(source_path)
            result = _sync(source, ROOT, dry_run)
        else:
            if source_path.suffix == ".zip":
                with zipfile.ZipFile(source_path) as archive:
                    archive.extractall(tmp)
            elif "".join(source_path.suffixes[-2:]) in (".tar.gz", ".tgz"):
                import tarfile

                with tarfile.open(source_path) as archive:
                    archive.extractall(tmp)
            else:
                raise ValueError(
                    f"지원하지 않는 형식입니다: {source_path.suffix}\n"
                    "  .zip / .tar.gz / 폴더 를 지정하십시오.")
            source = _find_project_root(Path(tmp))
            result = _sync(source, ROOT, dry_run)

    _report(result, dry_run)
    if not dry_run:
        _write_version({"source": f"file:{source_path.name}"})
        print("\n  ⚠ 노트북 커널을 재시작해야 바뀐 코드가 반영됩니다.")
    return result


def update(source: str | Path | None = None, dry_run: bool = False, **kwargs) -> dict:
    """코드 업데이트.

        pm.update()                       # GitHub (막혀 있으면 안내)
        pm.update('C:/temp/pm.zip')       # 반입한 파일
        pm.update(dry_run=True)           # 무엇이 바뀌는지만 확인

    데이터(`data/`)·로그·가상환경은 건드리지 않는다.
    """
    if source is not None:
        return update_from_file(source, dry_run=dry_run)

    status = check_github(verbose=False)
    if not status["reachable"]:
        raise RuntimeError(
            f"GitHub 에 닿지 않습니다 ({status['detail']}).\n"
            "  사내망에서 막혀 있는 것으로 보입니다. 반입한 파일을 쓰십시오:\n"
            "      pm.update(r'C:\\temp\\performance_monitor_win.zip')\n\n"
            "  사내 프록시가 있다면 먼저 설정해 보십시오:\n"
            "      import os; os.environ['HTTPS_PROXY'] = 'http://프록시:포트'\n"
            "      pm.check_github()"
        )
    return update_from_github(dry_run=dry_run, **kwargs)
