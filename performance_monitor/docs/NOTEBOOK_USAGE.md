# 노트북에서 Dashboard 보기

사내망 IPython/Jupyter 환경에서 바로 쓰는 방법이다.
노트북 서버는 이미 데이터(vrksa / jackhammer / DB)에 접근하므로, 여기서 실행하면
파일을 옮길 필요가 없다.

두 가지 방법이 있다. 환경에 맞는 쪽을 쓰면 된다.

| | 방법 A — 서버 띄우기 | 방법 B — 노트북 안에 그리기 |
|---|---|---|
| 호출 | `pm.launch_dashboard()` | `pm.report()` |
| 결과 | 브라우저에서 전체 대시보드 | 셀 출력에 요약 화면 |
| 필요 조건 | 포트 접근 가능 | 없음 |
| 화면 | 8개 메뉴 전부, 필터·drill-down | 요약(KPI·누적·기여도·종목·모델·업종) |
| 팀 공유 | 주소만 알려주면 됨 | 노트북을 HTML 로 내보내 공유 |

**계산은 둘 다 같은 엔진**(`src/dashboard_engine.py`)을 쓴다. 숫자가 다를 수 없다.

---

## 준비 — 한 번만

노트북 첫 셀에 넣는다.

```python
import sys
sys.path.insert(0, r'C:\apps\performance_monitor\notebooks')   # 설치 경로

import plotly.offline as po
po.init_notebook_mode(connected=False)   # 폐쇄망 필수: connected=True 는 CDN 을 쓴다

import pm_engine as pm
```

> `connected=False` 가 중요하다. `True` 면 plotly.js 를 인터넷에서 받으려 해
> 폐쇄망에서 그래프가 안 보인다.

`pm_engine` 은 **streamlit 없이도** import 된다. 운용 커널에 대시보드 패키지를
설치할 필요가 없다 (pandas 1.5.3 커널에서 확인).

---

## 매주 하는 일

```python
# 1) 평소대로 노트북을 끝까지 실행한 뒤
pm.export_snapshot(globals())    # 스냅샷 생성

# 2) 화면 보기 (둘 중 하나)
pm.launch_dashboard()            # 서버
pm.report()                      # 노트북 안
```

`export_snapshot` 은 계산을 다시 하지 않고 노트북이 만든 객체를 그대로 저장하므로
**대시보드 숫자가 노트북과 다를 수 없다.**

---

## 방법 A — `pm.launch_dashboard()`

```python
pm.launch_dashboard()
```

```
Dashboard 실행 중  (python: 프로젝트 가상환경 (C:\apps\performance_monitor\.venv\Scripts\python.exe))
  이 서버에서      : http://localhost:8501
  다른 PC 에서     : http://SRV-QUANT01:8501   (방화벽에서 8501 포트 개방 필요)
  스냅샷           : C:\apps\performance_monitor\data\processed  (3개)
  로그             : C:\apps\performance_monitor\logs\dashboard_server.log
  중지             : pm.stop_dashboard()
```

- **별도 프로세스**로 띄우므로 커널 환경(vrksa / jackhammer / 구버전 pandas)을 건드리지 않는다.
- 프로젝트의 `.venv` 를 자동으로 찾아 쓴다. 없으면 커널에 streamlit 이 있을 때만 동작한다.
- 이미 실행 중이면 새로 띄우지 않고 기존 주소를 알려준다.

```python
pm.launch_dashboard(port=9000)                 # 포트 지정
pm.launch_dashboard(host='127.0.0.1')          # 이 서버에서만
pm.launch_dashboard(data_dir='M:/공유/데이터')  # 스냅샷 위치 지정
pm.dashboard_status()                          # 상태
pm.stop_dashboard()                            # 중지
```

노트북 커널을 재시작하면 서버도 함께 죽는다. 상시 운영하려면
`run_dashboard.bat server` 를 작업 스케줄러에 등록하는 편이 낫다.

### 포트를 못 열면

`jupyter-server-proxy` 가 설치돼 있으면 노트북 주소로 접속할 수 있다.
설치돼 있으면 `launch_dashboard()` 가 알아서 안내한다.

```
  Jupyter 경유     : <노트북주소>/proxy/8501/
```

없으면 방법 B 를 쓴다.

---

## 방법 B — `pm.report()`

셀 출력에 요약 화면을 그린다. 포트가 필요 없다.

```python
pm.report()                          # 최신 스냅샷 / 상위 모델 / 주간
pm.report(preset='1D')               # 일간
pm.report(preset='MTD')              # 월간
pm.report(model='KS2_VALUE_FP')      # 특정 하위 모델
pm.report(as_of='2026-09-11')        # 과거 스냅샷
pm.report(sector_field='q_sector')   # 섹터 기준 변경
pm.snapshots()                       # 쓸 수 있는 스냅샷 목록
```

그려지는 것:

- KPI (MP / Benchmark / Excess / Specific / Risk Factor / Industry Factor)
- Summary (Top·Bottom Contributor, Best·Worst Model)
- 누적 성과 (MP / Benchmark / Excess)
- 성과 기여도 (항목별)
- 종목별 기여도 Top / Bottom
- 모델별 Active
- 업종별 기여도

### 결과를 더 가공하고 싶으면

```python
out = pm.report(show=False)          # 그리지 않고 결과만

out['tables']['stocks']              # 종목별 표 (DataFrame)
out['tables']['return_contribution_final']   # 원본 기여도 표
out['figures']['attribution']        # plotly figure

# 회의 자료로 내보내기
out['tables']['stocks'].to_excel('주간_종목기여도.xlsx')
out['figures']['stocks'].write_html('종목기여도.html')
```

`preset` 별 값을 비교하는 것도 된다.

```python
for preset in ('1D', '1W', 'MTD'):
    r = pm.report(preset=preset, show=False)
    rcf, m = r['period']['return_contribution_final'], r['model']
    print(f"{preset}: total={float(rcf.loc['total',m]):.4%} "
          f"active={float(rcf.loc['active',m]):.4%}")
```

---

## 결과 대조

노트북을 평소대로 실행한 직후 같은 커널에서:

```python
pm.compare(globals())
```

```
항목                     Notebook    Dashboard   Difference   일치
total (전 모델)          ...         ...         0.00e+00     OK
active (전 모델)         ...         ...         0.00e+00     OK
...
✅ 전 항목 일치 (허용오차 1e-12)
```

---

## 코드 업데이트 — `pm.update()`

새 버전을 받는 경로다. **git 은 필요 없다** (zip 을 받아 덮어쓴다).

### 먼저 확인 — 이 서버에서 GitHub 가 열리나?

데스크톱에서 막혀 있어도 노트북 서버는 다른 경로로 나갈 수 있으므로
한 번 확인해 볼 가치가 있다.

```python
pm.check_github()
```

```
✓ GitHub 연결 가능 (HTTP 200)
  프록시: http://proxy.내부주소:8080
  → pm.update() 로 바로 받을 수 있습니다.
```

막혀 있으면 이렇게 나온다.

```
✗ GitHub 에 닿지 않습니다 (URLError: [Errno 101] Network is unreachable)
  프록시 환경변수가 없습니다. 사내 프록시가 있다면:
      import os
      os.environ['HTTPS_PROXY'] = 'http://프록시주소:포트'
      pm.check_github()
  → 반입한 파일로 업데이트하십시오:
      pm.update(r'C:\temp\performance_monitor_win.zip')
```

사내 프록시 주소를 알고 있다면 위 두 줄을 실행한 뒤 다시 확인해 보십시오.
그래도 안 되면 망 자체가 막힌 것이라 **코드로 뚫을 수 없다.** 아래 파일 경로를 쓴다.

### GitHub 가 열릴 때

```python
pm.update(dry_run=True)   # 무엇이 바뀌는지만 먼저 본다
pm.update()               # 실제 적용
```

저장소가 비공개라 `HTTP 404` 가 나오면 개인 액세스 토큰이 필요하다.

```python
pm.update_from_github(token='ghp_...')
```

### GitHub 가 막혀 있을 때 (사내망 기본)

인터넷 되는 PC 에서 zip 을 내려받아 반입한 뒤:

```python
pm.update(r'C:\temp\performance_monitor_win.zip')   # .zip / .tar.gz / 폴더
```

### 무엇이 바뀌고 무엇이 그대로인가

| 대상 | 처리 |
|---|---|
| `src/` `tools/` `app.py` `pages/` `notebooks/` `docs/` | 덮어쓴다 |
| `data/` (주간 스냅샷) | **건드리지 않는다** |
| `logs/` `.venv/` `wheelhouse/` | **건드리지 않는다** |
| `config/` | **덮어쓰지 않는다.** 새 버전이 다르면 옆에 `.yaml.new` 로 두고 알려 준다 |

`config/` 에는 DB 주소·모델 목록 같은 사내 설정이 들어 있어 자동으로 바꾸지 않는다.
`config.yaml.new` 가 생기면 직접 비교해서 필요한 줄만 옮기십시오.

지운 파일을 따라 지우지는 않는다(덧씌우기만 한다). 완전히 깨끗하게 새로 깔려면
새 폴더에 압축을 풀고 `data/` 만 옮기면 된다.

### 적용 후

```python
pm.current_version()
# {'source': 'file:performance_monitor_win.zip', 'installed_at': '2026-09-16T16:40:02'}
```

> ⚠ **커널을 재시작해야** 바뀐 코드가 반영된다. 이미 import 된 모듈은 그대로이기 때문이다.
> 재시작 후 `import pm_engine as pm` 부터 다시 실행하십시오.

---

## 막히는 지점

| 증상 | 조치 |
|---|---|
| 그래프가 빈 칸으로 나온다 | `po.init_notebook_mode(connected=False)` 를 먼저 실행 |
| `launch_dashboard` 가 streamlit 을 못 찾는다 | 프로젝트 폴더에 `.venv` 를 만들고 `requirements.txt` 설치. 안내문에 명령이 나온다 |
| `Network paths are not supported` | 프로그램이 네트워크 드라이브에 있다. 로컬로 옮기고 `PM_DATA_DIR` 로 데이터만 공유 폴더 지정 (`docs/OFFLINE_INSTALL.md`) |
| 스냅샷이 없다고 나온다 | `pm.export_snapshot(globals())` 를 먼저 실행 |
| 서버가 곧바로 죽는다 | 출력에 로그 경로와 마지막 내용이 나온다 |
| 다른 PC 에서 접속 안 됨 | `host='0.0.0.0'`(기본) + 방화벽 포트 개방 |
| `pm.update()` 가 GitHub 에 못 닿는다 | 사내망에서 막힌 것이다. 반입한 zip 으로: `pm.update(r'C:\temp\...zip')` |
| 업데이트했는데 그대로다 | 커널 재시작 후 `import pm_engine as pm` 부터 다시 실행 |
| `config.yaml.new` 가 생겼다 | 설정이 새 버전과 다르다. 직접 비교해서 필요한 줄만 옮긴다 (기존 설정은 그대로 유지됨) |
