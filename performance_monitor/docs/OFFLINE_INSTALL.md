# 폐쇄망(사내망) 설치 가이드

사내망에서 **GitHub 와 PyPI 가 모두 차단**된 상태를 전제로 한다.
완성된 시스템은 원래 인터넷이 필요 없다 — 반입만 하면 된다.

반입해야 할 것은 두 가지다.

| # | 내용 | 없으면 |
|---|---|---|
| 1 | **소스 코드** | 실행 자체가 불가 |
| 2 | **Python 패키지** (streamlit, plotly, pandas …) | `pip install` 실패 |

---

## 1. 소스 코드 반입

### 방법 A — 사내 Git 서버가 있는 경우 (권장)

사내 GitLab / Bitbucket / Gitea 가 있으면 거기로 미러링한다. 이후 `git pull` 로 계속 받을 수 있다.

**인터넷 되는 PC에서**
```bash
git clone --mirror https://github.com/10bpwonsoo/10bp.git
tar czf 10bp-mirror.tar.gz 10bp.git
# → 10bp-mirror.tar.gz 를 사내로 반입
```

**사내망에서**
```bash
tar xzf 10bp-mirror.tar.gz
cd 10bp.git
git remote set-url --push origin https://git.사내도메인/quant/10bp.git
git push --mirror
```

### 방법 B — git bundle 파일 하나로 반입

히스토리가 보존되고, 이후 갱신분도 bundle 로만 주고받을 수 있다. **파일 1개**면 된다.

**인터넷 되는 PC에서**
```bash
git clone https://github.com/10bpwonsoo/10bp.git
cd 10bp
git bundle create 10bp_dashboard.bundle claude/quant-performance-dashboard-ho1mc6
```

**사내망에서**
```bash
git clone --branch claude/quant-performance-dashboard-ho1mc6 \
    10bp_dashboard.bundle 10bp
cd 10bp/performance_monitor
```

다음 주 갱신분만 받을 때는 변경분만 담은 bundle 을 만들면 훨씬 작다.
```bash
# 인터넷 PC: 사내가 가진 마지막 커밋 이후만
git bundle create update.bundle <사내_마지막_커밋>..claude/quant-performance-dashboard-ho1mc6
# 사내: 받아서 적용
git pull update.bundle claude/quant-performance-dashboard-ho1mc6
```

### 방법 C — 압축파일 반입 (가장 단순)

Git 이 아예 없어도 된다. 압축을 풀면 끝이다.

```bash
tar xzf performance_monitor_code.tar.gz
cd performance_monitor
```

단, 히스토리가 없어 다음 갱신 때 덮어쓰기가 된다.
`config/` 를 직접 수정했다면 덮어쓰기 전에 백업해 둘 것.

---

## 2. Python 패키지 반입

### 먼저 확인할 것 — 사내 PyPI 미러

많은 금융사가 Nexus / Artifactory 로 사내 PyPI 미러를 운영한다. 있으면 이게 가장 쉽다.

```bash
pip install -r requirements.txt -i https://pypi.사내도메인/simple --trusted-host pypi.사내도메인
```

`~/.pip/pip.conf` (Windows: `%APPDATA%\pip\pip.ini`) 에 넣어두면 매번 안 써도 된다.
```ini
[global]
index-url = https://pypi.사내도메인/simple
trusted-host = pypi.사내도메인
```

### 미러가 없으면 — wheelhouse 반입

**중요**: wheel 은 OS·CPU·Python 버전에 따라 다르다.
**반드시 사내 서버와 같은 환경**에서 내려받아야 한다.
(사내가 Linux x86_64 + Python 3.11 이면, 내려받는 PC도 그 조건이어야 한다)

**인터넷 되는 PC에서**
```bash
cd performance_monitor
python tools/make_wheelhouse.py          # → wheelhouse/ 생성
tar czf wheelhouse.tar.gz wheelhouse
# → wheelhouse.tar.gz 반입 (보통 200~400MB)
```

환경이 다르면 대상 환경을 명시한다.
```bash
# 예: 사내가 Linux x86_64 / Python 3.9 인데 내려받는 PC 는 다른 환경일 때
python tools/make_wheelhouse.py --platform manylinux2014_x86_64 --python-version 39
# 예: 사내가 Windows 64bit / Python 3.10
python tools/make_wheelhouse.py --platform win_amd64 --python-version 310
```

**사내망에서**
```bash
tar xzf wheelhouse.tar.gz
pip install --no-index --find-links=wheelhouse -r requirements.txt
```

`--no-index` 가 핵심이다. 이게 있어야 pip 가 인터넷을 아예 보지 않는다.

---

## 2-1. Windows Server + Python 3.10 (현재 대상 환경)

사내 서버가 **Windows Server / Python 3.10 (64bit)** 인 경우의 구체 절차다.

### 반입물

| 파일 | 내용 |
|---|---|
| `performance_monitor_code.tar.gz` (또는 `.zip`) | 소스 |
| `wheelhouse_win_amd64_py310.zip` | 패키지 46개 (94MB) |

wheel 이 `win_amd64` / `cp310` 으로 맞춰져 있어야 한다. 직접 만들려면 **인터넷 되는 PC**에서:

```bash
python tools/make_wheelhouse.py --platform win_amd64 --python-version 310
```

### 설치 (Windows 서버에서, cmd)

```bat
REM 1) 압축 해제 후 프로젝트 폴더로
cd C:\apps\performance_monitor

REM 2) Python 3.10 확인
py -3.10 --version

REM 3) 가상환경 생성 (시스템 Python 오염 방지)
py -3.10 -m venv .venv

REM 4) 인터넷 없이 설치
.venv\Scripts\pip install --no-index --find-links=wheelhouse -r requirements.txt

REM 5) 확인
.venv\Scripts\python -m pytest tests\ -q
.venv\Scripts\python tools\make_demo_snapshot.py --weeks 6 --stocks 30

REM 6) 실행
run_dashboard.bat
```

`run_dashboard.bat` 은 `.venv` 가 있으면 자동으로 쓴다.

### 사내 서버로 공개

```bat
run_dashboard.bat server
REM → http://<서버주소>/performance
```

방화벽에서 포트를 열어야 한다 (관리자 권한 cmd).

```bat
netsh advfirewall firewall add rule name="MP Performance Monitor" ^
    dir=in action=allow protocol=TCP localport=8501
```

포트를 바꾸려면 `set PM_PORT=9000` 후 실행.

### 서버 부팅 시 자동 실행

추가 설치 없이 **작업 스케줄러**로 등록하는 방법 (관리자 cmd):

```bat
schtasks /create /tn "MP Performance Monitor" ^
    /tr "C:\apps\performance_monitor\run_dashboard.bat server" ^
    /sc onstart /ru SYSTEM /rl HIGHEST /f
```

NSSM 등 서비스 래퍼를 쓸 수 있으면 그쪽이 로그·재시작 관리에 더 낫다.

### 주간 스냅샷 자동 생성 (배치)

Linux 의 cron 대신 작업 스케줄러를 쓴다. 매주 금요일 18:10:

```bat
schtasks /create /tn "MP Snapshot Weekly" ^
    /tr "C:\apps\performance_monitor\.venv\Scripts\python.exe C:\apps\performance_monitor\tools\build_snapshot.py --auto" ^
    /sc weekly /d FRI /st 18:10 /ru <계정> /f
```

이 배치는 사내 DB 와 `jackhammer` / `vrksa` 가 필요하다.
노트북에서 `pm.export_snapshot(globals())` 로 만드는 방식을 쓰면 배치 등록은 불필요하다.

### Windows 에서 주의할 점

| 항목 | 내용 |
|---|---|
| 경로 길이 | 260자 제한에 걸릴 수 있다. `C:\apps\` 처럼 짧은 경로에 두는 편이 안전 |
| 줄바꿈 | `.bat` 은 CRLF 여야 한다. Git 설정이 `core.autocrlf=true` 면 자동 처리됨 |
| 한글 깨짐 | cmd 기본 코드페이지(949) 문제. 로그가 깨지면 `chcp 65001` 후 실행 |
| Tibero ODBC | 스냅샷 생성 시에만 필요. Windows 용 Tibero6 ODBC 드라이버가 설치·등록돼 있어야 `pyodbc` 가 붙는다 |
| pymssql | `pip install pymssql` 필요 (requirements 에는 없음 — 스냅샷 생성 전용) |
| PowerShell 실행정책 | `.bat` 은 영향 없음. `.ps1` 로 감쌀 때만 문제 |

---

## 3. 설치 확인

```bash
cd performance_monitor

python -m pytest tests/ -q
# 46 passed  ← 계산 로직이 온전히 반입됐다는 뜻

python tools/make_demo_snapshot.py --weeks 6 --stocks 30
./run_dashboard.sh
# http://localhost:8501
```

여기까지 되면 **사내 DB 없이도** 화면이 뜬다.
그 다음 노트북에서 `pm.export_snapshot(globals())` 로 실제 데이터를 넣으면 된다.

사내 서버에 올려 팀 전체가 쓰려면:
```bash
./run_dashboard.sh server    # http://<서버>/performance
```

---

## 4. 실행에 인터넷이 필요한가

**아니다.** 설치만 끝나면 인터넷 없이 완전히 동작한다.

| 항목 | 외부 통신 |
|---|---|
| 계산 | 없음 (pandas / numpy / 사내 데이터) |
| 차트 | 없음 (plotly 를 패키지에 포함된 JS 로 렌더) |
| 폰트 / CSS | 없음 (외부 CDN·웹폰트 미사용) |
| 외부 LLM / SaaS | 없음 |
| Streamlit 사용통계 | **차단됨** (`run_dashboard.sh` 가 `gatherUsageStats=false` 설정) |

사내 DB(MSSQL / Tibero)만 접근하며, 그것도 **스냅샷 생성 시에만** 필요하다.
Dashboard 실행에는 DB 접속조차 필요 없다.

방화벽 차단 여부를 확인하려면 화면을 띄운 뒤 브라우저 개발자도구 Network 탭에서
외부 도메인 요청이 없는지 보면 된다.

---

## 5. 자주 막히는 지점

| 증상 | 원인 / 조치 |
|---|---|
| `pip install` 이 timeout | 미러 미설정. 2절의 `--no-index --find-links` 사용 |
| wheel 설치 시 `not a supported wheel on this platform` | 다른 OS/Python 용 wheel. 대상 환경을 맞춰 다시 받을 것 |
| `pyarrow` 설치 실패 | 없어도 된다. 스냅샷이 자동으로 pickle 로 폴백한다. `requirements.txt` 에서 빼도 무방 |
| `openpyxl` 없음 | Excel 내보내기만 안 된다. CSV 는 정상 |
| 브라우저에서 접속 불가 | `--server.address 0.0.0.0` 필요. 서버 방화벽에서 8501 포트 개방 확인 |
| 한글이 네모로 깨짐 | 서버가 아니라 **보는 PC** 의 폰트 문제. 화면은 브라우저가 그리므로 보통 문제없음 |
| 사내 프록시 때문에 pip 가 느림 | `pip install --proxy http://프록시:포트 ...` 또는 wheelhouse 사용 |

---

## 6. 매주 갱신은 어떻게

**코드는 자주 안 바뀐다.** 바뀌는 건 데이터뿐이고, 데이터는 사내에서 만든다.

```python
# 노트북 맨 아래 (사내망 안에서 실행)
import pm_engine as pm
pm.export_snapshot(globals())
```

즉 **최초 반입 이후에는 인터넷이 다시 필요하지 않다.**
코드 수정분이 생겼을 때만 1절의 방법으로 다시 반입하면 된다.
