"""실행 전 환경 점검.

setup / run 스크립트가 Streamlit 을 띄우기 **전에** 호출한다.
막히는 원인을 원시 traceback 대신 한국어로 알려주기 위한 것이다.

종료코드
    0  실행 가능 (경고는 있을 수 있음)
    1  실행 불가 — 사유와 조치를 출력함
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def is_unc(path) -> bool:
    """Windows UNC(네트워크) 경로인지. Streamlit 의 판정과 동일한 규칙."""
    return str(path).replace("/", "\\").startswith("\\\\")


def check_network_path() -> str | None:
    """네트워크 드라이브에서 실행 중인지.

    Streamlit 은 페이지 스크립트가 UNC 경로면 실행을 거부한다
    (SMB 자격증명 노출 방지를 위한 의도적 차단이며 우회 대상이 아니다).
    Windows 의 매핑 드라이브(M: 등)는 ``Path.resolve()`` 시 UNC 로 풀리므로
    똑같이 걸린다.
    """
    raw = str(ROOT)
    try:
        resolved = str(ROOT.resolve())
    except OSError:
        resolved = raw

    if not (is_unc(raw) or is_unc(resolved)):
        return None

    return (
        "네트워크 드라이브/공유 폴더에서는 실행할 수 없습니다.\n"
        f"    현재 위치 : {raw}\n"
        + (f"    실제 경로 : {resolved}\n" if resolved != raw else "")
        + "\n"
        "  Streamlit 이 네트워크 경로 실행을 막습니다(자격증명 노출 방지를 위한\n"
        "  의도적인 제한이라 우회할 수 없습니다).\n"
        "\n"
        "  조치 — 프로그램은 로컬 디스크로 옮기고, 데이터만 공유 폴더에 두십시오.\n"
        "\n"
        "    1) 이 폴더 전체를 로컬로 복사   예: C:\\apps\\performance_monitor\n"
        "    2) 거기서 setup.bat 실행\n"
        "    3) 스냅샷을 팀과 공유하려면 아래 중 하나로 데이터 위치만 지정\n"
        "\n"
        "       (a) 환경변수\n"
        '           set PM_DATA_DIR=M:/공유폴더/performance_monitor_data\n'
        "           run_dashboard.bat\n"
        "\n"
        "       (b) config\\config.yaml 의 project.data_dir 수정\n"
        "           data_dir: 'M:/공유폴더/performance_monitor_data'\n"
        "           ※ 역슬래시(\\) 대신 슬래시(/) 로 쓰는 편이 안전합니다.\n"
        "\n"
        "  데이터는 네트워크에 둬도 됩니다. 제한은 프로그램 위치에만 적용됩니다."
    )


def check_data_dir() -> tuple[str | None, str | None]:
    """스냅샷 위치와 존재 여부. (경고, 정보) 반환."""
    try:
        sys.path.insert(0, str(ROOT))
        from src.config import load_config

        processed = load_config().processed_dir
    except Exception as exc:  # noqa: BLE001 - 설정 오류도 여기서 알려준다
        return f"설정을 읽지 못했습니다: {exc}", None

    info = f"스냅샷 위치: {processed}"
    if not processed.exists():
        return ("스냅샷 폴더가 아직 없습니다. 데모 데이터를 만들거나 "
                "노트북에서 export_snapshot 을 실행하십시오.", info)
    found = sorted(p for p in processed.glob("snapshot_*") if p.is_dir())
    if not found:
        return ("스냅샷이 없습니다. 화면이 비어 보입니다.", info)
    return None, info + f"  (스냅샷 {len(found)}개, 최신 {found[-1].name})"


def check_path_length() -> str | None:
    """Windows 260자 제한."""
    if os.name != "nt":
        return None
    length = len(str(ROOT))
    if length > 150:
        return (f"경로가 깁니다({length}자). Windows 260자 제한에 걸릴 수 있으니 "
                "C:\\apps\\ 처럼 짧은 경로를 권합니다.")
    return None


def main() -> int:
    fatal = check_network_path()
    if fatal:
        print("\n[실행 불가] " + fatal + "\n", file=sys.stderr)
        return 1

    warnings = []
    for check in (check_path_length,):
        message = check()
        if message:
            warnings.append(message)

    data_warning, data_info = check_data_dir()
    if data_info:
        print(f"  {data_info}")
    if data_warning:
        warnings.append(data_warning)

    for message in warnings:
        print(f"  [주의] {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
