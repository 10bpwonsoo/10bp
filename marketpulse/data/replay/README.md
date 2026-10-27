# 로컬 CSV 리플레이 — 넣을 수 있는 데이터 목록

여기 `<instrument_id>.csv` 를 넣으면 해당 종목은 이 파일에서 읽는다.
`sources.yaml` 을 고칠 필요가 없다 — 파일이 있으면 자동으로 **마지막 후보**로
붙고, 네트워크 공급자가 전부 실패하면 여기로 떨어진다.

넣을 수 있는 것은 **45종목**이다. 50종목 중 파생 5개(`CURVE_2S10S`,
`COPPER_GOLD`, `CYC_DEF`, `VIX_RV_SPX`, `VKOSPI_RV_KOSPI`)는 기초 자산에서
계산되므로 넣으면 안 된다.

---

## 형식

```csv
date,close
2026-01-02,4.21
2026-01-03,4.26
```

파일 이름은 `<instrument_id>.csv` 다. 대소문자를 정확히 맞춘다 (`US10Y.csv`).

**받아들이는 열 이름** — 내려받은 파일을 그대로 넣을 수 있게 넓게 받는다.

| 역할 | 인정하는 이름 |
|---|---|
| 날짜 | `date` · `observation_date` · `일자` · `날짜` · `datetime` · `time` |
| 값 | `close` · `adj close` · `value` · `price` · `last` · `settle` · `종가` · `수정종가` · `값` · `현재가` |

열이 **둘뿐이면** 두 번째를 값으로 본다. FRED 의 `observation_date,DGS10`
이 그대로 들어간다. 열이 여럿인데 알려진 이름이 없으면 **거부한다** —
짐작해서 고르면 Open 을 종가로 읽는 사고가 난다.

**값 표기** — 자릿수 쉼표(`"1,380.5"`), 퍼센트 기호(`4.21%`) 는 알아서 뗀다.
FRED 의 휴일 표기 `.` 와 `-`, `N/A` 는 **결측**으로 건너뛴다. 0 으로
읽지 않는다 — 금리가 4.21 에서 0 으로 떨어진 것이 되면 z-score 가 폭발한다.

**날짜 형식** `YYYY-MM-DD` · `YYYYMMDD` · `YYYY-MM-DDTHH:MM:SS` ·
`DD-MM-YYYY` · `MM/DD/YYYY`

**인코딩** UTF-8, UTF-8 BOM, CP949, EUC-KR. KRX·네이버에서 받은 파일은
대개 CP949 라 그대로 넣으면 된다.

**최소 20행.** 그보다 짧으면 z-score 의 분모가 잡음이라 거부한다.
60행(약 3개월) 이상을 권한다 — `zscore_window` 기본값이 60이다.

---

## 1순위 — CSV 말고는 방법이 없다 (3종목)

무료 API 가 아예 없다. 종목 전체를 훑어야 나오는 값이라 개별 시세
API 로는 만들 수 없다. `sources.yaml` 에 **빈 목록으로 명시**해 두었다 —
설정에서 빠진 것과 "받을 곳이 없다" 는 다르다.

| id | 내용 | 단위 | 예시값 | 쓰는 곳 |
|---|---|---|---|---|
| `KOSPI_ADV_RATIO` | KOSPI 상승종목 비율 | 비율 **0~1** | `0.54` | KoreaBreadth factor |
| `KOSPI_NHNL` | KOSPI 신고가−신저가 | 종목 수 (차이) | `-41` | KoreaBreadth factor |
| `SPX_ADV_RATIO` | S&P500 상승종목 비율 | 비율 **0~1** | `0.63` | (직접 factor 없음) |

**받는 곳**
- KOSPI 계열 — KRX 정보데이터시스템 `data.krx.co.kr` → 통계 → 주식 →
  등락종목수 / 신고가·신저가. 화면마다 CSV·엑셀 내려받기 버튼이 있다.
- `KOSPI_NHNL` 은 **신고가 수 − 신저가 수** 를 직접 빼서 넣는다.
- `SPX_ADV_RATIO` 는 무료 경로가 사실상 없다. 유료 데이터거나 직접
  계산해야 한다. **비워 두어도 된다** — 빠지면 그만큼 coverage 가
  떨어질 뿐 다른 값이 오염되지 않는다.

> 비율을 `54` 로 넣으면 안 된다. `0.54` 다.

---

## 2순위 — KRX 포털만 있고 불안정하다 (8종목)

`krx` 공급자를 붙여 두었지만 공개 API 계약이 아니라 언제든 바뀔 수 있다.
CSV 를 넣어 두면 그 위험이 사라진다. **수급 4종목이 특히 중요하다** —
요구 5 의 Theme Flow Momentum 과 요구 7 의 가격↔수급 괴리가 여기 의존한다.

| id | 내용 | 단위 | 예시값 |
|---|---|---|---|
| `KR_FOREIGN_NET` | 외국인 순매수 | **십억원** | `-160.74` |
| `KR_INSTITUTION_NET` | 기관 순매수 | **십억원** | `271.19` |
| `KR_RETAIL_NET` | 개인 순매수 | **십억원** | `-110.45` |
| `KR_TRADING_VALUE` | 거래대금 | **십억원** | `11944.50` |
| `KR3Y` | 국고채 3년 | 퍼센트 | `3.00` |
| `KR10Y` | 국고채 10년 | 퍼센트 | `3.28` |
| `VKOSPI` | V-KOSPI | 지수 | `16.45` |
| `KRX_SEMI` | KRX 반도체 지수 | 지수 | `4123.10` |

**받는 곳**
- 수급 4종목 — KRX 정보데이터시스템 → 통계 → 주식 → 투자자별 거래실적.
  **단위 변환이 필요하다.** KRX 는 원 또는 백만원 단위로 준다.
  백만원이면 1000 으로, 원이면 10억으로 나눠 십억원으로 맞춘다.
- `KR3Y` · `KR10Y` — 한국은행 ECOS(`ecos.bok.or.kr`) 또는 금융투자협회
  채권정보센터(`bond.kofiabond.or.kr`). 둘 다 CSV 내려받기가 있다.
- `VKOSPI` · `KRX_SEMI` — KRX 정보데이터시스템 → 지수.

> 수급을 0 으로 채우지 마라. 빠지면 missing 이고 KoreaFlow factor 의
> 가중치가 재정규화된다. 0 을 넣으면 **"수급이 중립이다"** 라는 없는
> 주장이 만들어지고, 그 위에서 괴리 판정이 돈다.

---

## 3순위 — 네트워크가 막혔을 때만 (34종목)

Yahoo·stooq·FRED 가 닿으면 자동으로 받는다. 막힌 환경에서만 CSV 가
필요하다. `python -m marketpulse.cli probe --mode DELAYED` 로 무엇이
실패하는지 먼저 확인하고, 실패한 것만 채우면 된다.

### 금리 · 크레딧 — FRED (10종목)

`fred.stlouisfed.org/series/<ID>` → Download → CSV. 받은 파일을 이름만
바꿔 그대로 넣으면 된다.

| id | FRED ID | 단위 | 예시값 | 주의 |
|---|---|---|---|---|
| `US2Y` | `DGS2` | 퍼센트 | `4.31` | |
| `US5Y` | `DGS5` | 퍼센트 | `4.05` | Yahoo `^FVX` 도 됨 |
| `US10Y` | `DGS10` | 퍼센트 | `4.21` | |
| `US30Y` | `DGS30` | 퍼센트 | `4.48` | |
| `BE10Y` | `T10YIE` | 퍼센트 | `2.34` | 대체 공급자 없음 |
| `BE5Y` | `T5YIE` | 퍼센트 | `2.33` | 대체 공급자 없음 |
| `TIPS10Y` | `DFII10` | 퍼센트 | `2.61` | 10년 실질금리(TIPS). 명목 분해의 실측 대조 |
| `TIPS5Y` | `DFII5` | 퍼센트 | `2.30` | 5년 실질금리(TIPS) |
| `US_HY_OAS` | `BAMLH0A0HYM2` | **bp** | `298` | **×100 필요** |
| `VIX` | `VIXCLS` | 지수 | `16.4` | Yahoo `^VIX` 도 됨 |

> **`US_HY_OAS` 는 단위가 다르다.** FRED 는 퍼센트(`2.98`)로 주는데 이
> 시스템은 bp(`298`)를 쓴다. 네트워크 경로는 `sources.yaml` 의
> `scale: 100` 이 자동으로 처리하지만 **CSV 에는 scale 이 적용되지
> 않는다.** 파일에 100 을 곱해서 넣어야 한다.
>
> 금리 3종목은 `4.21` 이지 `0.0421` 이 아니다.

### 원자재 (5종목)

| id | 내용 | Yahoo | FRED 대안 | 예시값 |
|---|---|---|---|---|
| `WTI` | WTI 원유 | `CL=F` | `DCOILWTICO` | `72.41` |
| `BRENT` | 브렌트 원유 | `BZ=F` | `DCOILBRENTEU` | `76.18` |
| `GOLD` | 금 | `GC=F` | – | `2640.5` |
| `COPPER` | 구리 | `HG=F` | – | `4.12` |
| `NATGAS` | 천연가스 | `NG=F` | `DHHNGSP` | `2.85` |

### 지수 · 업종 ETF (17종목)

Yahoo Finance `finance.yahoo.com/quote/<심볼>/history` → Download.
막혀 있으면 stooq `stooq.com/q/d/?s=<심볼>` 의 CSV 링크.

| id | Yahoo | stooq | | id | Yahoo | stooq |
|---|---|---|---|---|---|---|
| `KOSPI` | `^KS11` | `^kospi` | | `XLK` | `XLK` | `xlk.us` |
| `KOSPI200` | `^KS200` | – | | `XLE` | `XLE` | `xle.us` |
| `KOSDAQ` | `^KQ11` | – | | `XLF` | `XLF` | `xlf.us` |
| `SPX` | `^GSPC` | `^spx` | | `XLU` | `XLU` | `xlu.us` |
| `NDX` | `^NDX` | `^ndq` | | `XLY` | `XLY` | `xly.us` |
| `RUT` | `^RUT` | – | | `SOXX` | `SOXX` | `soxx.us` |
| `HSCEI` | `^HSCE` | – | | `ITA` | `ITA` | `ita.us` |
| `NIKKEI` | `^N225` | `^nkx` | | `JETS` | `JETS` | `jets.us` |
| `SX5E` | `^STOXX50E` | – | | | | |

지수는 지수값(`2540.10`), ETF 는 주가(`58.44`) 를 넣는다. 배당·분할
조정 종가(`Adj Close`)가 있으면 그쪽이 수익률 계산에 맞다.

### FX (5종목)

| id | Yahoo | stooq | 예시값 |
|---|---|---|---|
| `USDKRW` | `KRW=X` | – | `1380.5` |
| `DXY` | `DX-Y.NYB` | `^dxy` | `106.2` |
| `USDJPY` | `JPY=X` | `usdjpy` | `154.3` |
| `EURUSD` | `EURUSD=X` | `eurusd` | `1.0421` |
| `USDCNH` | `CNH=X` | – | `7.29` |

### 변동성 (1종목)

| id | Yahoo | 예시값 |
|---|---|---|
| `MOVE` | `^MOVE` | `92.4` |

---

## 넣으면 안 되는 것 (5종목)

| id | 계산식 |
|---|---|
| `CURVE_2S10S` | `US10Y − US2Y` |
| `COPPER_GOLD` | `COPPER ÷ GOLD` |
| `CYC_DEF` | `XLY ÷ XLU` (경기민감/방어) |
| `VIX_RV_SPX` | `VIX − SPX 의 20일 실현변동성(연율 %)` |
| `VKOSPI_RV_KOSPI` | `VKOSPI − KOSPI 의 20일 실현변동성(연율 %)` |

기초 자산에서 자동 계산된다. 따로 넣으면 두 값이 어긋나고, 그 어긋남이
Growth factor 로 그대로 들어간다. `sources.yaml` 에도 공급자가 없고
테스트로 고정해 두었다.

---

## 확인

```bash
# 전체
python -m marketpulse.cli probe --mode DELAYED

# 넣은 것만
python -m marketpulse.cli probe --mode DELAYED --only US10Y,KR_FOREIGN_NET -v
```

성공하면 `csv:US10Y · 60개` 처럼 공급자와 행 수가 나온다. 실패하면
이유가 나온다 — 열 이름이 틀렸는지, 행이 모자란지, 파일이 없는지.

화면에서도 종목별 출처를 볼 수 있다. `DataMeta.source` 가 `csv:US10Y` 로
찍히므로 어느 값이 파일에서 왔는지 숨지 않는다.

---

## 최소 구성

50종목을 다 채울 필요는 없다. 빠진 것은 **missing** 이고 그만큼
coverage 와 confidence 가 떨어질 뿐, 다른 값이 오염되지 않는다.

핵심 화면이 돌아가려면 이 정도면 된다.

```
SPX  NDX  KOSPI  VIX  US2Y  US10Y  DXY  USDKRW  BRENT  GOLD  COPPER
KR_FOREIGN_NET
```

11개 가격 + 수급 1개. 여기에 `BE10Y` 와 `US_HY_OAS` 를 더하면 Inflation·
Credit factor 까지 살아난다.

---

## 메모리 가격 — 수집기가 채우는 파일 (2026-09-29)

`python -m marketpulse.scripts.collect_memory_prices` 가 여기에 여섯 파일을 쓴다.

| 파일 | 출처 | 주기 | 비고 |
|---|---|---|---|
| `DRAM_SPOT.csv` `DDR5_SPOT.csv` `NAND_SPOT.csv` `DXI.csv` | dramexchange.com 홈 표(세션 평균)·DXI | 하루 한 줄 | 공개 이력이 없어 **수집을 시작한 날부터** 쌓인다. z 는 20봉이 차면 나온다 |
| `HBM3E_CONTRACT.csv` `HBM4_CONTRACT.csv` | Silicon Analysts 무료 API(← TrendForce·언론 보도) | 분기·비정기 앵커 | 현물이 아니라 **계약가 추정치**. 출처·신뢰도·유형 열을 같이 남긴다. z 는 계산하지 않는다 |

여섯 항목은 `universe.yaml` 에 `min_points: 1` 이라 봉 하나여도 값·변화는 화면에 보인다.
HBM 둘은 `frequency: quarterly` 라 화면에 '분기 추정' 표식이 붙고 방향 계산에 들어가지 않는다.
DRAMeXchange 표는 개인 참고 용도로 읽는 것이라 이 CSV 를 다른 곳에 재배포하지 않는다.
