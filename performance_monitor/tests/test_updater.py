"""업데이트 도구 테스트.

핵심 계약은 하나다 — **운영 데이터를 건드리지 않는다.**
코드를 갱신하다 주간 성과 스냅샷이 날아가면 복구할 방법이 없으므로
보호 대상(data/ logs/ .venv/ wheelhouse/)과 사내 설정(config/)을
회귀 테스트로 고정해 둔다. 네트워크는 쓰지 않는다.
"""
from __future__ import annotations

import shutil
import zipfile

import pytest

from src import updater


def _make_release(root, version: str = "new"):
    """배포본(새 코드)을 흉내낸 폴더."""
    (root / "src").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (root / "app.py").write_text(f"# app {version}\n", encoding="utf-8")
    (root / "src" / "attribution.py").write_text(f"# attribution {version}\n", encoding="utf-8")
    (root / "src" / "brand_new.py").write_text("# 새 파일\n", encoding="utf-8")
    (root / "config" / "config.yaml").write_text(f"version: {version}\n", encoding="utf-8")
    return root


def _make_install(root):
    """사내에 설치된 기존 버전 + 운영 데이터."""
    _make_release(root, version="old")
    (root / "src" / "brand_new.py").unlink()          # 아직 없는 파일
    for name in ("data/processed", "logs", ".venv/Lib", "wheelhouse"):
        (root / name).mkdir(parents=True)
    (root / "data" / "processed" / "snap.parquet").write_bytes(b"SNAPSHOT")
    (root / "logs" / "run.log").write_text("log", encoding="utf-8")
    (root / ".venv" / "Lib" / "site.pth").write_text("venv", encoding="utf-8")
    (root / "wheelhouse" / "pandas.whl").write_bytes(b"wheel")
    # 운영자가 고친 설정 (DB 주소 등)
    (root / "config" / "config.yaml").write_text("version: old\nserver: 172.32.1.100\n",
                                                 encoding="utf-8")
    return root


@pytest.fixture
def install(tmp_path):
    return _make_install(tmp_path / "installed")


@pytest.fixture
def release(tmp_path):
    return _make_release(tmp_path / "release")


def _protected_snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).parts[0] in updater.PROTECTED}


# ---------------------------------------------------------------------------
# 보호 대상
# ---------------------------------------------------------------------------
def test_sync_never_touches_protected_directories(install, release):
    """data / logs / .venv / wheelhouse 는 한 바이트도 바뀌지 않는다."""
    # 배포본에도 같은 경로가 들어 있는 상황을 만든다 (가장 위험한 경우)
    (release / "data" / "processed").mkdir(parents=True)
    (release / "data" / "processed" / "snap.parquet").write_bytes(b"DEMO")
    (release / "logs").mkdir()
    (release / "logs" / "run.log").write_text("배포본 로그", encoding="utf-8")

    before = _protected_snapshot(install)
    updater._sync(release, install)
    assert _protected_snapshot(install) == before
    assert (install / "data" / "processed" / "snap.parquet").read_bytes() == b"SNAPSHOT"


def test_sync_reports_protected_dirs_present_in_install(install, release):
    result = updater._sync(release, install)
    assert set(result["protected"]) == {"data", "logs", ".venv", "wheelhouse"}


# ---------------------------------------------------------------------------
# 코드 갱신
# ---------------------------------------------------------------------------
def test_sync_updates_code_and_adds_new_files(install, release):
    result = updater._sync(release, install)
    assert (install / "src" / "attribution.py").read_text(encoding="utf-8") == "# attribution new\n"
    assert (install / "src" / "brand_new.py").exists()
    assert "src/brand_new.py" in result["added"]
    assert "src/attribution.py" in result["changed"]


def test_sync_is_idempotent(install, release):
    updater._sync(release, install)
    again = updater._sync(release, install)
    assert not again["added"] and not again["changed"]


def test_dry_run_writes_nothing(install, release):
    before = {str(p.relative_to(install)): p.read_bytes()
              for p in install.rglob("*") if p.is_file()}
    result = updater._sync(release, install, dry_run=True)
    after = {str(p.relative_to(install)): p.read_bytes()
             for p in install.rglob("*") if p.is_file()}
    assert after == before
    assert result["changed"], "바뀔 것이 있다고 보고는 해야 한다"


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
def test_local_config_is_not_overwritten(install, release):
    """사내에서 고친 설정은 덮어쓰지 않고 새 버전을 .new 로 둔다."""
    result = updater._sync(release, install)
    kept = (install / "config" / "config.yaml").read_text(encoding="utf-8")
    assert "172.32.1.100" in kept, "운영자가 고친 설정이 사라졌다"
    assert (install / "config" / "config.yaml.new").read_text(encoding="utf-8") == "version: new\n"
    assert result["review"] == ["config/config.yaml"]


def test_new_config_file_is_added(install, release):
    """설치본에 없는 설정 파일은 그냥 넣어 준다 (신규 기능용)."""
    (release / "config" / "optional.yaml").write_text("a: 1\n", encoding="utf-8")
    result = updater._sync(release, install)
    assert (install / "config" / "optional.yaml").exists()
    assert "config/optional.yaml" in result["added"]


def test_identical_config_is_left_alone(install, release):
    (install / "config" / "config.yaml").write_text("version: new\n", encoding="utf-8")
    result = updater._sync(release, install)
    assert not (install / "config" / "config.yaml.new").exists()
    assert result["review"] == []


# ---------------------------------------------------------------------------
# 반입 파일 경로 (폐쇄망)
# ---------------------------------------------------------------------------
def test_update_from_zip(tmp_path, install, release, monkeypatch):
    archive = tmp_path / "performance_monitor_win.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in release.rglob("*"):
            if path.is_file():
                zf.write(path, f"performance_monitor_win/{path.relative_to(release)}")

    monkeypatch.setattr(updater, "ROOT", install)
    before = _protected_snapshot(install)
    updater.update_from_file(archive)

    assert (install / "src" / "attribution.py").read_text(encoding="utf-8") == "# attribution new\n"
    assert _protected_snapshot(install) == before
    assert updater.current_version()["source"] == "file:performance_monitor_win.zip"


def test_update_from_folder(install, release, monkeypatch):
    monkeypatch.setattr(updater, "ROOT", install)
    updater.update_from_file(release)
    assert (install / "src" / "brand_new.py").exists()


def test_update_from_tar_gz(tmp_path, install, release, monkeypatch):
    archive = shutil.make_archive(str(tmp_path / "pm"), "gztar",
                                  root_dir=release.parent, base_dir=release.name)
    monkeypatch.setattr(updater, "ROOT", install)
    updater.update_from_file(archive)
    assert (install / "src" / "brand_new.py").exists()


def test_unknown_archive_format_is_rejected(tmp_path, install, monkeypatch):
    bogus = tmp_path / "pm.rar"
    bogus.write_bytes(b"x")
    monkeypatch.setattr(updater, "ROOT", install)
    with pytest.raises(ValueError, match="지원하지 않는 형식"):
        updater.update_from_file(bogus)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError):
        updater.update_from_file(tmp_path / "없는파일.zip")


def test_archive_without_project_is_rejected(tmp_path, install, monkeypatch):
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    monkeypatch.setattr(updater, "ROOT", install)
    with pytest.raises(FileNotFoundError, match="프로젝트를 찾지 못했"):
        updater.update_from_file(archive)


# ---------------------------------------------------------------------------
# 막힌 망에서의 안내
# ---------------------------------------------------------------------------
def test_update_without_network_explains_the_file_path(monkeypatch):
    """GitHub 이 막혀 있으면 조용히 실패하지 않고 대안을 알려 준다."""
    monkeypatch.setattr(updater, "check_github",
                        lambda **kwargs: {"reachable": False, "detail": "timed out"})
    with pytest.raises(RuntimeError) as excinfo:
        updater.update()
    message = str(excinfo.value)
    assert "timed out" in message
    assert "pm.update(" in message          # 반입 파일 경로 안내
    assert "HTTPS_PROXY" in message         # 프록시 시도 안내


def test_check_github_does_not_raise_when_blocked(monkeypatch):
    """사내망은 온갖 방식으로 막힌다. 어떤 예외든 결과 dict 로 돌려준다."""
    def boom(*args, **kwargs):
        raise OSError("[Errno 101] Network is unreachable")

    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    result = updater.check_github(verbose=False)
    assert result["reachable"] is False
    assert "Network is unreachable" in result["detail"]


def test_current_version_without_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "ROOT", tmp_path)
    assert updater.current_version()["source"] == "알 수 없음"
