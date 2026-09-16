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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
            "- pyarrow 는 없어도 됩니다. 스냅샷이 pickle 로 자동 폴백합니다.\n"
            "  requirements.txt 에서 빼고 다시 시도해 보십시오.",
            file=sys.stderr,
        )
        return result.returncode

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
