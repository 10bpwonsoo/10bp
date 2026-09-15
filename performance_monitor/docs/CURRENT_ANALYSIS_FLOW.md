# Current Performance Analysis Flow (PHASE 1 분석 결과)

> 이 문서는 **기존 운용 코드를 그대로 기술한 것**이다. 새로운 계산식은 없다.
> 대상 파일:
> - `notebooks/Performance_Analysis_Module_ver2_.ipynb` (실행 진입점 / 화면·표·그래프)
> - `notebooks/Function_calculation_return_contribution_ver2.ipynb` (핵심 계산 엔진)
> - `notebooks/Function_get_score_ver1.ipynb` (Alpha score, 주간 성과회의 밖 영역)
> - `notebooks/shared_data.py`, `notebooks/shared_func.py` (DB I/O)
> - `Function_fund_return_calculation_ver2.ipynb` (**미제공** — 펀드 성과 분해. 아래 9절 참조)

---

## 1. 현재 데이터 구조

### 1.1 외부 의존성 (모두 사내 전용)

| 구성요소 | 정체 | 사용처 |
|---|---|---|
| `vrksa` (`vr`, `vc`, `vdk`, `vh`) | 사내 리서치 데이터 라이브러리 | BPM factor/industry exposure, 가격, 섹터, 지수비중 |
| `jackhammer` (`jh`, `jh.ScoreBasedPortfolio`) | 사내 백테스트/최적화 라이브러리 | **일별 weight drift + 일별 포트폴리오 수익률** |
| MSSQL `172.32.1.100` (`mssql+pymssql://performer:newquant@…`) | BQUANT | MP/RP target weight, benchmark weight, scores, 종목명, 지수 종가 |
| Tibero `172.31.3.62:8629` (PBIDB, `uquant`) | HWBI | KRX 지수 구성종목·시총, Barra(KRE3S) factor return / exposure / specific return / predictive beta / covariance / risk, 펀드 NAV |

### 1.2 핵심 DataFrame

| 이름 | Index | 내용 |
|---|---|---|
| `data_bpm_factor` | `(date, item)` | Barra factor/industry exposure 41종, `price_adj`, `return_d`, `forward_return_d`, `q_sector`, `new_sector`, `weight_<bm>`, `weight_<bm>_next`, `is_<bm>`, `market_cap_*` |
| `mp_weight` | `(date, item)` | 리밸런싱일 RP **active weight** (`portfolios.simple_rebalancing_target_weights`) |
| `final_mp` | `(date, item)` | **중심 테이블.** 모델별 active/total weight(일별 drift 반영), `bm`, `bm_next`, `<model>_next`, exposure, `predictive_beta`, `specific_return`, 그리고 종목·항목별 `*_contribution_<model>` 컬럼 전체 |
| `temp_return_final` | `date` | 모델별 + `bm` 일별 **단순수익률** |
| `log_rtn_bm` | `date` | BM **로그수익률** (kospi, kospi200, krx300, kosdaq, kosdaq150, nps, kospi_large/mid/small) |
| `rtn_bpm` | `date × factor` | Barra 팩터 일별 수익률 (`list_bpm_factor` 17개 + `list_bpm_sector` 21개 + `country`) |
| `bpm_pred_beta` | `date × item` | Barra predictive beta |
| `rtn_bpm_spec` | `date × item` | Barra specific return |
| `index_market_cap` | `(date, item)` | BM 구성종목 지수시총 (`bm`, `bm_next`) → 섹터 BM 수익률 산출용 |
| `return_contribution_final` | 항목 × 모델 | 기간 성과 분해 결과 (`total/bm/active/market_timing/specific/risk_factor/industry_factor/country/selection/allocation/selection_new/allocation_new`) |
| `compare_final` | `(date, contribution)` × 모델 | 항목별 **누적** 기여도 추이 |
| `sector_compare_final` / `new_sector_compare_final` | 섹터 × `<model>_allocation`/`_selection` | 섹터별 Allocation/Selection |
| `betalog_final` | `date` × 모델 | 일별 → 기간 기여도 환산 scaling factor |

### 1.3 날짜 처리

- 모든 날짜는 **UTC tz-aware** (`pd.to_datetime(..., utc=True)`).
- `total_date_list` = `data_load_start ~ mp_end_date` 영업일 (BM 수익률 인덱스 기준)
- `date_list` = `mp_start_date ~ mp_end_date` 영업일 — **계산 구간**
- `report_date_list` = `report_start_date ~ mp_end_date` 영업일 — **리포트 구간**
  - `report_start_date`는 **직전 주(월) 마지막 영업일**. 즉 `report_date_list[0]`은 성과 기간에 포함되지 않는 기준일이며,
    수익률 집계는 항상 `report_date_list[1:]`을 쓴다.
- 비교기간 기준일(`mtd/qtd/htd/ytd/1y_ago`)은 `AQUANT.dbo.WORKDATE_MAST_TB`에서 SQL로 조회 (`Performance_Analysis_Module` CELL 16~18).
- 휴일: 별도 캘린더 없이 **BM 종가가 존재하는 날**이 영업일. 결측은 `fillna(0)`(BM 로그수익률) 또는 백테스트 drift로 처리.

---

## 2. MP 수익률 계산 방식

`Function_calculation_return_contribution_ver2.ipynb` CELL 25 / 39.

1. DB에서 모델별 **active weight**를 읽는다 (`sd.load_target_weights(mp_nm)`).
2. `total_<model> = active_<model> + bm` (BM weight는 `weight_<analysis_bm>`).
3. `jh.ScoreBasedPortfolio`에 `total_<model>`을 score로 주고
   `set_rebalancing(schedule=rebalance_date_list, method='RAW')` →
   `run_backtest(start=rebalance_date_list[0], end=mp_end_date, pricing=data_bpm_factor[['return_d']])`.
   - 결과 `backtest_result.weights` → `final_mp['total_<model>']` (**일별 drift weight**)
   - 결과 `backtest_result.returns` → `temp_return_final['<model>']` (**일별 포트폴리오 단순수익률**)
4. drift 이후 active weight 재계산:
   - `final_mp['<model>']      = total_<model> - bm`
   - `final_mp['<model>_next'] = total_<model> - bm_next`  ← **기여도 계산에 쓰이는 값**
5. 기간 수익률: `((temp_return_final.loc[report_date_list[1:], col] + 1).cumprod()).iloc[-1] - 1`

> **중요**: 일별 weight drift와 포트폴리오 수익률은 `jackhammer`가 계산한다.
> Dashboard는 이 값을 **재구현하지 않고 그대로 스냅샷에 저장하여 사용**한다.

`bm_next`는 지수 정기변경(차기 구성) 대응용이다. 기여도는 항상 `_next` active weight를 쓴다.

## 3. Benchmark 수익률 계산 방식

`Function_calculation_return_contribution_ver2.ipynb` CELL 15.

- 지수 종가: `fngdb.dbo.fns_ud`의 `cls_prc` (`I.001`=kospi, `I.101`=kospi200, `I.201`=kosdaq, `I.405`=krx300, `I.253`=kosdaq150, `I.002/3/4`=kospi 대/중/소형)
- `log_rtn_bm = np.log(1 + prc.pct_change(1)).fillna(0)`
- 일별 단순수익률: `temp_return_final['bm'] = np.exp(log_rtn_bm[analysis_bm]) - 1`
- `nps`는 지수가 아니라 KOSPI+KOSDAQ150(+LargeCap 전환구간) **지수시총 합계**의 변화율.
- BM 비중: `HWBI.KRX_CONSTITUENT_CLS`의 `INDEX_ADJUSTED_SHARE * PRICE`를 일자별로 합산 정규화.
  `_NXT` 테이블은 차기(next) 구성 기준 → `weight_<bm>_next`.
- **BM 정기변경 선반영** (`bm_pre_rebal=True`): `HWBI.krx_ca`의 Addition/Deletion/Free-float Factor Change/Index Share Change를
  `rebal_end_dt ~ bm_reb_date` 구간에 미리 반영해 `weight_kospi200`/`_next`를 교체하고, BM 수익률도
  해당 구성으로 백테스트해 덮어쓴다 (CELL 10, CELL 39).

## 4. 초과성과(Excess Return) 계산 방식

```
active = total - bm          # 기간 단순수익률 차이 (기하 아님)
```
`return_contribution_final.loc['active'] = .loc['total'] - .loc['bm']`

### 4.1 Scaling factor (Barra 로직 차용, CELL 40)

일별 기여도를 기간 기여도로 환산하기 위한 계수.

```
Alog[col]      = active[col] / (log(1+total[col]) - log(1+bm))      (active≠0)
               = 1 + bm                                             (active==0)

alphalog[d,col] = (log(1+r[d,col]) - log(1+r[d,bm])) / (r[d,col] - r[d,bm])   (r≠rbm)
                = 1 / (1 + r[d,bm])                                           (r==rbm)

betalog = alphalog * Alog        (index=report_date_list, NaN→0)
```

기간 집계 시에는 항상 `betalog[col].shift(-1)`을 곱한다 (당일 weight × 익일 수익률 구조 때문).

## 5. 성과 기여도 계산 방식 (CELL 46~52)

모든 일별 기여도는 **`t`일 active weight(`_next`) × `t+1`일 수익률**이다.

| 항목 | 계산식 |
|---|---|
| `active_contribution_<col>` | `w_next[t] * (forward_return_d[t] - bm_return[t+1])` |
| `market_timing_contribution_<col>` | `w_next[t] * (predictive_beta[t] - bm_pred_beta[t+1]) * bm_return[t+1]` |
| `<factor>_contribution_<col>` (risk 17종) | `w_next[t] * exposure_factor[t] * factor_return[t+1]` |
| `<industry>_contribution_<col>` (industry 21종) | `w_next[t] * exposure_industry[t] * factor_return[t+1]` |
| `country_contribution_<col>` | `w_next[t] * 1 * country_return[t+1]` |
| `specific_contribution_<col>` | `active − market_timing − country − Σ(risk+industry)` |

- `forward_return_d = return_d.groupby('item').shift(-1)`
- `bm_pred_beta[t] = Σ_i weight_<bm>_next[t,i] * predictive_beta[t,i]`
- 마지막 날(`i == len(date_list)-1`)은 0.

### 5.1 기간 집계 (CELL 52)

```
return_contribution_final[item, col]
    = Σ_d ( Σ_i contribution_item[d,i,col] ) * betalog[col].shift(-1)[d]
```
단, `specific`은 **잔차**로 정의한다:
```
specific = active − (market_timing + risk_factor + industry_factor + country)
```

### 5.2 Allocation / Selection (CELL 53)

섹터 BM 수익률:
```
sector_bm[d,s]      = Σ_{i∈s} index_market_cap.bm[d,i]
sector_bm_next[d,s] = Σ_{i∈s} index_market_cap.bm_next[d,i]   → unstack().shift(1).stack()
sector_return[d,s]  = sector_bm[d,s] / sector_bm_next[d,s] − 1
```
```
allocation[col] = Σ_d [ Σ_s ( Σ_{i∈s} w_next[d,i,col] ) * (sector_return − bm_return).shift(-1)[d,s] ] * betalog[col].shift(-1)[d]
selection[col]  = active[col] − allocation[col]

섹터별:
  <col>_allocation[s] = Σ_d ( Σ_{i∈s} w_next[d,i,col] ) * (sector_return − bm_return).shift(-1)[d,s] * betalog[col].shift(-1)[d]
  <col>_selection[s]  = Σ_{i∈s} Σ_d active_contribution[d,i,col] * betalog[col].shift(-1)[d]  −  <col>_allocation[s]
```
섹터 기준은 두 가지:
- `q_sector` (vrksa 기본) → `sector_compare_final`, `allocation`/`selection`
- `new_sector` (= `fics_industry_group27` + 수기 조정 78종목: 2차전지/화장품/빅테크/방산/로봇/은행/카드/맥쿼리)
  → `new_sector_compare_final`, `allocation_new`/`selection_new`

### 5.3 종목별 기여도 (Performance_Analysis_Module CELL 48)

```
stock_contribution[i,col] = Σ_d active_contribution[d,i,col] * betalog[col].shift(-1)[d]
```
`risk_factor`/`industry_factor`를 고르면 해당 팩터군 `_contribution_<col>` 합을 쓴다.
종목코드 → `info_stock['name_stock']` (`FNGDB.dbo.fns_j_mast`)로 매핑.

### 5.4 기여도 추이 (CELL 54) — `compare_final`

```
compare_final[d, '<item>_contribution', col]
   = cumsum_d( Σ_i contribution[d,i,col] * betalog[col].shift(-1)[d] ).shift(1).fillna(0)

active_contribution 행만 예외:
   = cumprod 기반 (누적 total − 누적 bm)

specific_contribution 행 = active − market_timing − country − Σ(risk+industry)   (누적 기준 동일 정의)
```

## 6. 종목별 비중 계산 방식

- DB에 저장된 것은 **active weight**. `total = active + bm`.
- 리밸런싱일 이후는 `jackhammer` RAW 백테스트로 일별 drift.
- 기여도용 active weight는 `_next` (차기 BM 대비).
- 평균비중은 사용처에 따라 `groupby('item')['weight'].mean()` 또는 특정일 `xs(date)`.

## 7. 리밸런싱 처리 방식

- `rebalance_date_list` = `simple_rebalancing_target_weights`에 존재하는 날짜들
  (`mp_start_date='2023-02-13'`이면 전체, 아니면 시작일 직전 리밸일부터).
- `method='RAW'` = score를 그대로 weight로 사용.
- 리밸런싱일 사이에는 `return_d`로 drift.
- **CA(기업행위) 수기 반영**:
  - 인적분할: 거래정지 마지막날 total weight를 분할비율(ratio_1/ratio_2)로 쪼개고 신설법인 행 추가.
    평가가격 대비 상장일 종가로 `return_d`/`forward_return_d` 수기 보정.
    (한화 2026-08, 삼성바이오로직스 2025-11, 한화에어로 2024-09 사례)
  - 편출: 해당일 weight 0 설정 (금양 2025-03-10, 동국제강 2023-06-21)

## 8. 거래비용 / 슬리피지

**존재하지 않는다.** MP/RP 성과분해에는 거래비용·슬리피지가 없다.
펀드 분해(9절)에서만 `other_contribution` 잔차에 거래비용이 포함된다.

## 9. 하위 모델 구조

`Function_calculation_return_contribution_ver2.ipynb` CELL 3에서 결정된다.

```
analysis_bm = 'kospi200' → import_name = 'KS2'
analysis_bm = 'kospi'    → import_name = 'KSP'
```

KS2 (kospi200):
```
RP  = Hanwha_Quant_KS2_RP            ← 상위(실운용) 포트폴리오, 컬럼명 'RP'
 ├ KS2_CONSENSUS_FP
 ├ KS2_DIVIDEND_FP
 ├ KS2_INVESTMENT_FP
 ├ KS2_LTREV_FP
 ├ KS2_NEWIAM_FP
 ├ KS2_PRICEMOMENTUM_FP
 ├ KS2_PROFITABILITY_FP
 ├ KS2_PROFITABILITYGROWTH_FP
 ├ KS2_VALUE_FP
 └ Hanwha_Quant_KS2_MP               ← 하위 FP 합성 모델 포트폴리오
 (KS2_SMALLSIZE_FP 는 현재 주석 처리)
```
KSP (kospi): 위와 동일 + `KSP_LIQUIDITY_FP`, 상위는 `Hanwha_Quant_KSP_MP`.

- 각 하위 모델은 **독립적인 active weight 시계열**이며, 상위 RP는 별도 저장된 weight다.
- 즉 **RP ≠ Σ(하위 FP)** — 합산 관계가 아니라 나란히 비교하는 구조다.
  (`return_contribution_final`의 컬럼이 곧 `mp_list + ['RP']`)
- Aggregation은 존재하지 않고, 모든 모델에 **동일한 분해식을 각각 적용**한다.

### 9.1 펀드 단계 (Function_fund_return_calculation_ver2.ipynb — 미제공)

```
Fund excess return = MP contribution + RP contribution + Manager contribution + Other contribution
```
`other_contribution`: 설정/환매, 우선주 괴리, ETF 괴리, 선물, 배당, 편입비, 거래비용.
Copy Ratio = `1 − Σ|w_a − w_b| / 2`.
→ 이 노트북이 제공되지 않아 **Dashboard 범위에서 제외**했다. 훅 포인트만 남겨둔다.

## 10. 기존 notebook 실행 흐름

```
Performance_Analysis_Module_ver2_.ipynb
  CELL 13  파라미터 설정 (mp_start_date / report_start_date / mp_end_date / analysis_bm / data_load / bm_pre_rebal)
     └ %run 'Function_calculation_return_contribution_ver2.ipynb'
          CELL 2~3    import, DB 연결, mp_list 결정
          CELL 4      mp_start_date 유효성 (go_ahead)
          CELL 5~7    종목명, Barra exposure/가격/지수비중 로드
          CELL 10     BM 정기변경 선반영(옵션)
          CELL 12     new_sector 수기 조정
          CELL 13~22  specific return / pred beta / 지수종가 / factor return / exposure / market / risk
          CELL 25     date list, mp_weight + bm 결합, total weight 생성
          CELL 30~36  CA 수기 반영
          CELL 39     jackhammer 백테스트 → 일별 weight + 일별 수익률
          CELL 40     return_contribution_final 골격 + Alog/alphalog/betalog
          CELL 41~43  factor/beta/specific/covariance 결합
          CELL 46~51  일별·종목별 기여도 (active/market_timing/factor/country/specific)
          CELL 52     기간 집계
          CELL 53     섹터 BM 수익률 → allocation/selection (q_sector, new_sector)
          CELL 54     compare_final 누적 추이
          CELL 57~64  risk profile / correlation / risk contribution  ← **현재 미실행(서버 부하)**
  CELL 14  %run 'Function_get_score_ver1.ipynb'   (alpha score — 주간 성과회의 밖)
  CELL 16~18  비교기간 기준일 SQL
  CELL 21~58  표·그래프 (성과기여도, 항목별/MP별 추이, 종목 Top/Bottom, 섹터 Allocation/Selection)
  CELL 60~77  %run 'Function_fund_return_calculation_ver2.ipynb' + 펀드 화면
```

매주 작업: `report_start_date`(전주 마지막 영업일), `mp_end_date` 수정 → 전체 재실행.

## 11. 현재 notebook이 생성하는 표/그래프

| # | 산출물 | 원천 |
|---|---|---|
| 1 | 성과 기여도 bar + 표 (10항목 × 모델) | `return_contribution_final` |
| 2 | 항목별 기여도 추이 (모델 비교) | `compare_final.xs('<item>_contribution', level=1)` |
| 3 | 항목별 기여도 추이 (단일 모델, 항목 비교) | `compare_final.loc[idx[:, [...]], port]` |
| 4 | Factor / Industry 기여도 추이 + 최신 bar | `compare_final` (list_bpm_factor / list_bpm_sector) |
| 5 | 기간별(WTD/MTD/QTD/HTD/YTD/1Y) 모델 기여도 bar | `final_mp['active_contribution_*']` 앵커별 sum |
| 6 | 업종별 specific 기여도 누적 추이 / bar | `final_mp['specific_contribution_RP']` + `q_sector`/`new_sector` |
| 7 | 종목별 기여도 Top/Bottom 10 (+active weight 보조축) | `compare_contribution_final` |
| 8 | 업종별 Allocation / Selection 표 + bar | `sector_compare_final`, `new_sector_compare_final` |
| 9 | 특정 업종 내 종목 기여도 | `final_mp` 필터링 |
| 10 | 펀드 성과 요약 / Copy Ratio / 종목별 fund·mp·rp 비교 | 펀드 노트북 (미제공) |

## 12. 하드코딩된 경로·날짜·BM·모델명

| 위치 | 내용 |
|---|---|
| `shared_data.py` | MSSQL/Tibero 접속문자열 + 평문 비밀번호 |
| contrib CELL 3 | `mp_list`, `mp_nm`, `import_name` 매핑 |
| contrib CELL 6 | `bpm_factor_name_match` (41개) |
| contrib CELL 12 | `adj_sector` 78종목 수기 섹터 |
| contrib CELL 17 | `list_bpm_factor` 17개 (나머지는 sector) |
| contrib CELL 25 | `mp_start_date == '2023-02-13'` 분기 |
| contrib CELL 30~36 | CA 종목코드·가격·비율, 편출 종목/일자 |
| contrib CELL 18 | `add_date_list = ...[-5:]` (임시 코드) |
| perf CELL 13/60 | 분석기간, `analysis_bm`, `fund_code`, `fund_bm` |
| 여러 곳 | `'A001230'`(동국제강) 제외, `'A380440'` 제외 |
| score 노트북 | `pickle` 경로 `Data/fcm_score_<bm>.pkl` |

→ `config/config.yaml` + `config/corporate_actions.yaml` + `config/sector_overrides.yaml`로 분리했다.

## 13. Dashboard로 이전 가능한 함수 / 리팩토링 필요 지점

### 이전 가능 (순수 pandas/numpy — `src/`로 이관 완료)
- scaling factor (Alog / alphalog / betalog) → `src/performance.py`
- 일별 기여도 6종 → `src/attribution.py`
- 기간 집계·allocation/selection·compare_final → `src/attribution.py`
- 섹터 BM 수익률 → `src/benchmark.py`
- 종목별 weight/active weight/position change → `src/portfolio.py`
- 모델 비교 → `src/model_analysis.py`

### 이전 불가 (사내 라이브러리 필수 — `src/data_loader.py`의 DB 백엔드에 격리)
- `jh.ScoreBasedPortfolio` 일별 drift 및 포트폴리오 수익률
- `vr.load(...)` exposure/가격/섹터
- 모든 SQL

### 리팩토링이 필요했던 지점
1. 3중 `for` 루프(일자×팩터×모델) — **벡터화하지 않고 동일 구조 유지**. 형태를 바꾸면 값이 달라질 위험이 있어 의도적으로 보존했다. (기여도 계산은 이미 계산된 스냅샷을 읽기 때문에 대시보드 응답속도 영향 없음)
2. `if i<len(date_list)+1` (CELL 51) — 항상 참인 조건. 원본 그대로 유지.
3. 전역변수 의존 → 함수 인자로 명시화.
4. 접속정보 평문 → 환경변수(`PM_MSSQL_URL`, `PM_TIBERO_DSN`)로 이동, 기본값은 기존 값 유지.

## 14. 데이터 업데이트 방식

**기존**: 노트북에서 `data_load=True`로 두고 매주 전체 재실행 (DB 직접 조회).

**신규**: 동일한 로드/계산을 `tools/build_snapshot.py`가 수행하고 결과를
`data/processed/snapshot_<YYYYMMDD>/`에 저장한다. Dashboard는 **스냅샷만 읽는다**.

```
data/processed/
    snapshot_20260911/
        manifest.json        # as_of, bm, 모델목록, 기간, 행수, 체크섬
        final_mp.parquet
        temp_return_final.parquet
        betalog_final.parquet
        return_contribution_final.parquet
        compare_final.parquet
        sector_compare_final.parquet
        new_sector_compare_final.parquet
        sector_index_market_cap.parquet
        info_stock.parquet
        rtn_bpm.parquet
        anchors.json
```
- 파일명을 코드에 하드코딩하지 않는다. `manifest.json`의 `as_of`와 디렉터리 mtime으로 최신 스냅샷을 자동 인식한다.
- 캐시 무효화 키 = (스냅샷 경로, mtime, 파일크기).

## 15. 기존 코드와 결과 일치성 검증 방법

1. **Unit test** (`tests/`): 합성 데이터로 각 공식을 노트북 표현식과 직접 대조한다.
   `tests/test_notebook_parity.py`는 노트북 코드를 그대로 옮긴 참조 구현(reference implementation)을
   테스트 안에 두고 `src/` 함수와 비교한다.
2. **실데이터 대조** (`tools/compare_with_notebook.py`): 노트북을 평소대로 실행한 뒤
   같은 커널에서 `compare_with_notebook.compare(globals())`를 호출하면
   `return_contribution_final`, `temp_return_final`, `compare_final`,
   `sector_compare_final`, 종목별 기여도를 스냅샷 기반 엔진 결과와 비교해
   `Notebook / Dashboard / Difference` 표를 출력한다. 허용오차 `1e-12` (부동소수점만).
3. **Dashboard 화면** (`pages/8_Parity_Check.py`): 위 비교 결과 CSV를 업로드하면 화면에서 확인 가능.
