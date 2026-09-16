#!/usr/bin/env bash
# MP Performance Monitor 실행 스크립트
#
#   ./run_dashboard.sh              # 로컬 http://localhost:8501
#   ./run_dashboard.sh server       # 사내 서버 http://<host>/performance
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PM_PORT:-8501}"

# 외부 telemetry 차단 (Streamlit 사용통계 수집 off)
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

python3 tools/preflight.py || exit 1

if [[ "${1:-local}" == "server" ]]; then
  exec python -m streamlit run app.py \
    --server.port "$PORT" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.baseUrlPath performance \
    --browser.gatherUsageStats false
else
  exec python -m streamlit run app.py \
    --server.port "$PORT" \
    --server.address 127.0.0.1 \
    --browser.gatherUsageStats false
fi
