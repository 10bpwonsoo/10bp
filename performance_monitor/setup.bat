@echo off
REM ===========================================================================
REM  MP Performance Monitor - 최초 설치 (Windows)
REM
REM  이 파일을 더블클릭하거나 cmd 에서 실행하면 끝까지 알아서 진행한다.
REM    1) Python 확인
REM    2) 가상환경(.venv) 생성
REM    3) 패키지 설치  - wheelhouse 폴더가 있으면 오프라인, 없으면 인터넷
REM    4) 테스트
REM    5) 데모 스냅샷 생성 (data/processed 가 비어 있을 때만)
REM    6) 대시보드 실행
REM
REM  두 번째부터는 run_dashboard.bat 만 실행하면 된다.
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul 2>nul

echo ============================================================
echo  MP Performance Monitor - 설치
echo  폴더: %CD%
echo ============================================================
echo.

REM --- 1) Python 찾기 --------------------------------------------------------
set "PY="
py -3.10 --version >nul 2>nul && set "PY=py -3.10"
if not defined PY ( py -3 --version >nul 2>nul && set "PY=py -3" )
if not defined PY ( python --version >nul 2>nul && set "PY=python" )

if not defined PY (
    echo [ERROR] Python 을 찾을 수 없습니다.
    echo.
    echo   Python 3.10 을 설치하십시오. 설치 시 "Add Python to PATH" 를 반드시 체크.
    echo   설치 후 이 파일을 다시 실행하십시오.
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo [1/6] Python 확인: %%v

REM --- 2) 가상환경 -----------------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo [2/6] 가상환경 이미 있음 - 건너뜀
) else (
    echo [2/6] 가상환경 생성 중... (.venv)
    %PY% -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo [ERROR] 가상환경 생성 실패.
        pause
        exit /b 1
    )
)
set "VPY=.venv\Scripts\python.exe"

REM --- 3) 패키지 설치 --------------------------------------------------------
%VPY% -c "import streamlit" >nul 2>nul
if %ERRORLEVEL%==0 (
    echo [3/6] 패키지 이미 설치됨 - 건너뜀
    goto :installed
)

if exist "wheelhouse\*.whl" (
    echo [3/6] 오프라인 설치 중... ^(wheelhouse 사용, 인터넷 불필요^)
    %VPY% -m pip install --quiet --upgrade pip --no-index --find-links=wheelhouse 2>nul
    %VPY% -m pip install --no-index --find-links=wheelhouse -r requirements.txt
) else (
    echo [3/6] wheelhouse 폴더가 없어 인터넷으로 설치합니다...
    echo       ^(폐쇄망이면 wheelhouse zip 4개를 이 폴더에 풀고 다시 실행하십시오^)
    %VPY% -m pip install --quiet --upgrade pip
    %VPY% -m pip install -r requirements.txt
)

if not %ERRORLEVEL%==0 (
    echo.
    echo [ERROR] 패키지 설치 실패 - wheel 이 이 Python 과 맞지 않을 가능성이 큽니다.
    for /f "delims=" %%v in ('%VPY% --version 2^^^>^^^&1') do echo   가상환경 Python : %%v
    for /f "delims=" %%t in ('%VPY% -c "import sys;print(f'cp{sys.version_info.major}{sys.version_info.minor}')"') do echo   필요한 태그     : %%t
    for /f "delims=" %%w in ('dir /b wheelhouse\*.whl 2^^^>nul') do (echo   wheelhouse 예시 : %%w & goto :showed)
    :showed
    echo.
    echo   wheel 파일명의 cp3XX 와 위 태그가 같아야 하고, win_amd64 여야 합니다.
    echo   폐쇄망이면 wheelhouse 폴더가 이 위치에 있는지도 확인하십시오.
    echo   자세한 내용: docs\OFFLINE_INSTALL.md
    pause
    exit /b 1
)
:installed

REM --- 4) 테스트 -------------------------------------------------------------
echo [4/6] 계산 로직 테스트 중...
%VPY% -m pytest tests -q
if not %ERRORLEVEL%==0 (
    echo.
    echo [WARN] 테스트에 실패한 항목이 있습니다. 위 내용을 확인하십시오.
    echo        그래도 화면은 띄울 수 있습니다.
    echo.
)

REM --- 5) 스냅샷 -------------------------------------------------------------
dir /b "data\processed\snapshot_*" >nul 2>nul
if %ERRORLEVEL%==0 (
    echo [5/6] 스냅샷 이미 있음 - 건너뜀
) else (
    echo [5/6] 스냅샷이 없어 데모^(합성^) 데이터를 만듭니다...
    echo       실제 데이터는 노트북에서 pm.export_snapshot^(globals^(^)^) 로 넣으십시오.
    %VPY% tools\make_demo_snapshot.py --weeks 10 --stocks 40
)

REM --- 6) 실행 ---------------------------------------------------------------
echo.
echo ============================================================
echo  [6/6] 대시보드를 시작합니다.
echo.
echo   브라우저에서  http://localhost:8501
echo   종료하려면 이 창에서 Ctrl+C
echo.
echo   다음부터는 run_dashboard.bat 만 실행하면 됩니다.
echo ============================================================
echo.

set STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
%VPY% -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --browser.gatherUsageStats false

endlocal
