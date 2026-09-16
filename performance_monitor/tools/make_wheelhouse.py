"""폐쇄망 반입용 wheelhouse 생성.

**인터넷이 되는 PC에서** 실행해 `wheelhouse/` 를 만들고, 그 디렉터리를 사내망으로
반입한 뒤 아래처럼 설치한다.

    pip install --no-index --find-links=wheelhouse -r requirements.txt

`--no-index` 가 있어야 pip 가 인터넷을 아예 보지 않는다.

wheel 은 **OS · CPU · Python 버전마다 다르다.** 기본값은 현재 실행 환경 기준이며,
사내 서버 환경이 다르면 `--platform` / `--python-version` 으로 지정한다.

    python tools/make_wheelhouse.py
    python tools/make_wheelhouse.py --platform manylinux2014_x86_64 --python-version 39
    python tools/make_wheelhouse.py --platform win_amd64 --python-version 310

자세한 절차는 docs/OFFLINE_INSTALL.md 참조.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent


def _target_environment(python_version: str | None, platform: str | None) -> dict:
    """마커 평가용 환경. 지정이 없으면 현재 인터프리터 기준."""
    if python_version:
        major, minor = python_version[0], python_version[1:]
        version = f"{major}.{minor}"
    else:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
    system = "Windows" if (platform or "").startswith("win") else (
        "Darwin" if "macos" in (platform or "") else "Linux")
    return {
        "python_version": version,
        "python_full_version": version + ".0",
        "sys_platform": {"Windows": "win32", "Darwin": "darwin"}.get(system, "linux"),
        "platform_system": system,
        "os_name": "nt" if system == "Windows" else "posix",
        "implementation_name": "cpython",
        "platform_machine": "AMD64" if system == "Windows" else "x86_64",
        "extra": "",
    }


def _installed_names(target: Path) -> set:
    names = set()
    for whl in target.glob("*.whl"):
        names.add(canonicalize_name(whl.name.split("-")[0]))
    return names


def _missing_requirements(target: Path, env: dict) -> list:
    """받아둔 wheel 들의 METADATA 를 읽어, 대상 환경에서 필요한데 없는 것을 찾는다.

    ``pip download --python-version`` 은 ``python_version < "3.11"`` 같은
    조건부 의존성(exceptiongroup, tomli ...)을 놓치는 경우가 있다.
    실제로 대상 서버에서 설치할 때 그 지점에서 실패하므로 여기서 메꾼다.
    """
    have = _installed_names(target)
    missing = {}
    for whl in sorted(target.glob("*.whl")):
        try:
            with zipfile.ZipFile(whl) as zf:
                meta_name = next(n for n in zf.namelist()
                                 if n.endswith(".dist-info/METADATA"))
                metadata = zf.read(meta_name).decode("utf-8", "replace")
        except (StopIteration, zipfile.BadZipFile, KeyError):
            continue
        for line in metadata.splitlines():
            if not line.startswith("Requires-Dist:"):
                continue
            try:
                req = Requirement(line.split(":", 1)[1].strip())
            except Exception:  # noqa: BLE001 - 메타데이터 파싱 실패는 건너뛴다
                continue
            if req.marker is not None and not req.marker.evaluate(env):
                continue
            if canonicalize_name(req.name) not in have:
                missing[canonicalize_name(req.name)] = str(req).split(";")[0].strip()
    return sorted(missing.values())


def main(args) -> int:
    requirements = ROOT / args.requirements
    if not requirements.exists():
        print(f"requirements 파일을 찾을 수 없습니다: {requirements}", file=sys.stderr)
        return 2

    target = Path(args.output)
    if not target.is_absolute():
        target = ROOT / target
    target.mkdir(parents=True, exist_ok=True)

    command = [sys.executable, "-m", "pip", "download",
               "-r", str(requirements), "-d", str(target)]

    cross = bool(args.platform or args.python_version or args.implementation)
    if cross:
        # 다른 환경용으로 받을 때 pip 는 소스 빌드를 할 수 없으므로
        # 반드시 바이너리 wheel 만 받아야 한다.
        command += ["--only-binary=:all:"]
        if args.platform:
            command += ["--platform", args.platform]
        if args.python_version:
            command += ["--python-version", args.python_version]
        if args.implementation:
            command += ["--implementation", args.implementation]
        if args.abi:
            command += ["--abi", args.abi]

    print("실행:", " ".join(command), "\n")
    result = subprocess.run(command)
    if result.returncode != 0:
        print(
            "\nwheel 내려받기에 실패했습니다.\n"
            "- 특정 패키지에 대상 환경용 wheel 이 없을 수 있습니다 "
            "(그 경우 사내 서버와 동일한 OS/Python 에서 다시 실행하십시오)\n"
            "- pyarrow 는 wheel 이 가장 크지만 streamlit 의 필수 의존성이라 뺄 수 없습니다.",
            file=sys.stderr,
        )
        return result.returncode

    # --- 조건부 의존성 보강 ------------------------------------------------
    env = _target_environment(args.python_version, args.platform)
    for attempt in range(5):
        missing = _missing_requirements(target, env)
        if not missing:
            break
        print(f"\n[보강 {attempt + 1}] 대상 환경(python {env['python_version']}, "
              f"{env['platform_system']})에서 필요한데 빠진 패키지: {', '.join(missing)}")
        extra = list(command) + missing
        # -r requirements.txt 는 이미 처리했으므로 제거하고 개별 패키지만 받는다
        for flag in ("-r", str(requirements)):
            if flag in extra:
                extra.remove(flag)
        if subprocess.run(extra).returncode != 0:
            print("[WARN] 보강 다운로드 실패 - 대상 서버에서 설치가 막힐 수 있습니다.",
                  file=sys.stderr)
            break
    else:
        print("[WARN] 의존성이 5회 안에 닫히지 않았습니다.", file=sys.stderr)

    files = sorted(target.glob("*"))
    total = sum(f.stat().st_size for f in files) / 1048576
    print(f"\n완료: {len(files)}개 파일 / {total:.1f} MB → {target}")
    print("\n사내망에서:")
    print(f"    pip install --no-index --find-links={target.name} -r requirements.txt")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="wheelhouse", help="출력 디렉터리")
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument("--platform",
                        help="대상 플랫폼 (예: manylinux2014_x86_64, win_amd64, macosx_11_0_arm64)")
    parser.add_argument("--python-version", help="대상 Python 버전 (예: 39, 310, 311)")
    parser.add_argument("--implementation", help="예: cp")
    parser.add_argument("--abi", help="예: cp311")
    sys.exit(main(parser.parse_args()))
