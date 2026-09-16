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

## 막히는 지점

| 증상 | 조치 |
|---|---|
| 그래프가 빈 칸으로 나온다 | `po.init_notebook_mode(connected=False)` 를 먼저 실행 |
| `launch_dashboard` 가 streamlit 을 못 찾는다 | 프로젝트 폴더에 `.venv` 를 만들고 `requirements.txt` 설치. 안내문에 명령이 나온다 |
| `Network paths are not supported` | 프로그램이 네트워크 드라이브에 있다. 로컬로 옮기고 `PM_DATA_DIR` 로 데이터만 공유 폴더 지정 (`docs/OFFLINE_INSTALL.md`) |
| 스냅샷이 없다고 나온다 | `pm.export_snapshot(globals())` 를 먼저 실행 |
| 서버가 곧바로 죽는다 | 출력에 로그 경로와 마지막 내용이 나온다 |
| 다른 PC 에서 접속 안 됨 | `host='0.0.0.0'`(기본) + 방화벽 포트 개방 |
