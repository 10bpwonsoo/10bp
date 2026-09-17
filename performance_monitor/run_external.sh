#!/usr/bin/env bash
# 사외 서버에서 대시보드를 띄운다. 스냅샷 번들만 있으면 된다.
#   ./run_external.sh /srv/pm/data 8501
set -euo pipefail
cd "$(dirname "$0")"

DATA_DIR="${1:-}"
PORT="${2:-8501}"

if [ -z "$DATA_DIR" ]; then
    echo "사용법: $0 <데이터폴더> [포트]"
    echo "  예 : $0 /srv/pm/data 8501"
    echo "  데이터폴더 안에 processed/snapshot_YYYYMMDD 가 있어야 합니다."
    exit 1
fi
if [ ! -d "$DATA_DIR/processed" ]; then
    echo "오류: $DATA_DIR/processed 가 없습니다."
    echo "  번들을 먼저 푸십시오: unzip pm_bundle_*.zip -d <상위폴더>"
    exit 1
fi

PYTHON=".venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

echo "데이터 : $DATA_DIR"
echo "스냅샷 : $(ls -1 "$DATA_DIR/processed" | wc -l) 개"
echo "포트   : $PORT"
echo
echo "※ Streamlit 에는 로그인이 없습니다. 사외 공개 시 앞단에 인증을 두십시오."
echo "  (docs/EXTERNAL_HOSTING.md 4장)"
echo

PM_DATA_DIR="$DATA_DIR" exec "$PYTHON" -m streamlit run app.py \
    --server.port "$PORT" --server.address 0.0.0.0 \
    --server.headless true --browser.gatherUsageStats false
