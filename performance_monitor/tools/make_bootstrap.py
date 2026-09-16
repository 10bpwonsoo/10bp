"""붙여넣기로 설치하는 부트스트랩 셀을 만든다.

사내 노트북 서버에 **파일을 올릴 수 없을 때** 쓰는 경로다.
(업로드 버튼 없음 / zip 반입 차단 / 로컬 폴더 미연결 / GitHub 차단)

노트북 셀에 텍스트를 붙여넣는 것은 되므로, 프로젝트 전체를 base64 텍스트로
바꿔서 **셀에 붙여넣으면 스스로 풀리는 파이썬 코드**를 만든다.
표준 라이브러리만 쓰므로 노트북 서버에 아무것도 설치할 필요가 없다.

    python tools/make_bootstrap.py                  # 한 덩어리 (기본)
    python tools/make_bootstrap.py --max-bytes 40000  # 나눠서 (붙여넣기 실패 시)
    python tools/make_bootstrap.py --minimal        # 노트북 전용 (대시보드 서버 제외)

만들어진 `pm_bootstrap*.py` 를 메모장에서 열어 전체 복사 → 노트북 셀에 붙여넣고
실행하면 된다. 여러 개로 나온 경우 번호 순서대로 각각 실행한다(순서는 상관없다.
마지막 조각이 들어오면 그때 설치가 시작된다).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import sys
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 노트북에서 계산·리포트를 하는 데 필요한 최소 구성
MINIMAL = [
    "__init__.py",
    "src/*.py",
    "config/*.yaml",
    "notebooks/pm_engine.py",
    "tools/__init__.py",
    "tools/export_snapshot_from_notebook.py",
    "tools/compare_with_notebook.py",
    "tools/make_demo_snapshot.py",
    "tools/preflight.py",
    "requirements.txt",
]
# 같은 서버에서 Streamlit 대시보드까지 띄우려면 이것도 필요하다
DASHBOARD = ["app.py", "pages/*.py", ".streamlit_config_example.toml"]


def collect(minimal: bool) -> list[Path]:
    patterns = MINIMAL if minimal else MINIMAL + DASHBOARD
    files: list[Path] = []
    for pattern in patterns:
        if "*" in pattern:
            files.extend(sorted(ROOT.glob(pattern)))
        else:
            candidate = ROOT / pattern
            if candidate.exists():
                files.append(candidate)
    missing = [p for p in patterns if "*" not in p and not (ROOT / p).exists()]
    if missing:
        raise FileNotFoundError(f"빠진 파일: {missing}")
    return files


def build_payload(files: list[Path]) -> tuple[str, str, int]:
    """파일들을 zip → base64 문자열로. (base64, sha256, 원본바이트)"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            # zip 안의 경로는 프로젝트 루트 기준 (앞에 폴더명을 붙이지 않는다)
            archive.write(path, str(path.relative_to(ROOT)).replace("\\", "/"))
    raw = buffer.getvalue()
    return base64.b64encode(raw).decode("ascii"), hashlib.sha256(raw).hexdigest(), len(raw)


# 생성되는 셀의 본문. {} 자리를 채운다.
TEMPLATE = '''\
# ===========================================================================
#  MP Performance Monitor — 붙여넣기 설치  ({part}/{total})
# ---------------------------------------------------------------------------
#  이 셀 전체를 노트북에 붙여넣고 실행하십시오.
#  파일을 서버에 올릴 수 없는 환경을 위한 것으로, 외부 통신을 하지 않습니다.
#  data/ logs/ .venv/ 와 이미 있는 config/ 는 건드리지 않습니다.
#
#  설치 위치를 바꾸려면 아래 PM_TARGET 을 고치십시오.
#  (기본값 = 지금 노트북이 보고 있는 폴더 아래 performance_monitor)
# ===========================================================================
PM_TARGET = "performance_monitor"

_PART, _TOTAL, _SHA = {part}, {total}, "{sha}"
_DATA = (
{data}
)

# --- 아래는 고치지 마십시오 -------------------------------------------------
import base64, hashlib, io, os, shutil, tempfile, zipfile
from pathlib import Path

_PROTECTED = {{"data", "logs", ".venv", "venv", "wheelhouse", ".git", "__pycache__"}}
_KEEP_LOCAL = {{"config"}}
_stage = Path(".pm_bootstrap_parts")
_stage.mkdir(exist_ok=True)
(_stage / f"{{_PART:02d}}.b64").write_text(_DATA, encoding="ascii")

_have = sorted(p.stem for p in _stage.glob("*.b64"))
if len(_have) < _TOTAL:
    _left = [f"{{i:02d}}" for i in range(1, _TOTAL + 1) if f"{{i:02d}}" not in _have]
    print(f"조각 {{_PART}}/{{_TOTAL}} 저장됨. 남은 조각: {{', '.join(_left)}}")
    print("나머지 조각도 붙여넣고 실행하십시오.")
else:
    _blob = "".join((_stage / f"{{name}}.b64").read_text(encoding="ascii")
                    for name in _have)
    _raw = base64.b64decode(_blob)
    if hashlib.sha256(_raw).hexdigest() != _SHA:
        shutil.rmtree(_stage, ignore_errors=True)
        raise SystemExit("붙여넣기가 깨졌습니다. 조각을 다시 붙여넣으십시오 "
                         "(셀 전체를 빠짐없이 복사해야 합니다).")

    _target = Path(PM_TARGET).expanduser().resolve()
    _added, _changed, _review = [], [], []
    with tempfile.TemporaryDirectory() as _tmp:
        with zipfile.ZipFile(io.BytesIO(_raw)) as _zf:
            _zf.extractall(_tmp)
        for _item in sorted(Path(_tmp).rglob("*")):
            if not _item.is_file():
                continue
            _rel = _item.relative_to(_tmp)
            if _rel.parts[0] in _PROTECTED:
                continue
            _dest = _target / _rel
            _exists = _dest.exists()
            if _exists and _dest.read_bytes() == _item.read_bytes():
                continue
            if _exists and _rel.parts[0] in _KEEP_LOCAL:
                # 사내 설정(DB 주소·모델 목록)은 덮어쓰지 않는다
                shutil.copy2(_item, _dest.with_suffix(_dest.suffix + ".new"))
                _review.append(str(_rel))
                continue
            _dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_item, _dest)
            (_added if not _exists else _changed).append(str(_rel))
    for _name in ("data/processed", "data/raw", "data/archive", "data/reference", "logs"):
        (_target / _name).mkdir(parents=True, exist_ok=True)
    shutil.rmtree(_stage, ignore_errors=True)

    print(f"설치 위치: {{_target}}")
    print(f"  신규 {{len(_added)}}개 / 변경 {{len(_changed)}}개")
    if _review:
        print("  설정이 새 버전과 다릅니다. 덮어쓰지 않고 .new 로 두었습니다:")
        for _name in _review:
            print(f"   ! {{_name}}  ->  {{_name}}.new")
    if not _added and not _changed:
        print("  이미 최신입니다.")
    print()
    _nb = _target / "notebooks"
    print("다음 셀에서:")
    print(f"    import sys; sys.path.insert(0, r'{{_nb}}')")
    print("    import plotly.offline as po; po.init_notebook_mode(connected=False)")
    print("    import pm_engine as pm")
    print()
    print("  이미 pm_engine 을 import 한 뒤라면 커널을 재시작해야 반영됩니다.")
'''


def render(chunk: str, part: int, total: int, sha: str) -> str:
    lines = textwrap.wrap(chunk, 76)
    body = "\n".join(f'    "{line}"' for line in lines)
    return TEMPLATE.format(part=part, total=total, sha=sha, data=body)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "dist"),
                        help="결과를 둘 폴더 (기본: performance_monitor/dist)")
    parser.add_argument("--max-bytes", type=int, default=0,
                        help="조각 하나의 최대 base64 바이트. 0 이면 나누지 않는다.")
    parser.add_argument("--minimal", action="store_true",
                        help="노트북 전용 (Streamlit 대시보드 파일 제외)")
    args = parser.parse_args(argv)

    files = collect(args.minimal)
    encoded, sha, raw_size = build_payload(files)

    step = args.max_bytes if args.max_bytes > 0 else len(encoded)
    chunks = [encoded[i:i + step] for i in range(0, len(encoded), step)]
    total = len(chunks)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for index, chunk in enumerate(chunks, start=1):
        name = "pm_bootstrap.py" if total == 1 else f"pm_bootstrap_{index}of{total}.py"
        path = out_dir / name
        path.write_text(render(chunk, index, total, sha), encoding="utf-8")
        written.append(path)

    print(f"파일 {len(files)}개 → zip {raw_size/1024:.1f} KB "
          f"→ base64 {len(encoded)/1024:.1f} KB")
    print(f"sha256 {sha[:16]}…")
    for path in written:
        print(f"  {path}  ({path.stat().st_size/1024:.1f} KB)")
    print("\n메모장으로 열어 **전체 선택 → 복사** 후 노트북 셀에 붙여넣고 실행하십시오.")
    if total > 1:
        print("조각은 순서에 상관없이 각각 실행하면 되고, 마지막 조각에서 설치됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
