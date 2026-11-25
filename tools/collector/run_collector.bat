@echo off
rem Market Pulse 입력 수집 — Windows 작업 스케줄러용. 인자 없이: 가격 + 기사 수집, "news": 기사만.
rem 종료 코드 0 = 다 받음, 75 = 일부 남음(나중에 다시 부르면 이어 받는다), 73 = 이미 도는 중.
rem 키는 사용자 환경변수(FRED_API_KEY, TWELVEDATA_API_KEY)에서 읽는다 — 이 파일에 적지 않는다.
setlocal
cd /d "%~dp0..\.."
if not exist logs mkdir logs
set PY=.venv\Scripts\python.exe
if not exist %PY% set PY=python
set PYTHONUTF8=1
if /i "%~1"=="news" (
  %PY% -m marketpulse.collector news >> logs\collector.log 2>&1
) else (
  %PY% -m marketpulse.collector run --budget-min 25 >> logs\collector.log 2>&1
)
set CODE=%ERRORLEVEL%
rem 받은 데까지 넘겨준다(전달 가지 collector-inputs). 넘기지 않으려면 MARKETPULSE_NO_PUBLISH=1
if not "%MARKETPULSE_NO_PUBLISH%"=="1" %PY% -c "from datetime import datetime,timezone,timedelta;from pathlib import Path;from marketpulse.collector import handoff,engine;d=engine.kst_today().isoformat();print(handoff.publish(engine.inputs_root()/d,d)[:10])" >> logs\collector.log 2>&1
exit /b %CODE%
