# MP Performance Monitor

주간 성과회의용 **내부 Performance Monitoring Dashboard**.

현재 운용에 쓰는 `.ipynb` / Python 코드의 계산 로직을 **Single Source of Truth** 로 두고,
그 위에 자동화된 화면을 올린 것이다. **새로운 성과분석 모델을 만든 것이 아니다.**

- 기존 notebook 은 그대로 남아 있고 계속 쓸 수 있다.
- Notebook 과 Dashboard 가 **같은 함수**(`src/`)를 호출한다 → 로직 수정은 한 곳에서만.
- **외부 LLM / SaaS / telemetry 를 전혀 쓰지 않는다.** 인터넷 없이 사내망에서 단독 실행된다.

---

## 1. 빠른 시작

```bash
pip install -r requirements.txt

# (점검용) 합성 데이터 스냅샷 생성 — 사내 DB 없이 화면 확인
python tools/make_demo_snapshot.py

./run_dashboard.sh          # http://localhost:8501
```

사내 서버 배포:

```bash
./run_dashboard.sh server   # http://<internal-server>/performance
```

---

## 2. 구조

```
[Data Layer]          data/ + src/data_loader.py   (스냅샷 / 사내 DB)
      ↓
[Existing Quant Logic] notebooks/*.ipynb           (원본 그대로)
      ↓
[Analytics Engine]    src/performance.py, attribution.py, benchmark.py,
                      portfolio.py, model_analysis.py, validation.py
      ↓
[Dashboard / Reporting] app.py + pages/ + src/export.py
```

```
                 src/  (Core Analytics)
                       ↑
              ┌────────┴────────┐
          Notebook          Dashboard
```

```
performance_monitor/
    app.py                      # 메인 Dashboard
    run_dashboard.sh
    requirements.txt
    pages/
        1_Performance.py        # 누적 성과 / 기간 성과
        2_Attribution.py        # 성과 분해 (항목/종목/섹터/팩터/추이)
        3_Models.py             # 상위·하위 모델 분석 및 비교
        4_Stocks.py             # 종목 분석 / Active Weight / 종목 상세
        5_Position_Change.py    # 주간 포지션 변화
        6_Data_Validation.py    # 데이터 검증 / 로그
        7_Export.py             # Excel / CSV 내보내기
    src/
        config.py               # 설정 로딩
        data_loader.py          # 스냅샷 IO + 사내 DB 접근(DbSource)
        performance.py          # 수익률 / Alog·alphalog·betalog
        attribution.py          # 기여도 (CELL 46~54)
        benchmark.py            # BM 수익률 / 섹터 BM 수익률
        portfolio.py            # 비중 / Active Weight / Position Change
        model_analysis.py       # 모델 비교
        validation.py           # Validation Layer
        pipeline.py             # CELL 40~54 오케스트레이션
        dashboard_engine.py     # 기간 선택 → 집계 (화면 전용 조회 계층)
        export.py               # Weekly Snapshot Excel
        optional_metrics.py     # TE / Hit Ratio / Turnover (기존 코드 외, 기본 OFF)
        ui.py                   # Streamlit 공통 레이어
        logging_utils.py, utils.py
    config/
        config.yaml             # Benchmark / Model / 기간 / 검증 임계값 / DB
        bpm_factors.yaml        # Barra 팩터명 매핑 (CELL 6, 17)
        sector_overrides.yaml   # new_sector 수기 조정 70종목 (CELL 12)
        corporate_actions.yaml  # 인적분할 / 편출 내역 (CELL 30~36)
    data/
        raw/ processed/ reference/ archive/
    notebooks/                  # 기존 notebook 원본 + pm_engine.py
    tools/
        export_snapshot_from_notebook.py   # ★ 권장 주간 작업
        build_snapshot.py                  # 배치(cron)용
        compare_with_notebook.py           # PHASE 10 결과 대조
        make_demo_snapshot.py              # 합성 데이터 (점검용)
    tests/
    docs/CURRENT_ANALYSIS_FLOW.md          # ★ 기존 로직 분석 문서
```

---

## 3. 매주 하는 일

### 방법 A — 노트북을 평소대로 실행 (권장)

계산을 다시 하지 않고 노트북이 만든 객체를 그대로 저장하므로
**Dashboard 결과가 노트북과 다를 수 없다.**

`Performance_Analysis_Module_ver2_.ipynb` 에서 `report_start_date` / `mp_end_date` 를
평소처럼 바꿔 끝까지 실행한 뒤, 맨 아래에 셀 하나를 추가한다.

```python
import sys
sys.path.append('/srv/performance_monitor/notebooks')
import pm_engine as pm

pm.export_snapshot(globals())    # data/processed/snapshot_YYYYMMDD/ 생성
pm.compare(globals())            # (선택) 노트북 vs 엔진 결과 대조표
```

Dashboard 를 새로고침하면 사이드바 **데이터 기준일** 에 새 스냅샷이 자동으로 뜬다.
파일명을 코드에 하드코딩하지 않으며, 최신 스냅샷은 `manifest.json` 의 `as_of` 로 판단한다.

### 방법 B — 배치 실행 (cron)

노트북의 **code 셀을 그대로 실행**하고 스냅샷까지 만든다. 사내 DB / `jackhammer` / `vrksa` 가 필요하다.

```bash
python tools/build_snapshot.py --auto
# 또는
python tools/build_snapshot.py --mp-end-date 2026-09-11 --report-start-date 2026-09-04

# 매주 금요일 18:10
# 10 18 * * 5  cd /srv/performance_monitor && python tools/build_snapshot.py --auto
```

BM 정기변경 선반영이 필요한 주에는 원본과 동일하게:

```bash
python tools/build_snapshot.py --auto --bm-pre-rebal \
    --rebal-end-dt 2026-06-08 --bm-reb-date 2026-06-12
```

---

## 4. 화면에서 고르는 것

| 항목 | 설명 |
|---|---|
| 데이터 기준일 | 스냅샷 선택 (최신순) |
| 분석 시작일 | **기준일**. 원본과 동일하게 직전 주(월) 마지막 영업일을 넣는다. 이 날 수익률은 기간 성과에서 제외된다 (`report_date_list[1:]`) |
| 분석 종료일 | |
| Benchmark | 스냅샷 생성 시 결정됨 (`analysis_bm`). 다른 BM 은 해당 BM 스냅샷을 선택 |
| 상위 Model / MP | 기본값 = `RP` |
| 하위 Model | 비교 대상 다중 선택 |
| 섹터 기준 | `q_sector` (vrksa 기본) / `new_sector` (수기 조정) |
| 비교 기간 | WTD / MTD / QTD / HTD / YTD / 1Y — 기준일은 `WORKDATE_MAST_TB` 조회값 |

필터는 `session_state` 로 공유되어 페이지를 옮겨도 유지된다.

> 기간을 스냅샷 기본 구간과 다르게 고르면 화면 상단에 안내가 뜨고,
> **스냅샷의 일별 값에서 동일 함수로 재집계**한다 (`source: recomputed`).
> 노트북과 1:1 대조할 때는 기본 구간을 쓴다 (`source: snapshot`).

---

## 5. 계산 로직 — 무엇이 어디서 왔는가

전체 내용은 **[`docs/CURRENT_ANALYSIS_FLOW.md`](docs/CURRENT_ANALYSIS_FLOW.md)** 참조.
핵심만 요약하면:

| 항목 | 계산식 | 원본 |
|---|---|---|
| MP 일별 수익률 | `jh.ScoreBasedPortfolio(total_weight).run_backtest(...).returns` | CELL 39 |
| BM 일별 수익률 | `exp(log_rtn_bm[bm]) − 1` | CELL 25 |
| 기간 수익률 | `((r+1).cumprod()).iloc[-1] − 1` over `report_date_list[1:]` | CELL 40 |
| Excess | `total − bm` | CELL 40 |
| scaling | `Alog`, `alphalog`, `betalog = alphalog × Alog` | CELL 40 |
| 종목 active 기여도 | `w_next[t] × (fwd_ret[t] − bm_ret[t+1])` | CELL 46 |
| market timing | `w_next[t] × (pred_beta[t] − bm_pred_beta[t+1]) × bm_ret[t+1]` | CELL 47 |
| risk/industry factor | `w_next[t] × exposure[t] × factor_ret[t+1]` | CELL 48, 49 |
| country | `w_next[t] × country_ret[t+1]` | CELL 50 |
| specific | `active − market_timing − country − Σ(risk+industry)` | CELL 51 |
| 기간 집계 | `Σ_d (일별합 × betalog.shift(-1))` | CELL 52 |
| allocation | 섹터 active weight × (섹터 BM 수익률 − BM 수익률).shift(-1) × betalog.shift(-1) | CELL 53 |
| selection | `active − allocation` | CELL 53 |
| 기여도 추이 | `cumsum(일별합 × betalog.shift(-1)).shift(1).fillna(0)` | CELL 54 |

**하위 모델 구조** (`config/config.yaml`, 원본 CELL 3에서 추출):

```
RP = Hanwha_Quant_KS2_RP          ← 상위 실운용 포트폴리오
 ├ KS2_CONSENSUS_FP  KS2_DIVIDEND_FP  KS2_INVESTMENT_FP  KS2_LTREV_FP
 ├ KS2_NEWIAM_FP     KS2_PRICEMOMENTUM_FP  KS2_PROFITABILITY_FP
 ├ KS2_PROFITABILITYGROWTH_FP    KS2_VALUE_FP
 └ Hanwha_Quant_KS2_MP           ← 하위 FP 합성 모델
```

> **RP 는 하위 모델의 가중합이 아니다.** 각 모델이 독립적인 active weight 시계열이며
> 동일한 분해식을 각각 적용한다. 원본에 Aggregation 로직이 없으므로 만들지 않았다.
> KSP(kospi) 는 여기에 `KSP_LIQUIDITY_FP` 가 추가된다.

### 거래비용 / 슬리피지
MP·RP 성과분해 코드에는 **없다.** 임의로 추가하지 않았다.
(펀드 단계의 `other_contribution` 잔차에만 포함되며, 해당 노트북은 미제공이라 범위 밖이다.)

### 기존 로직을 바꾼 부분
없다. 다만 다음 두 가지는 명시해 둔다.

1. `CELL 51` 의 `if i < len(date_list)+1` 은 항상 참인 조건이다. **원본 그대로 유지**했다.
2. 3중 `for` 루프(일자×팩터×모델)를 **벡터화하지 않았다.** 연산 순서가 바뀌면 부동소수점
   결과가 미세하게 달라질 수 있어서다. 이 계산은 주 1회 스냅샷 생성 시에만 돌고
   대시보드 응답속도와 무관하다.

접속정보는 평문 하드코딩에서 환경변수로 옮겼다 (`PM_MSSQL_URL`, `PM_TIBERO_DSN`).
기본값은 기존 값 그대로라 동작이 달라지지 않는다.

---

## 6. 결과 일치성 검증

### 6-1. Unit Test

```bash
python -m pytest tests/ -q
```

`tests/notebook_reference.py` 에 **노트북 원본 코드를 그대로 붙여넣은 참조 구현**이 있고,
`tests/test_notebook_parity.py` 가 `src/` 결과와 대조한다 (허용오차 `1e-15`).

검증하는 항등식:
- `active == total − bm`
- `active == market_timing + risk_factor + industry_factor + country + specific`
- `Σ 종목 기여도 == active`
- `allocation + selection == active`
- `Σ 섹터별 allocation == 전체 allocation`
- 기여도 추이의 마지막 값 `== active`

### 6-2. 실데이터 대조 (PHASE 10)

노트북을 평소대로 실행한 뒤 같은 커널에서:

```python
import pm_engine as pm
pm.compare(globals())
```

```
항목                     Notebook    Dashboard   Difference   일치
total (전 모델)          ...         ...         0.00e+00     OK
active (전 모델)         ...         ...         0.00e+00     OK
specific (전 모델)       ...         ...         0.00e+00     OK
stock_contribution[RP]   ...         ...         0.00e+00     OK
...
✅ 전 항목 일치 (허용오차 1e-12)
```

핵심 값의 차이는 원칙적으로 **0** 이어야 한다. 부동소수점 오차만 허용한다.

---

## 7. 데이터 검증 (Validation Layer)

분석 전에 자동 실행되며, **문제가 있으면 화면 상단에 그대로 노출**한다.

검증 항목: Missing Price / Missing Weight / Duplicate Stock / Weight Sum /
Missing Benchmark / Missing Model / Date Gap / Invalid Return / Contribution 합계

```
Data Validation
Portfolio Weight Sum : 99.98% OK
Missing Price        : 0
Missing Benchmark    : 0
Duplicate            : 0
```

> **데이터 오류를 자동으로 0 처리하지 않는다.** 문제 종목·일자를 전부 열거한다.

임계값은 `config/config.yaml` 의 `validation` 에서 조정한다.

---

## 8. Optional 지표

`Tracking Error` / `Hit Ratio` / `Turnover` 는 **기존 코드에 존재하지 않는다.**
(노트북의 risk profile 셀들은 "서버 과부하로 인한 미실행" 상태)

따라서 기본값 OFF 이고, `config/config.yaml` 에서 켜면 화면에 `(Optional)` 로 표기된다.
**노트북 대조 대상이 아니다.** 정의는 `src/optional_metrics.py` 의 docstring 참조 —
실제 운용에 쓰려면 사내 정의를 먼저 확정해야 한다.

---

## 9. Export

- 각 화면의 표마다 **CSV / Excel** 다운로드 버튼
- **Export** 메뉴에서 `Weekly Performance Snapshot` 을 Excel 한 파일로:
  `Summary` / `Performance` / `Performance_Cumulative` / `Attribution` /
  `Attribution_Sector` / `Models` / `Stocks` / `PositionChange` / `Validation`
- 원본 스냅샷 테이블(`return_contribution_final` 등)도 그대로 내보낼 수 있다 (대조용)

---

## 10. 성능 / 캐시 / 로그

- 스냅샷은 `@st.cache_data` 로 캐싱된다.
- **캐시 키에 파일 mtime·size 가 들어 있어, 데이터가 바뀌면 자동으로 무효화된다.**
- 무거운 계산(일별 종목별 기여도)은 스냅샷 생성 시 1회만 수행하고 화면은 집계만 한다.
- 로그는 `logs/YYYYMM.log` 에 남고 **Data Validation** 화면에서 볼 수 있다.

---

## 11. 보안 / 독립 실행

- 외부 AI API (OpenAI / Claude / Gemini / 기타 LLM) **사용하지 않음**
- 외부 SaaS 분석 서비스, telemetry, tracking **사용하지 않음**
- Streamlit 사용통계 수집은 `gatherUsageStats = false` 로 차단 (`run_dashboard.sh` 가 자동 설정)
- 모든 계산은 Python / pandas / NumPy / 기존 내부 코드 / 내부 데이터 기반
- **인터넷 연결 없이 동작한다.** Claude·GPT 는 개발 과정에서만 사용했고, 완성된 시스템은 독립 실행된다.

DB 접속정보는 환경변수로 주입한다:

```bash
export PM_MSSQL_URL='mssql+pymssql://USER:PASS@172.32.1.100'
export PM_TIBERO_DSN='Driver={Tibero6};Server=172.31.3.62;Port=8629;UID=...;Database=PBIDB;Password=...'
```

미설정 시 `config/config.yaml` 의 기존 기본값을 쓴다 (동작 호환).
Dashboard **실행**에는 DB 접속이 필요 없다 — 스냅샷만 읽는다.

---

## 12. 알려진 범위 밖 항목

| 항목 | 사유 |
|---|---|
| 펀드 성과 분해 (`Function_fund_return_calculation_ver2.ipynb`) | 해당 노트북 미제공. Copy Ratio / MP·RP·Manager·Other contribution 화면 없음 |
| Risk Profile / Risk Contribution (CELL 57~64) | 원본이 "서버 과부하로 인한 미실행" raw 셀 상태 |
| Alpha Score / IC 분석 (`Function_get_score_ver1.ipynb`) | 주간 성과회의 범위 밖 (알파 리서치) |
| 순수 매매 Turnover | `portfolios.portfolio_trades` 가 스냅샷에 없음. 현재 화면의 비중 변화에는 가격 drift 포함 |

필요하면 해당 노트북/테이블을 주면 같은 방식(원본 로직 보존)으로 붙일 수 있다.
