#!/usr/bin/env bash
# ===========================================================================
#  MP Performance Monitor - 최초 설치 (macOS / Linux)
#
#    chmod +x setup.sh && ./setup.sh
#
#    1) Python 확인  2) 가상환경(.venv)  3) 패키지 설치
#    4) 테스트  5) 데모 스냅샷 (없을 때만)  6) 대시보드 실행
#
#  두 번째부터는 ./run_dashboard.sh 만 실행하면 된다.
# ===========================================================================
set -uo pipefail
cd "$(dirname "$0")"

echo "============================================================"
echo " MP Performance Monitor - 설치"
echo " 폴더: $PWD"
echo "============================================================"
echo

# --- 1) Python -------------------------------------------------------------
PY=""
for candidate in python3.10 python3.11 python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [[ -z "$PY" ]]; then
  echo "[ERROR] Python 을 찾을 수 없습니다. Python 3.10 이상을 설치하십시오."
  exit 1
fi
echo "[1/6] Python 확인: $($PY --version 2>&1)"

# --- 2) 가상환경 -----------------------------------------------------------
if [[ -x ".venv/bin/python" ]]; then
  echo "[2/6] 가상환경 이미 있음 - 건너뜀"
else
  echo "[2/6] 가상환경 생성 중... (.venv)"
  "$PY" -m venv .venv || { echo "[ERROR] 가상환경 생성 실패"; exit 1; }
fi
VPY=".venv/bin/python"

# --- 3) 패키지 -------------------------------------------------------------
if "$VPY" -c "import streamlit" >/dev/null 2>&1; then
  echo "[3/6] 패키지 이미 설치됨 - 건너뜀"
elif compgen -G "wheelhouse/*.whl" >/dev/null; then
  echo "[3/6] 오프라인 설치 중... (wheelhouse 사용, 인터넷 불필요)"
  if ! "$VPY" -m pip install -q --no-index --find-links=wheelhouse -r requirements.txt; then
    echo
    echo "[ERROR] 오프라인 설치 실패 - wheel 이 이 Python 과 맞지 않을 가능성이 큽니다."
    echo "  가상환경 Python : $("$VPY" --version 2>&1)  (태그 $("$VPY" -c 'import sys;print(f"cp{sys.version_info.major}{sys.version_info.minor}")'))"
    echo "  wheelhouse 예시 : $(ls wheelhouse/*.whl 2>/dev/null | head -1 | xargs -r basename)"
    echo
    echo "  wheel 파일명의 cp3XX 와 위 태그가 같아야 합니다."
    echo "  다르면 사내 서버와 같은 Python 버전에서 wheelhouse 를 다시 만드십시오:"
    echo "      python tools/make_wheelhouse.py --platform win_amd64 --python-version 310"
    echo "  자세한 내용: docs/OFFLINE_INSTALL.md"
    exit 1
  fi
else
  echo "[3/6] wheelhouse 폴더가 없어 인터넷으로 설치합니다..."
  echo "      (폐쇄망이면 wheelhouse 를 이 폴더에 두고 다시 실행하십시오)"
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -r requirements.txt \
    || { echo "[ERROR] 설치 실패"; exit 1; }
fi

# --- 4) 테스트 -------------------------------------------------------------
echo "[4/6] 계산 로직 테스트 중..."
"$VPY" -m pytest tests -q || echo "[WARN] 실패한 테스트가 있습니다. 위 내용을 확인하십시오."

# --- 5) 스냅샷 -------------------------------------------------------------
if compgen -G "data/processed/snapshot_*" >/dev/null; then
  echo "[5/6] 스냅샷 이미 있음 - 건너뜀"
else
  echo "[5/6] 스냅샷이 없어 데모(합성) 데이터를 만듭니다..."
  echo "      실제 데이터는 노트북에서 pm.export_snapshot(globals()) 로 넣으십시오."
  "$VPY" tools/make_demo_snapshot.py --weeks 10 --stocks 40
fi

# --- 6) 실행 ---------------------------------------------------------------
"$VPY" tools/preflight.py || exit 1

cat <<'BANNER'

============================================================
 [6/6] 대시보드를 시작합니다.

  브라우저에서  http://localhost:8501
  종료하려면 이 창에서 Ctrl+C

  다음부터는 ./run_dashboard.sh 만 실행하면 됩니다.
============================================================

BANNER

export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
exec "$VPY" -m streamlit run app.py \
  --server.port "${PM_PORT:-8501}" \
  --server.address 127.0.0.1 \
  --browser.gatherUsageStats false
