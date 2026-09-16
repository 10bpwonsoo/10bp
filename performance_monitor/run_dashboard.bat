@echo off
REM ===========================================================================
REM  MP Performance Monitor - Windows 실행 스크립트
REM
REM    run_dashboard.bat              로컬   http://localhost:8501
REM    run_dashboard.bat server       사내서버 http://<서버>/performance
REM
REM  가상환경(.venv)이 있으면 자동으로 사용한다.
REM  포트를 바꾸려면:  set PM_PORT=9000 && run_dashboard.bat
REM ===========================================================================
setlocal

cd /d "%~dp0"

REM --- 외부 telemetry 차단 (Streamlit 사용통계 수집 off) ---------------------
set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

if "%PM_PORT%"=="" set PM_PORT=8501

REM --- Python 찾기 -----------------------------------------------------------
REM 1) 프로젝트 가상환경  2) py 런처  3) PATH 의 python
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
    echo [INFO] 가상환경 사용: .venv
) else (
    where py >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY=py -3.10"
    ) else (
        where python >nul 2>nul
        if %ERRORLEVEL%==0 (
            set "PY=python"
        ) else (
            echo [ERROR] Python 을 찾을 수 없습니다.
            echo         Python 3.10 을 설치하거나 .venv 가상환경을 만드십시오:
            echo            py -3.10 -m venv .venv
            echo            .venv\Scripts\pip install --no-index --find-links=wheelhouse -r requirements.txt
            exit /b 1
        )
    )
)

REM --- 설치 확인 -------------------------------------------------------------
%PY% -c "import streamlit" >nul 2>nul
if not %ERRORLEVEL%==0 (
    echo [ERROR] streamlit 이 설치되어 있지 않습니다.
    echo         pip install --no-index --find-links=wheelhouse -r requirements.txt
    exit /b 1
)

REM --- 스냅샷 확인 -----------------------------------------------------------
dir /b "data\processed\snapshot_*" >nul 2>nul
if not %ERRORLEVEL%==0 (
    echo [WARN] data\processed 에 스냅샷이 없습니다. 화면이 비어 보입니다.
    echo        점검용 합성 데이터를 만들려면:
    echo            %PY% tools\make_demo_snapshot.py
    echo.
)

REM --- 실행 ------------------------------------------------------------------
if /i "%~1"=="server" (
    echo [INFO] 사내 서버 모드 - 포트 %PM_PORT% / 경로 /performance
    echo [INFO] 방화벽에서 %PM_PORT% 포트가 열려 있어야 합니다.
    %PY% -m streamlit run app.py ^
        --server.port %PM_PORT% ^
        --server.address 0.0.0.0 ^
        --server.headless true ^
        --server.baseUrlPath performance ^
        --browser.gatherUsageStats false
) else (
    echo [INFO] 로컬 모드 - http://localhost:%PM_PORT%
    %PY% -m streamlit run app.py ^
        --server.port %PM_PORT% ^
        --server.address 127.0.0.1 ^
        --browser.gatherUsageStats false
)

endlocal
