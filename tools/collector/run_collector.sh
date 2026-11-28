#!/usr/bin/env bash
# Market Pulse 입력 수집 — cron · systemd 용. 인자 없이: 가격 + 기사, "news": 기사만.
# 종료 코드 0 = 다 받음, 75 = 일부 남음(나중에 다시 부르면 이어 받는다), 73 = 이미 도는 중.
# 키는 환경변수(FRED_API_KEY, TWELVEDATA_API_KEY)에서 읽는다 — 이 파일에 적지 않는다.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p logs
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
if [ "$1" = "news" ]; then
  "$PY" -m marketpulse.collector news >> logs/collector.log 2>&1
else
  "$PY" -m marketpulse.collector run --budget-min 25 >> logs/collector.log 2>&1
fi
CODE=$?
# 받은 데까지 넘겨준다(전달 가지 collector-inputs). 넘기지 않으려면 MARKETPULSE_NO_PUBLISH=1
if [ "$MARKETPULSE_NO_PUBLISH" != "1" ]; then
  "$PY" -c "from marketpulse.collector import handoff,engine;d=engine.kst_today().isoformat();print(handoff.publish(engine.inputs_root()/d,d)[:10])" >> logs/collector.log 2>&1
fi
exit $CODE
