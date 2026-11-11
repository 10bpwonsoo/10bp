# Market Pulse AI — 세션 작업 정리 (2026-09-16)

브랜치 `claude/market-pulse-ai-design-r7pmsm`, 커밋 34개 (전부 푸시됨), 백엔드 테스트 618건 + 프런트 렌더 테스트 23건 통과.
배포본: 대시보드 https://claude.ai/code/artifact/1211f267-bc03-4151-8278-0da629aca833 (Version 23, 2026-09-22 종가),
화면 판독 가이드 https://claude.ai/code/artifact/fd6cd140-aae5-4b29-b7e7-53a088790c1e (Version 17).

> 2026-09-16 후반에 **Investment Intelligence** 층이 기존 대시보드 아래에 추가됐다 — 5절.

---

## 1. 구현한 기능 목록

### P0~P2 (기반)
- 데이터 계약: pydantic 모델 전부에 출처·모드·신선도 메타(`DataMeta`)와 계산 근거(`ScoreBreakdown`) 강제.
- MOCK 파이프라인: 시나리오 JSON에 "체제 + 충격(σ)"만 적으면 시드 고정 합성 시계열 생성. 충격값이 z-score로 정확히 재현됨.
- FeatureEngine: rolling z (기준선에서 현재값 제외), 결측은 None (0 아님).
- FactorEngine 11개 (Growth·Inflation·Rates·USD·Liquidity·RiskAppetite·Credit·Volatility·China·KoreaFlow·KoreaBreadth), 결측 시 가중치 재정규화.
- MarketStateEngine: require + support 2단 룰, 8개 상태 라벨, Confidence = 분리도·확인·커버리지·지속성.
- ThemeEngine 13개 테마 × 뉴스·가격·변동성, Cross-asset 확인, 안정성.
- SentimentEngine: 사전 기반 룰 태깅, 시간감쇠·영향도·출처 가중.
- DivergenceEngine: opposing / unresponsive 두 형태, 2틱 지속 조건, severity = tanh(gap)·지속·중요도.
- AlertEngine: 수준이 아니라 직전 틱 대비 변화, dedupe·쿨다운·보존창.
- SQLite 저장소, 스케줄러, FastAPI 단일 스냅샷 엔드포인트, WebSocket 스트림.
- React 대시보드 9개 패널, 토큰 기반 CSS, 폰 대응.

### P3~P4 (LLM · 실데이터)
- Impact Map: 사건→테마→매크로→업종→자산 BFS, 전파 단계 열 배치, 예상 부호 vs 실측 반응.
- LLM 이벤트 추출·검증·요약, 실패 시 룰·템플릿으로 자동 대체 (LLM 없이도 전 화면 동작).
- LLM 웹검색 어댑터 (`web_search_20260209`), RSS 0건일 때만 검색.
- 실데이터 어댑터: Yahoo·Stooq·FRED·KRX·GitHub 미러·로컬 CSV 우선순위 폴백. 종목별 실패 사유가 화면에 남음.
- 백테스트: 과거 재생으로 신호 채점, look-ahead 제거.
- 실데이터 오류 수정: ^TNX 스케일, US2Y 심볼, 파생 시계열 날짜 정렬, CNH 심볼.

### P5 이후 (세션 후반)
- 센티멘트 온도계: 가격 온도·뉴스 온도·종합, 격차 30 이상이면 내러티브 괴리 표시.
- 수기 태깅 경로: API 크레딧 없이 Claude가 기사를 읽고 `extractor="manual"`로 정직하게 표시. 3차례 캡처.
- 수급 신호 off (`theme.use_flow: false`), 뉴스 감성이 그 자리를 흡수. 히트맵 행 클릭 시 관련 기사 4건, 원문 링크.
- GOAL Kickstart 차용 8종:
  1. 장기 백분위 + 3개월 변화 (What's Moving, Main Drivers)
  2. 재료 스트립 (온도계 아래, ● 현재 / ◇ 1주 전)
  3. 1주 전 표식 (온도계 ◇, 히트맵 Δ1w, What's Moving 막대 ◇)
  4. 상관 레짐 대조 — 사전 정의 관계를 60일 상관으로 확인/약화/뒤집힘, `CORRELATION_REGIME` 괴리
  5. 지배 축 — |z| 최대 후보와 ±0.3 이상 연동 자산
  6. 이벤트 달력 — 중앙은행 회의 D-2 안이면 지속성 ×0.5, 알림 임계 ×1.25
  7. 변동성 프리미엄 파생 종목 (VIX − S&P 실현변동성)
  8. 경기민감/방어 파생 종목 (XLY ÷ XLU)
- 뉴스 판단 배지 3상태 (없음 / 수기 / API), '지금 업데이트' 버튼 (`?refresh=true`로 TTL 캐시 우회).

---

## 2. 디렉터리 구조 (3단계)

```
10bp/
├── README.md · pyproject.toml · requirements*.txt · .env.example · conftest.py
├── docs/
│   ├── 00-analysis-and-architecture.md      설계서
│   └── 01-session-summary-2026-09-16.md     이 문서
├── marketpulse/                             백엔드 패키지
│   ├── adapters/
│   │   ├── market/   live.py · mock.py · providers.py · scenario.py · synthetic.py
│   │   ├── news/     rss.py · llm_search.py · mock.py
│   │   └── base.py · http.py · registry.py
│   ├── ai/           client.py · event_extractor.py · rule_extractor.py · summarizer.py · validation.py
│   ├── analysis/     backtest.py
│   ├── api/
│   │   ├── routes/   snapshot.py · signals.py · graph.py · news.py · health.py · stream.py
│   │   └── deps.py · main.py
│   ├── config/       settings.py · registry.py
│   │                 instruments · factors · state_rules · themes · lexicon · relationships
│   │                 divergence_rules · scoring · sources · feeds · calendar  (.yaml 11개)
│   ├── data/
│   │   ├── captures/ 2026-09-14-llm · 2026-09-15-llm · 2026-09-15-llm-3
│   │   │             2026-09-15-manual · 2026-09-15-manual-2 · 2026-09-16-manual
│   │   ├── mock/     scenario_{baseline,inflation_shock,ai_divergence,ai_sentiment}.json
│   │   └── replay/   README.md (CSV 적재 안내)
│   ├── engines/      features · normalize · factors · market_state · confirmation · sentiment
│   │                 theme · direction · divergence · alert · relationship · thermometer
│   │                 correlation · calendar · scoring · korean · orchestrator
│   ├── models/       common · market · news · state · theme · divergence · alert
│   │                 relationship · thermometer · correlation · calendar · snapshot
│   ├── scheduler/    runner.py
│   ├── storage/      repository.py · sqlite_repo.py · schema.sql
│   ├── vendor/       indicators.py
│   └── cli.py
├── frontend/
│   ├── src/
│   │   ├── api/         client.ts · types.ts · useSnapshot.ts
│   │   ├── components/  AlertTimeline · ConfirmationMatrix · DataHealthPanel · DataModeBadge
│   │   │                DivergencePanel · ImpactMap · MarketStateHeader · NewsFeed · Panel
│   │   │                RefreshButton · RuleTrace · ScenarioSwitcher · ScoreTooltip
│   │   │                SentimentGauge · SignalBar · ThemeHeatmap · WhatsMoving  (.tsx 17개)
│   │   ├── layout/      DashboardGrid.tsx
│   │   ├── theme/       tokens.css · layout.css
│   │   └── App.tsx · main.tsx
│   └── index.html · vite.config.ts · package.json
├── tests/            conftest.py · flowera.py · fixtures/ · test_*.py 20개
└── upbit_trading/    기존 코드 (건드리지 않음)
```

---

## 3. 핵심 컴포넌트와 역할

파이프라인 순서 — `run_pipeline_detailed()`가 I/O를 하고 `build_intelligence()`는 순수 함수다.
어댑터 → 정규화 → 이벤트 추출 → 시장 상태 → 테마 → 괴리 → Impact Map → 요약 → 온도계 → 알림 → 스냅샷.

### 백엔드

| 계층 | 파일 | 역할 |
|---|---|---|
| 어댑터 | `adapters/market/live.py` | sources.yaml 순서로 공급자 시도, 파생 종목(ratio·spread·vol_premium) 계산, 실패 사유 기록 |
| | `adapters/market/synthetic.py` | 시나리오의 σ 충격을 정확히 재현하는 결정론 시계열 |
| | `adapters/news/rss.py` · `llm_search.py` | RSS 수집, RSS가 비면 LLM 웹검색으로 대체 |
| 정규화 | `engines/features.py` | z_1d/5d/20d, 1주 전 z, 3개월 변화, 백분위(실제 봉 수 동반), 실현변동성 |
| | `engines/correlation.py` | 60일 변화량 상관 행렬 + 한 분기 전 창. 날짜로 정렬 |
| 판정 | `engines/factors.py` | 부호·가중 z 평균, 결측 재정규화, 품질 등급 |
| | `engines/market_state.py` | 룰 채점, Confidence, Main Drivers, 지배 축 |
| | `engines/theme.py` · `sentiment.py` | 테마 점수, 뉴스 감성(감쇠·영향도·출처) |
| | `engines/thermometer.py` | 가격·뉴스·종합 온도, 재료 스트립, 1주 전 |
| 괴리 | `engines/divergence.py` | 테마쌍·자산쌍·상태vs변동성·테마vs자산·상관 레짐 5갈래, 2틱 지속 |
| | `engines/relationship.py` | Impact Map BFS, 예상 부호 전파, 실측 상관으로 관계 대조 |
| | `engines/alert.py` | 변화 기반 알림, 이벤트 창에서 임계 ×1.25 |
| | `engines/calendar.py` | 중앙은행 일정 창 판정, 지속성·알림 배율 |
| AI | `ai/client.py` | Anthropic 클라이언트, 서킷 브레이커, 실패 사유 기록 |
| | `ai/rule_extractor.py` | LLM 없을 때의 사전 기반 태깅 |
| 서비스 | `api/deps.py` | TTL 캐시, 히스토리 12틱, 1주 전 스냅샷 조회, `force` 갱신 |
| | `storage/sqlite_repo.py` | 스냅샷 저장, `at_or_before()` |
| 설정 | `config/scoring.yaml` | 모든 가중치·임계값. 코드에 숫자 없음 |
| | `config/calendar.yaml` | 회의 일정, `verified` 플래그 |

### 프론트엔드

| 컴포넌트 | 역할 |
|---|---|
| `MarketStateHeader` | 판정·Confidence·Main Drivers(백분위·◇1주 전)·지배 축·이벤트 창 배지 |
| `SentimentGauge` | 온도계 SVG(세 바늘 + 1주 전 표식) + 재료 스트립 |
| `ThemeHeatmap` | 테마 행(Score·Δ1w·News·Price·Conf), 클릭 시 관련 기사 |
| `WhatsMoving` | z 순 변수, %ile·3개월·막대 위 ◇ |
| `ImpactMap` | 지도/목록 보기, 상관 미확인 관계 점선, 단계별 실측 점도표 |
| `DivergencePanel` · `AlertTimeline` · `ConfirmationMatrix` · `NewsFeed` · `DataHealthPanel` | 각 패널 |
| `DataModeBadge` · `RefreshButton` | 모드·신선도·커버리지·뉴스 판단 3상태, 지금 업데이트 |
| `ScoreTooltip` · `RuleTrace` | 모든 점수의 계산 근거, 발동 룰 |

---

## 4. 마지막 작업과 남은 TODO

### 마지막 작업 (커밋 `6cc7962`)
9/16 02:05 UTC 기준 실데이터 3차 수기 캡처. 시장 35/50 종목, RSS 78건 중 31건 + 해외 12건 수기 태깅.
판정 없음 29%, 온도계 −9, 지배 축 USD/JPY, FOMC D-day 이벤트 창, 괴리 3건(상관 레짐 2 + Rates 뉴스↔가격).

### 남은 TODO
- **API 크레딧** — Anthropic 계정 잔액 0. 키는 `MARKETPULSE_ANTHROPIC_API_KEY`로 이미 들어가 있어 크레딧만 채우면 `뉴스 판단 API`로 자동 전환.
- **데이터 공백 15종목** — KRX 8종(국고채·V-KOSPI·KRX반도체·수급 4종)은 포털이 세션을 거부. FRED 2종(BE10Y·US_HY_OAS)은 `FRED_API_KEY` 필요. 시장폭 3종은 무료 공급자 없음. KOSPI200은 오늘 Yahoo 일시 실패.
- **1주 전 표식의 뉴스·종합 부분** — 서버를 1주일 이상 돌려 저장 스냅샷이 쌓여야 채워짐. 지금 배포본은 `–`.
- **달력 날짜 검증** — 이번 주 3건만 1차 출처 확인. 나머지 `verified: false`는 `(미확인)` 표시 중.
- **추가 탭 제안 (미착수)** — 중앙은행 주간·지정학 충격·유동성 경색·성장 충격·가짜 Risk-On 시나리오, 1주 전 비교·리플레이·수기 vs 룰 보기.
- **GOAL 9번(내러티브 골격)** — 요청대로 미반영.
- **설계상 미해결** — 얇은 데이터에서 Confidence 과신 문제(승인 요청 ④), 가이드 A절에 기록.
- **수기 태깅 갱신** — 자동이 아니므로 새 기사 반영은 매번 요청 필요.

---

## 5. Investment Intelligence (2026-09-16 후반 추가)

기존 대시보드·엔진·API·컴포넌트는 그대로 두고 그 **아래**에 두 번째 층을 붙였다.
사슬 MARKET → ALTERNATIVE DATA → INDUSTRY → STOCK → PRICE/FLOW → FUNDAMENTAL → ANALYST → CLAUDE.

### 구현
- 설정: `config/universe.yaml` (36종목·41대체지표, 종목별 aliases), `config/stock_exposures.yaml` (사업 노출), `config/intelligence.yaml` (모든 임계·가중치).
- 엔진 13개: `stock_features` `stock_exposure` (20/60/120일 beta·상관) `stock_impact` (충격×노출×통계신뢰×사업관련성×현재관련성) `stock_anomaly` (뉴스 없는 거래량 급증 = UNEXPLAINED_ACTIVITY, '매집' 금지) `alternative_data` (MISSING/STALE/롤오버 의심 + 다음 봉 확인) `commodity_impact` `analyst` (CSV 만) `lead_lag` ("앞서는 경향" 까지) `stock_explanation` (원인 6종 × 확신 3단) `stock_divergence` `semiconductor` `commentary` (수기 JSON, API 아님) `investment` (오케스트레이터).
- 어댑터: `AltLiveAdapter` (Yahoo 차트 + CSV, `alt_daily` 일별 upsert, 같은 날 재사용, 실패 시 STALE), `AltMockAdapter` (시나리오 shocks·volume_shocks·analyst).
- API: `/api/v1/investment`, `/investment/stocks/{id}`, `/investment/alternative?group=`. 별도 캐시(MOCK 4초 / DELAYED 15분).
- 프런트: 12패널 + Investment Data Health, `InvestmentSection` 이 `DashboardGrid` 바로 아래.
- MOCK 시나리오 6개 추가: commodity_shock, memory_upcycle, oil_spike, china_stress, rates_stock_divergence, eps_price_divergence.
- 테스트: `tests/test_investment.py` 66건, `frontend/src/__tests__/investment.test.tsx` 23건 (vitest + Testing Library; App 렌더에서 기존 9패널이 먼저, 12패널이 뒤에 오는지 확인).

### 실데이터 (2026-09-16 07:26 UTC 캡처, `data/captures/2026-09-16-manual/investment.json`)
종목 36/36, 대체데이터 31/41. CSI 300 은 본토 지수가 막혀 ASHR ETF 로 대체(source 에 표기).
못 받은 것: DRAM·DDR5·NAND·DXI 현물, 석탄·니켈·아연·나프타, SCFI, 중국 PMI, 외국인·기관 수급(KRX), 애널리스트 컨센서스.
모두 화면에 '없음' 으로 남기고 CSV 슬롯(`data/replay/alternative/`, `data/replay/analyst/`)만 열어 뒀다.
수기 해설 `data/commentary/2026-09-16.json` — 시장 1 · 종목 6 · 대체데이터 2, FACT/NEWS/ANALYST/INTERPRETATION/UNKNOWN 분리.

### 후속 조치 (같은 날)
- NEW_EVENT 배지: 테마 태그만으로는 켜지지 않고 종목을 직접 지목한(entity·affected_assets·제목/요약의 종목명·alias) 기사만 센다 — 전에는 20줄 전부에 붙어 정보가 없었다.
- 롤오버 의심의 다음 봉 판정: 직전 실행의 의심 계열이 새 봉에서 되돌리면 `reverted`(일회성), 이어지면 `persisted`(실제 충격인지 롤오버 단차인지는 가리지 못한다고 적는다) 를 note 에 남긴다.
- 프런트 렌더 테스트 도입 (`npm test`).

### 2026-09-18 갱신 (4차 수기 캡처, `data/captures/2026-09-18-manual/`)
- 시장 봉은 9/17 종가까지(9/18 장중 봉 제외), 기준 시각은 수집 시각 9/18 01:13 UTC. 시장 35/50, RSS 80건 + 해외검색 10건 중 43건 수기 태깅.
- 판정 Risk-On 88%(VIX −2.2σ, S&P +1.6σ, 나스닥 +1.4σ), 온도계 +42(가격 +59 / 뉴스 +16), 괴리 6건(상관 레짐 2 + 뉴스↔가격 4), 알림 10건.
- Investment Intelligence: 종목 36/36, 대체 31/41. 드라이버 6(DXY·VIX·USD/KRW·US10Y·SPX·MOVE), Impact 는 USD/KRW 경유 5건. 9/16 롤오버 의심(휘발유·난방유)은 이번 수집에서 같은 봉이 +0.6%/−0.3% 로 **수정**돼 왔다(확정 전 값) — 저장 봉 수정 감지(`AltLiveAdapter.revisions`)를 추가해 Data Health 경고로 올린다. 수기 해설 시장 1 · 종목 7 · 대체 2.
- 데이터 주의: Yahoo 가 ^KS11·BZ=F·HG=F·KRW=X 의 9/17 일봉을 주지 않아 그 계열은 9/16 이 마지막이고 종목 상대 z 는 전부 결측.
- 롤오버 후속: 다음 봉 판정은 날짜로 비교(저장소는 날짜만 남긴다). `persisted` 문구는 "실제 충격인지 월물 단차인지는 가리지 못한다" 로 — 단차도 되돌리지 않기 때문.

### 2026-09-23 — Market State 한 달 히스토리
- `models/state_history.py` `engines/state_history.py`: 같은 시계열을 날짜별로 잘라 같은 엔진으로 재생. 22거래일, 마지막 점은 as_of 절단(화면과 동일). 온도계(종합·가격·뉴스·재료)까지 같은 식으로 재생 — 뉴스는 그 시점까지 캡처된 기사로만.
- `PipelineResult.series_by_id` 로 원시 시계열을 넘기고, `StateHistoryService` 가 as_of 별로 캐시. `GET /api/v1/market-state/history`. 스냅샷은 그대로.
- 프런트 `StateHistoryStrip` (Market State 패널 안, 주도 변수 아래): 종합·가격·뉴스 온도 선 + 판정 확신 기둥(보조지표) + 라벨 띠, 온도계 재료 여섯 항목의 날짜별 히트맵, 요약·구간 목록. 정적 배포본은 뷰별 재생 JSON 을 shim 이 돌려준다.
- 테스트 +9(백엔드) +5(프런트). 실데이터 9/17 종가 기준: 판정 없음 16일 · Risk-On 3일 · Policy Driven 1 · Risk-Off 1 · Liquidity Stress 1, 전환 9회, 현재 Risk-On 1일째.

### 2026-09-23 갱신 (5차 수기 캡처, `data/captures/2026-09-23-manual/`)
- 기준 시각 9/23 01:06 UTC(10:06 KST 장중) — 한국·아시아 봉은 장중값, 미국·유럽은 9/22 종가. 시장 36/50(코스피200은 Yahoo 429 뒤 단독 재시도로 확보), RSS 80건 + 해외검색 9건 중 40건 수기 태깅. 모의 탭 5개도 같은 시각으로 재생성(`regen_mock_views.py`).
- 판정 없음 36%(유가 급락·칩 랠리·에너지 급락이 같은 날), 온도계 +23(가격 +28 / 뉴스 +16), 괴리 4건, 알림 5건.
- Investment Intelligence: 드라이버 6(WTI·브렌트·천연가스·CSI300·USD/KRW·항셍), 이상 거동 대한항공(+3.5σ, 거래량 +2.7σ, NEWS_DRIVEN_MOVE), 괴리 4건, 반도체 peer·국내 모두 상승 합의. 설탕·면화·커피 저장 봉 수정 경고가 처음 실제로 떴다.
- 히스토리: 9/17 Risk-On → 9/18 Liquidity Stress → 9/21 Risk-On → 9/22 판정 없음. 종합 온도 나흘 연속 양수(이 달 처음). 뉴스 온도는 병합 이벤트로 9/8~9/22.
- 수기 해설 `data/commentary/2026-09-23.json`: 시장 1 · 종목 5 · 대체 3.
- 히스토리에 **공포·탐욕(온도계 밴드)** 기준을 추가: `StateHistoryPoint.band/band_label`, `BandSegment`, `days_by_band` · `band_labels` · `band_changes` · `current_band_streak` · `previous_band` · `band_summary`. 색은 `--band-*` 토큰(청 → 회 → 적). 1차 분류는 뷰별(`historyPrimaryFor`): 실데이터·물가 충격 등은 판정 라벨 그대로, AI 센티멘트 뷰만 공포·탐욕. 다른 쪽은 보조 줄. 라이브 공포·탐욕: 중립 10 · 온기 6 · 냉각 6, 밴드 전환 12회, 현재 온기 2일째.

### 2026-09-28 갱신 (6차 수기 캡처, `data/captures/2026-09-28-manual/`)
- 기준 시각 9/28 07:24 UTC(16:24 KST) — 한국·아시아 봉은 9/28 종가, 미국·유럽은 9/25 종가(추석 연휴 9/24~27 로 국내 나흘 휴장). 시장 35/50(코스피200 은 Yahoo 가 1봉만 돌려줘 단독 재시도도 실패), RSS 80건 + 해외검색 8건 중 53건 수기 태깅. 모의 탭 5개·모의 Investment·히스토리도 같은 시각으로 재생성.
- 판정 없음 36%, 온도계 +10(가격 +30 / 뉴스 -20, 격차 50 = 내러티브 차가움). 코스피 6,889.74(-2.7%) 7,000 붕괴 — 삼성전자 -5.4%·SK하이닉스 -5.1%(OpenAI 최상위 모델 학습 중단 → 아시아 칩주 급락). 미 10년물 5.18%(9/25 장중 5.225%, 2007년 이후 최고). 금 -2.3σ. 괴리 4건(금↔VIX 상관 99, Geopolitical 뉴스+/가격- 81 …), 알림 7건.
- 재생 이력: 9/23 Liquidity Stress 37 → 9/24 Liquidity Stress 89 → 9/25 판정 없음 → 9/28 판정 없음. 22일: 판정 없음 12 · Risk-On 4 · Liquidity Stress 4, 전환 14회. 공포·탐욕: 중립 10 · 냉각 6 · 온기 6, 현재 중립.
- Investment: 드라이버 6(금·MOVE·브렌트·건화물·VIX·천연가스 — 시장 드라이버 노출 종목이 없어 4번 패널은 비고 원자재 패널로 감), 이상 거동 LG화학(NEWS_DRIVEN_MOVE, 상대 +1.5σ), 괴리 3(KB금융·삼성전자·SK이노베이션). 봉 수정 경고 8건(휘발유 11.7% · 현대제철 7.5% · 브렌트 4.0% …) — 브렌트 9/28 봉(98.9, -5%)은 보도(106달러)와 반대라 월물 교체 의심으로 적었다.
- 수기 해설 `data/commentary/2026-09-28.json`: 시장 1 · 종목 4 · 대체 4.

### 2026-09-29 갱신 (7차 수기 캡처, `data/captures/2026-09-29-manual/`) — FRED 첫 적용
- `FRED_API_KEY` 를 환경변수로 넣은 첫 캡처. 키는 이 세션 컨테이너에 없어 같은 환경의 자식 세션이 `fetch_0929.py` 로 시장·뉴스만 받아 JSON 으로 커밋했고(`series_live.json`, `fetch_report.json`, `news_raw.json`), 나머지는 이 세션이 그 JSON 으로 이어서 만들었다. 키 값은 어디에도 출력·저장하지 않았다.
- 기준 시각 9/29 00:45 UTC(09:45 KST 장중). 시장 37/50 — BE10Y(T10YIE)·US_HY_OAS(BAMLH0A0HYM2) 처음 채워짐. 코스피200 은 여전히 Yahoo 1봉. Yahoo 가 코스피·섹터 ETF·SOXX·항셍·유럽의 9/28 봉을 주지 않아 지수 1일 변화(−2.93%)는 9/25 대비이고 종목 상대 z 가 위로 왜곡됐다(6번 패널 이상 거동 2건은 이 산물). FRED 금리는 하루 지연이라 미 10년물은 9/25 값.
- 판정 **Liquidity Stress 66%**(보조 Risk-Off) — US HY OAS +3.9σ(293bp, +13bp) 가 Credit +3.87·Liquidity −2.81 을 만들었다. 온도계 −38(냉각), 가격 −59 / 뉴스 −6(내러티브 뜨거움). 괴리 6건(새로 달러↔원화 92, 브렌트↔기대인플레이션 77), 알림 9건. 신용 재료가 처음 채워져 히스토리 히트맵 제외 항목은 한국 수급만 남았다.
- 재생 이력이 신용·기대인플레이션 포함으로 다시 계산됐다: 판정 없음 9 · Liquidity Stress 6 · Risk-On 3 · Policy Driven 2 · Inflation Shock 1(9/1) · Growth Shock 1(9/10), 전환 13회, 현재 Liquidity Stress 4일째(9/23~). FOMC 날(9/15~16)은 기대인플레이션이 들어와도 Inflation 0.71 / −0.98 로 물가 충격이 아니다.
- Investment: 드라이버 6(금 −3.1σ·브렌트·건화물·USD/JPY·VIX·S&P), Impact 1(브렌트→SK이노베이션, 봉 의심), 롤오버 의심 5(휘발유·은·설탕·면화·대두 — 분기말 월물 교체), 반도체 peer·국내 모두 '상승 합의' 는 국내가 장중 봉이라 신뢰 낮음. 수기 해설 `data/commentary/2026-09-29.json`: 시장 1 · 종목 3 · 대체 4(HY OAS·BE10Y 첫 해설).

- 배지 신선도를 거래일로: `trading_days_between`(평일만), `DataHealth.max_freshness_trading_days/oldest_instruments/freshness_note`, 배지 "2거래일 전"(툴팁에 초 기준·계열), Data Health 패널 "최대 지연 2거래일 (4.0일)". 휴장일 미반영이라 상한. 테스트 +6(백엔드) +2(프런트).

- 모의 탭을 **실데이터 시나리오 점검**으로 바꿈: `config/scenario_checks.yaml`(시나리오 → 판정 라벨·테마, 임계·창·가중 규칙), `models/scenario_check.py`, `engines/scenario_check.py`(충격 서명 vs 하루·5일 z, |기대 z| 가중 일치도, 결측은 분모 제외, require 룰 상태·가설 점수, 템플릿 판정문), `GET /api/v1/scenario-check`(as_of 별 캐시, Investment 캐시의 대체·종목 z 보탬). 프런트 헤더에 점검 탭(실데이터 + 시나리오별 일치도). 시나리오 탭은 실데이터 화면을 복제하지 않고 `ScenarioView` 가 설정의 `focus` 대로 그 탭에 어울리는 판정만 앞세운다 — rule(물가 충격·유가 급등: require/support 룰 + 팩터 재료·22일 팩터 흐름 + 원자재 경로) · fear_greed(AI 센티: 온도계 밴드 + 한 달 밴드 띠) · semiconductor(메모리: 네 신호 합의) · calm(평시: 룰 걸림 여부 + 판정 없음 일수), 그 아래 관련 테마·괴리·서명 대조. 정적 배포본은 실데이터 한 뷰 + `scenario_check.json`. 모의 데이터 자체는 백엔드 MOCK 모드·테스트에 그대로 남는다. 테스트 +5(백엔드) +2(프런트). 테마 조건(뉴스 톤·가격 점수, `theme_conditions`)으로 가격 z 로 못 잡는 서명(AI 센티 = 뉴스 뜨겁고 가격 제자리)을 따로 잰다. 9/29 실데이터: 평시 63% · AI 센티 52% · 물가 충격 43% · 메모리 업사이클 17% · 유가 급등 10% — 어느 것도 지금 판정(Liquidity Stress)과 같지 않다.

- 메모리 가격: `adapters/alternative/memory_sources.py`(DRAMeXchange 홈 표·Silicon Analysts HBM 파서) + `scripts/collect_memory_prices.py`(CSV 수집기). DRAM·DDR5·NAND 현물·DXI 는 오늘부터 하루 한 줄, HBM3E·HBM4 계약가 추정은 분기 앵커. `Instrument.min_points`(봉 1개 허용)·`AltInstrument.frequency`(분기면 z 없음)·`AltDataPoint.frequency/observations`, 화면 '분기 추정'·'봉 n/20' 표식, 반도체 해석문에 '값은 있으나 봉 부족' 문장. 테스트 +8.

- 유가 탭을 **시장 원인 판별** 화면으로: `config/oil_regime.yaml`(driver 4개의 증거표·부호·가중, 확인표, 내러티브 명사, 감시 임계), `models/oil_regime.py`, `engines/oil_regime.py`(가중 clip 평균, 유가 관측 대비 CONFIRMED/UNCONFIRMED/CONTRADICTED, 브렌트·WTI 불일치면 보류, 확인표, 테마별 한 문장, 감시 조건 ≤5), `GET /api/v1/oil-regime`. 프런트 `OilRegimeView`(REGIME → DRIVER → CONFIRMATION → NARRATIVE vs PRICE → WHAT TO WATCH NEXT → Diagnostics 접이식에 룰 판정·서명 대조). 9/29: Macro/Liquidity Risk-Off −80 STRONG UNCONFIRMED, 지정학 +20. 테스트 +5(백엔드) +3(프런트).

- 물가 탭을 **Inflation & Rates Intelligence** 화면으로: `config/rates_regime.yaml`(driver 5개의 증거표, 물가 구성 5개, 커브 테너, 명목 분해, 확인표 12줄, 괴리 6짝, 전이표, 전환·해제 조건), `models/rates_regime.py`, `engines/rates_regime.py`(가중 clip 평균, 10년 금리 방향 대비 상태, 방향 맞는 driver 우선 지배, 커브 모양·주도 구간(트위스트 처리), 명목 − 기대인플레 = 실질 + TIPS 대조, CONFIRMED/MIXED/NOT_CONFIRMED/MISSING, 괴리 자동 탐지, 전이 방향, 전환 조건 ≤5 + 해제 조건), `GET /api/v1/rates-regime`. 계열 US5Y·BE5Y·TIPS10Y·TIPS5Y 추가(자식 세션이 FRED 키로 9/29 캡처에 병합), 금리 이름 "US 10Y Yield" 식으로 명확화. 프런트 `RatesRegimeView`(REGIME → DRIVER → INFLATION PRESSURE → CURVE → DECOMPOSITION → CONFIRMATION → DIVERGENCE → IMPLICATION → WHAT CHANGES THE VIEW → Diagnostics 접이식). 9/29: **LONG-END RATE / TERM PREMIUM SHOCK — Inflation Repricing Not Confirmed**, 기간 프리미엄 +84 STRONG CONFIRMED(30Y +1.6σ · 2s10s +1.9σ · MOVE +2.6σ · TIPS10Y +1.5σ), 물가 리프라이싱 −19; 베어 스티프닝 장기 주도; 10Y +16bp = 실질 +16bp + 기대인플레 0bp(TIPS 실측 +15bp); 확인 7 · 혼재 4 · 불확인 1(은행); 괴리 6건. 실현 물가·임금 계열 없음(결측 표시). 테스트 +9(백엔드) +4(프런트).

- AI 탭을 **AI Trade Intelligence** 화면으로: `config/ai_regime.yaml`(바스켓 6그룹 32종목 + 국내 8종목, 상대·breadth·리더십 임계, driver 5개 증거표, 내러티브 driver 7개 키워드 사전, 매크로 확인 행, 스트레스 항목, 판정 규칙, 전환 조건), `models/ai_regime.py`, `engines/ai_regime.py`(Nasdaq 달력 위 동일가중 바스켓 지수와 벤치마크 비율 지수 → compute_feature 로 절대·상대 z, 그룹별 1D/1W/1M 상대 모멘텀·순위·회전, 5/20DMA·상승 breadth 와 1주 변화, 내러티브×가격 2×2, 매크로 EXPLAINS/DOES_NOT_EXPLAIN → macro_driven/ai_specific, 스트레스 점수, 순서 있는 판정 규칙, 트리거), `AiRegimeService`(바스켓 계열은 알트 어댑터로 수집·as_of 캐시, MOCK 은 시나리오 합성), `GET /api/v1/ai-regime`, ai_sentiment focus = ai_regime(fear_greed 경로는 남아 있다). 프런트 `AiRegimeView`(AI REGIME → AI vs MARKET → DRIVERS → LEADERSHIP → BREADTH → NARRATIVE×PRICE → MACRO CONFIRMATION → STRESS → WHAT CHANGES → Diagnostics 에 판정 규칙·공포/탐욕 띠·구성원 표·서명 대조). 9/29: **MACRO-DRAGGED AI WEAKNESS** — 바스켓 −1.2σ(5일 −2.2%), Nasdaq 대비 −1.5%p·상대 z −0.7σ(AI-specific 문턱 −1 아님), 매크로 6/6 설명, breadth 20일선 59%(1주 −22%p, 광범위한 매도), 1주 리더 Software(전 그룹이 Nasdaq 에 뒤짐)·후미 Hyperscalers −3.5%p, 뉴스×가격 UNCLEAR(톤 +6), 스트레스 LOW 2/8, 트리거 하이퍼스케일러 4/5 하락 충족. 테스트 +10(백엔드) +4(프런트).

- **AI 센티2** 탭 신설(AI 센티는 기본 화면 유지): `scenario_checks.yaml` 의 check 가 `scenario:`(기준 시나리오)·`title:` 을 가질 수 있게 해 같은 ai_sentiment 시나리오를 `ai_sentiment2`(focus `ai_regime_full`)로 한 번 더 쓴다. `AiRegimeView` 의 `extended` 로 확장 블록을 켠다. 확장 내용: `engines/ai_value_chain.py` + `config/ai_regime.yaml`(instruments 52종목 universe, value_chain 10 세그먼트·노출·매크로 민감도·driver, stock_impact 네 축 임계, expectation_gap 가중, transmission 9단계, semi_confirmation 6영역 + 메모리 6행, news_impact driver→세그먼트 체인, what_matters 질문 7). 상태 띠·FUNDAMENTAL CONFIRMATION·부제·SUMMARY, 전파 체인, 밸류체인 리더십(CURRENT LEADERSHIP 4 / LAGGING 3), 반도체 펀더멘털 확인(업사이클 판정 아님, 메모리 데이터는 확인 데이터·N/A 그대로), 종목 영향도(THEME/FUNDAMENTAL/MARKET/MACRO 화살표 + overall + 해석, 단일 점수 없음), 레이더 5버킷(이유 포함), 뉴스→driver→밸류체인→종목(직접 언급 종목 우선, NEWS POSITIVE / MARKET UNCONFIRMED), 기대 vs 펀더멘털 gap, What Matters Now ≤5. 서비스는 Investment 캐시(메모리·HBM 대체데이터·컨센서스)를 넘긴다. 프런트 `AiValueChainSections.tsx`, Diagnostics → Details / Data Quality. 9/29: MACRO-DRAGGED / FUNDAMENTALS RESILIENT(PARTIAL — Advanced Packaging STRONG · Equipment LEADING, Compute·HBM·Foundry MIXED, Commodity Memory 계열 없음), 전파: HBM +39 POSITIVE · Equipment +37 · Foundry/Packaging +16, Capex·GPU·DC Infra MIXED, EPS UNCONFIRMED; 리더십 Equipment(+4.9%p)·Packaging·Software·Networking, 후미 Hyperscalers·Compute·Power; 레이더 Strongest SMCI·MU·PWR, Improving TEL·DDOG·AMAT·LRCX; gap Equipment +19 / Power −34. 테스트 +3(백엔드) +1(프런트).

- **`실시간 2` 탭을 decision cockpit 으로**(`실시간` 은 기존 화면 그대로 첫 탭, `실시간 2` 가 cockpit — AI 센티/AI 센티2 와 같은 방식. 물가·유가·AI 센티·AI 센티2 탭은 손대지 않음): `config/cockpit.yaml`(판정별 절 문구·꼬리, driver 후보 11개의 증거·시장 영향 가중·why/next 템플릿, 대체데이터 증거 조건, 자산군 7행의 판정별 기대 방향, 주식 테마만 고르는 리더십 규칙과 섹터 중복 제거, 전파 체인, 레이더 가중, 촉매 등급 임계·군집 Jaccard·알림 병합, 데이터 상태 중요 계열), `models/cockpit.py`, `engines/cockpit.py`(MARKET NOW 문장 조립, importance = (강도·커버리지·판정 확인·지속·뉴스) × 영향 가중, CROSS-ASSET CONFIRM/HEADWIND/DIVERGE/FLAT/MISSING + 괴리 ≤2, 주식 테마 리더십 + THEME PULSE, driver → 산업 → 종목 전파와 종목 z 확인, 레이더 점수, 촉매 군집·등급·알림 병합·KST 시각, 컨센서스 없으면 earnings None, WHAT MATTERS NEXT ≤5 + 달력, 워치리스트 ≤5, Data Status 한 줄 + 경고), `CockpitService`(보조 계층은 `_try` 로 감싸 실패해도 cockpit 은 뜬다), `GET /api/v1/cockpit`. 프런트 `CockpitView`(격자 40|60 · 50|50 · 100 · 50|50 · 60|40, 모바일 한 열 + TOP 3 drivers + "나머지 n개 보기", LIVE CATALYSTS 고정 높이·내부 스크롤·클릭 펼침, Details / Diagnostics 아래에 기존 DashboardGrid·InvestmentSection 그대로), cockpit 을 못 받으면 예전 화면. `App` 의 `liveView` 상태로 두 탭을 오가며 cockpit 은 둘째 탭에서만 요청한다. 정적 배포본 `cockpit.json` 포함. 9/29: **LIQUIDITY STRESS / RISK-OFF** HIGH 66% · 4일째 · NO REGIME → LIQUIDITY STRESS, 핵심 변수 HY OAS +3.9σ · VIX +1.2σ · S&P −1.2σ · MOVE +1.0σ; drivers LONG-END RATES ↑(지속) · CREDIT STRESS ↑(판정 확인) · VOLATILITY ↑ · OIL ↓ · EQUITY ↓; 교차자산 5/7 확인(RATES 역풍 · GOLD 괴리), 핵심 괴리 금/VIX 98 · 달러/원화 92(전체 12); 리더 Airlines·Semiconductor·IT·AI, 후미 Oil·Energy; 전파 6체인(장기금리↑ → 소프트웨어·데이터센터 REIT: ServiceNow·Snowflake·Digital Realty·Equinix CONFIRMED, Palantir CONTRADICTED); 레이더 8; 촉매 12(CRITICAL 3, 브렌트 $106 기사 2건 군집, HY OAS 알림 병합); earnings 없음(숨김); NEXT 5; 워치 5; 데이터 37/50 · 지연 5 · 최대 2D · 10Y·HY OAS stale. 테스트 +6(백엔드) +3(프런트).

- **실시간 2 에 MARKET REGIME HISTORY · 1M**(다른 탭은 손대지 않음): `config/cockpit.yaml` `history`(taxonomy, display 안정화 규칙, heat driver 5, regime_factors, 기간표), `models/cockpit.py`(RegimeDay · RegimeBlock · RegimeTransition · DriverHeat · RegimeShare · HistoryRange · RegimeHistory, `Cockpit.history`), `engines/regime_history.py`(거래일 스냅샷 dominant/end/dwell/장중 전환, `stabilize` = 연속 2일 또는 확신 ≥ 80 또는 dwell 조건, 블록·전환·비중·composite slope·factor heat, 3M/6M 은 데이터 없으면 꺼짐), `SnapshotService.state_observations`(저장소 + 메모리 스냅샷의 장중 판정), `CockpitService` 가 관측을 넘김. 프런트 `RegimeHistoryCard`(MARKET NOW 다음 · DRIVERS 앞, 띠 hover 툴팁 · 클릭 상세, 전환 클릭 evidence, 모바일 접기), `.ck-hist` 격자(now 40 | history 60, drivers 전폭). 9/29: Neutral 11일 → Liquidity Stress 하루(9/14) → Neutral 3일 → Policy Driven 3일 → Liquidity Stress 4일째, 전환 4회(9/15 · 9/18 Rates ↑ · 9/23 Rates ↑ + MOVE·달러), 비중 Neutral 64 · Liquidity 23 · Policy 14, composite −39 (5D −74), heat Credit ↑↑ · Liquidity ↓↓. 테스트 +3(백엔드) +2(프런트).

- **실시간 2 · STOCK RADAR ANALYST VIEW + WHAT MATTERS NEXT 전파 경로**(두 카드만): `models/analyst_view.py`, `adapters/analyst_view.py`(수기 파일 + JSON 캐시 저장소, `validate_view` 필수 필드·30일·검색 결과 URL 대조, `LlmAnalystSearch`), `ai/client.py` `search_structured`(web_search + JSON 스키마, 검색 결과 목록 반환), `AnalystViewService`(radar 종목만, TTL 12h, 백그라운드 스레드, provider 없으면 저장분만), `GET /api/v1/analyst-views`, `data/analyst_views/manual/2026-09-29.json`(웹 확인 5건: SK하이닉스 이수림·DS 9/29, Micron Gerra·Baird 9/28, Quanta Dillard·Bernstein 9/24, AMAT Brett·MS 9/28, 삼성전자 정우성·LS 8/31; SMCI·TEL 30일 초과, DDOG 이름 미확인 → 제외). `config/cockpit.yaml what_matters_next.paths`(11 driver × up/down: trigger/first_order/assets/themes/stocks tier/confirm), `engines/issue_path.py`(status_of/aggregate, Observer instrument·segment·theme·stock, EXPECTED vs OBSERVED 결론, AI 이슈는 ai_regime 밸류체인 재사용), `models/cockpit.py`(IssuePath·PathStage·PathCheck·PathTier·PathStock, RadarStock.system_axes/related_issues, NextItem.id/path). 프런트 `IssuePath.tsx`(accordion, tier 5 + View all, What would confirm n/m), RadarCard(ANALYST VIEW 줄 + 클릭 상세 + SYSTEM vs ANALYST 라벨 + Related market issues), NextCard 클릭, radar ↔ issue 양방향 스크롤, `useAnalystViews`(비동기, pending 재조회). 9/29: 이슈 5 모두 경로 있음 — 10Y 3/4 확인(Software·Compute·REIT·Hyperscalers WEAK), HY OAS 4/4(반도체 RESILIENT), VIX·MOVE 4/4, 유가→기대인플레 PARTIAL(BE10Y −0.3σ, 테마 데이터 없음), 지수 하락 확산 2/4(breadth 결측). 테스트 +6(백엔드) +3(프런트).

- **실시간 2 표현 층(2026-09-30)** — CROSS-ASSET · WHAT MATTERS NEXT 만, 로직 불변: `config/cockpit.yaml explain`(regime_short · cross_meaning · divergence_notes · horizon_read · stage_explain · tier_show) + candidates `why_next` + cross_assets `group` + 경로별 `*_explain`; 모델 CrossAssetRow.instrument_label/group/meaning, CrossAsset.current_view/confirm_text/market_read, KeyDivergence.phenomenon/why/reference, PathStage.explain, PathStock.expected_text/priority, PathSummary, IssuePath.summary/tier_show, NextItem.horizons/horizon_read/why_next; 엔진은 MARKET READ 조립(조사 처리), 괴리 현상·근거(legs), 1D/5D/1M 기간과 자동 해석, 단계 확인 수(CONFIRMED 만, PARTIAL 별도), 종목 우선순위 정렬. 프런트 `components/ko.ts`(STATUS_KO · 모바일 짧은 꼬리 · TIER_TIP · GLOSSARY · MATCH_COLOR · legend), `StatusKo`, CrossAssetCard(목적·현재 판단·n/m 의미·MARKET READ·그룹·대표 지표·KEY DIVERGENCE 현상→왜→근거·legend), NextCard(닫힘: 상태+한글·1D/5D/1M·해석·Why it matters / 열림: SUMMARY → EXPECTED/OBSERVED → 단계 → 종목 → WHAT WOULD CONFIRM), `IssuePath.tsx` 재작성. 테스트 +2(프런트).

- **실시간 2 · DRIVER HEAT 의미 층 + Leadership Intelligence(2026-09-30)**: `config/cockpit.yaml history.drivers`(label_ui · label_ko · meaning · horizon 대표 계열 · read 템플릿, heat_legend), `leadership_intel`(임계, quality_ko, 테마별 hints: driver · links(macro 플래그) · ai_segment · risk · watch · stocks · view_up/down), `data/street_views/manual/2026-09-30.json`(확인 6건); 모델 DriverHeat.label_ui/label_ko/meaning/horizons/horizon_read, ConfirmRow · StreetView · KeyStock · LeadershipDetail, LeaderRow.system_view/detail, Leadership.read; `engines/regime_history.py`(heat 의미·1D/5D·해석), `engines/leadership_intel.py`(WHY ≤3, MARKET CONFIRMATION 6행 리더/후미 의미 분리, QUALITY 규칙 순서, SYSTEM VIEW 템플릿, STREET VIEW 로더·검증·SYSTEM READ, KEY STOCKS 우선순위, WHAT TO WATCH, LEADERSHIP READ), cockpit 4b 절(AI 전파 단계 점수를 펀더멘털로). 프런트 Heat 재작성(라벨·의미·기간·legend), `LeadRow` 분리 + 카드 아래 full-width `LeadershipDetailView`(INTERNAL/EXTERNAL 구분, RADAR ● → radar). 9/29: LEADERSHIP READ "broad Risk-Off 이지만 Airlines · Semiconductor · IT 는 상대강도 유지, Oil · Energy 는 Brent ↓ 와 함께 이탈, 선별적 Risk-On 이 breadth 를 갖고 유지"; Semiconductor BROADENING(펀더멘털 Equipment 전파 +37 PARTIAL, street 3건), Airlines MACRO-DRIVEN(Brent −1.9σ, street Deutsche Bank), AI BROADENING(street GS · UBS 견해 갈림 → SYSTEM READ), Oil · Energy MACRO-DRIVEN(street JPM Lofting). 테스트 +3(백엔드) +2(프런트).

- **실시간 2 · TRANSMISSION read + WATCHLIST 체크포인트(2026-09-30)**: `config/cockpit.yaml transmission.strength/strength_ko/subject_ko/industry_labels`, `watchlist`(weights · priority_high · driver_labels · hints); 모델 TransmissionStock.industry, TransmissionChain.evaluated/strength/strength_ko/read, WatchLink, WatchRow.theme/why/key_drivers/trigger/reasons/priority/transmission/issues/commentary/eps_revision; 엔진 `_strength`(확인 비율 × driver 강도) · `_read`(STRONG/PARTIAL/LIMITED/UNCONFIRMED 별 문장 + CONTRADICTED 종목 점검 문장), 워치리스트 선정 점수와 WHY(펀더멘털/테마 상태 + 가격 confirmation, '이고/지만' 연결) · KEY DRIVER ≤3 · TRIGGER · 태그 · 전파/이슈 연결. 프런트 TransmissionCard(강도 + read, 링크 focus), `WatchRowView`(TRANSMISSION ● → 전파 카드 스크롤·강조, RELATED ISSUE → 이슈 열기, 탭 펼침). 9/29: LONG-END RATES 4/5 STRONG("Software · Data Center Infra 까지 폭넓게 확인, Palantir 는 예상과 다르게 상대강도 유지"), CREDIT STRESS 2/5 PARTIAL, VOLATILITY 1/3 LIMITED, OIL 3/3 STRONG, EQUITY DIRECTION 0/4 UNCONFIRMED; 워치리스트 SK하이닉스 · 삼성전자 · HMM · 한미반도체 · 대한항공(모두 HIGH). 테스트 +2(백엔드) +2(프런트).

- STOCK VIEW(2026-10-01): `config/ai_regime.yaml stock_view`(impact anomaly taxonomy·read·watch 템플릿, radar 버킷 재명명·설명·why, news 카테고리·why·reaction·priority 가중, 중복 묶기), `news_impact.top_n` 12, 모델 StockSignal/RadarItem/RadarBucketView/NewsCard/StockView + `AiRegime.stock_view`, `engines/ai_stock_view.py`(라벨 규칙, 특이성 순 선별 + 세그먼트 cap, 레이더 재매핑, 뉴스 묶기·반응·우선순위), 프런트 `AiStockSections.tsx`(SignalRow accordion · RadarRow · NewsRow TOP/OTHER accordion, 기존 네 축 표는 View all). 계산 불변.
- BASKET READ · BREADTH READ(2026-10-01): `config/ai_regime.yaml basket_read · breadth_read`(TRUE LEADERSHIP / RELATIVE RESILIENCE / 구조적 laggard 임계, rotation 5조건, 단기·중기 분리, contrast, 다음 확인 포인트 템플릿, 연결형 _conj 로 3문장 유지), `engines/ai_reads.py`, `Leadership.read` · `Breadth.read`, 프런트 extended 만 read 표시(기본 탭은 예전 문장). 숫자 나열 금지 테스트.
- 전파 단계 근거 태그 + 메모리 가격 일일 수집(2026-10-01): `TransmissionStage.basis`/`ChainStage.basis`(NEWS · PRICE · DATA, 결측 입력 제외 — `ai_value_chain.py` 단계 루프에서 실제 들어간 part 로 결정), 프런트 `AiChainSections` 태그 + 범례, `.github/workflows/collect-memory-prices.yml`(평일 03:40 UTC, collect_memory_prices → CSV 커밋), 10/1 DRAMeXchange 행 4개 추가. 테스트 +1(백엔드) +프런트 기존 테스트 확장.
- AI 센티2 AI CHAIN VIEW(2026-10-01): `config/ai_regime.yaml chain_view`(subtitle · 행 매핑 stage↔segment · VIEW 규칙 · 라벨 · read 템플릿), 모델 ChainRow/ChainStage/ChainSemiArea/ChainSnapshot/ChainView + `AiRegime.chain_view`, `engines/ai_chain_view.py`(가격 상태 LEADING/STRONG/MIXED/LAGGING/WEAK, VIEW 조합, 상하위 3, 반도체 의미 자동 문장, SNAPSHOT), 프런트 `AiChainSections.tsx`(SNAPSHOT + ALIGNMENT → TRANSMISSION 한 줄씩 → LEADERS/LAGGARDS → SEMI 상태 행; 기존 상세 섹션은 펼침 안으로). 계산 불변.
- AI 센티2 AI VS MARKET → WHAT IS DRIVING AI(2026-09-30): `config/ai_regime.yaml vs_market`(절대·상대·상대 z 라벨/의미, MARKET READ·RELATIVE READ 템플릿, 연결 문구) · `driver_view`(점수 범례, 5 밴드, driver 별 meaning/why/transmission/price_check/status_ko/aux/extra_rows) · `driver_verdict`(status_weight·min_abs·역할 라벨·결론 템플릿), 모델 PriceCheck/DriverRef/DriverVerdict + AiVsMarket·DriverScore 표시 필드, `engines/ai_driver_view.py`(annotate_vs_market · annotate_drivers · build_verdict: CONFIRMED 우선, |score|×확인 가중×확보율, 바스켓 방향 없으면 primary 없음), 프런트 `AiDriverSections.tsx`(VsMarketSection · DriversSection, extended 만). 점수 계산 불변.
- AI 센티2 표현 개선(2026-09-30): `status_meaning`(상태 띠 카드마다 한 줄 투자적 의미), `regime_read`(FC 장문·SUMMARY·맥락 → AI REGIME READ 2~3문장 + KEY TENSION), sentiment `gap_read`·`net_effect`·`history.read`·`desc_ko`, READ 는 입력 단위 ≤2문장. 프런트 `StatusStrip` 의미 줄 + AI REGIME READ + KEY TENSION(장문은 `RegimeLongText` 로 Details 안), `AiSentimentSection` 재배치(게이지 → 5 factor bar → KEY TENSION → DRIVERS + NET → 1M 밴드 배경 스파크라인 → READ), 숫자 나열·큰 legend 제거. 로직 변경 없음.
- **AI 센티2 · AI SENTIMENT · GREED & FEAR(2026-09-30)**: `config/ai_regime.yaml sentiment`(구성요소 5 가중·입력 ref·밴드·보조 상태 규칙·SUPPORT/PRESSURE 문턱·READ 템플릿·1M 이력), `models/ai_regime.py` SentimentInput/Component/Factor/Point/History/AiSentiment + `AiRegime.sentiment`, `engines/ai_sentiment.py`(기존 AiRegime 값 → clip(값/ref) 0~100 → 가중 평균, 결측은 분모 제외, 보조 상태 = 긴장 최대 규칙, 입력 단위 SUPPORT/PRESSURE ≤3, 템플릿 READ + fix_particles, 1M 이력은 같은 공식을 하루씩 되돌림 — 이력 없는 구성요소는 basis 제외·명시), `build_ai_regime` 끝에 호출. 프런트 `AiSentimentSection.tsx`(SVG 반원 게이지 · 바늘 −90°+s/100×180° · 중앙 점수/상태/한글/1D·1W · 보조 상태 · 구성요소 분해 · READ · STRUCTURE · 1M 스파크라인 · 범례), AI TRADE REGIME → 게이지 → AI vs MARKET(extended 만), `--gf-*` muted 팔레트. 9/29: 40 NEUTRAL, FUNDAMENTALS > PRICE. 테스트 +4(백엔드) +1(프런트).
- MARKET LEADERSHIP Full-width Detail Panel(2026-09-30): 상세를 카드 column 안에서 펼치지 않고 그리드 `leaddet` 행(전체 폭)에 별도 `LeadershipDetailPanel` 로 연다(`.ck.ck-ldopen` 그리드 템플릿, 한 번에 한 테마, ACTIVE 표시, Summary → WHY / SYSTEM VIEW / CONFIRMATION | STREET VIEW / KEY STOCKS / WATCH). 2열은 1280px+ 이면서 `@container ldp` 폭이 충분할 때만, 이하 한 열, 768px 이하 single column. STREET VIEW 원문은 2줄 접힘, KEY STOCKS 는 독립 row, CONFIRMATION 은 Metric | Value | Status. 로직 변경 없음. 프런트 테스트 65.
- DRIVER HEAT 모바일 겹침 수정(2026-09-30): factor 를 이름/한글 → 띠(width 100%) → 상태·1D/5D → 해석문 순 세로 스택 블록으로 재구성. 데스크톱은 150px 라벨 | 본문 2열, 768px 이하는 단일 열. 고정폭·nowrap 제거, 날짜축은 공통 헤더 한 줄. Playwright 로 1680/390/360px 에서 라벨·띠 겹침 없음 확인.

### 2026-10-06 갱신 (8차 수기 캡처, `data/captures/2026-10-06-manual/`) — 장 마감 후 첫 캡처
- 기준 시각 10/6 07:40 UTC(16:40 KST 장 마감 후). 한국 봉은 10/6 종가, 미국 지수·VIX·MOVE·섹터 ETF 는 10/5 종가. FRED DGS 계열(US2Y·5Y·10Y·30Y·TIPS·HY OAS)은 10/2 가 마지막이라 배지가 "2거래일 전" 이고, BE10Y·BE5Y 는 10/5. 시장 41/54 — 코스피200(Yahoo 1봉)·항셍·니케이 결측. `fetch_1006.py` → `fetch_extra_rates.py` → `rebuild_snap_1006.py` → `manual_tags_v8.py` + `build_manual_snapshot_v8.py` → investment(이전 = 9/29) → scenario/oil/rates → history(모든 캡처 이벤트 383건 병합) → ai_regime(`--fetch`, 바스켓 52/52) → cockpit 순. 키 값은 어디에도 출력·저장하지 않았다.
- 뉴스: RSS 80건(한경 마켓·매경 증권·Investing.com·CNBC) 중 38건 + 웹검색으로 제목·URL·날짜를 확인한 해외 기사 3건(Yahoo 10/5 마감, RTE 유가 10/5, Seoul Economic Daily HBM 10/1) 수기 태깅. 본문을 읽지 못한 기사는 넣지 않았다. news.google 은 프록시 403.
- 판정 **Risk-On 91%** — US HY OAS −3.6σ(10/1 324bp → 10/2 310bp), S&P +0.9σ(10/5 7,773.95 사상 최고권), Nasdaq 100 +0.7σ, USD/CNH −2.6σ. 온도계 +29(온기), 가격 +43 / 뉴스 +9(narrative_cold). 괴리 3(금↔VIX 97, 10Y↔금융 74 상관 반전, China 뉴스↔가격 65). 재생 이력: 판정 없음 7 · Risk-On 6 · Liquidity Stress 6 · Policy Driven 2 · Growth Shock 1, 전환 12회, Risk-On 3일째(10/2~).
- 국내는 반대 방향: 코스피 6,941.38(−0.89%) 7,000 아래, 코스닥 919.92(+2.98%). 외국인 코스피 1조7,689억 순매도. SK하이닉스 −3.69%·삼성전자 −1.45% vs 삼성전기 +5.95%·주성엔지니어링 +17.5%. 원·달러 1,341.5. 미국 10년물 5.31%(2002년 이후 최고권)에도 나스닥 27,477(+1.05%)·엔비디아 사상 최고.
- 시나리오 점검: 평시 79% · AI 센티 78% · 물가 충격 29% · 메모리 업사이클 15% · 유가 급등 9%. 유가 탭 Macro/Liquidity UNCONFIRMED(+21). 물가 탭: 베어 스티프닝, 10Y +11bp = 실질 +9bp + 기대인플레 +2bp(TIPS 실측 +9bp).
- AI 센티2: **CONFIRMED AI RISK-ON / FUNDAMENTALS RESILIENT** — 바스켓 +0.6σ(5일 +3.4%), Nasdaq 대비 +0.7%p INLINE, breadth 20일선 81%(1주 +19%p widening), 뉴스×가격 CONFIRMED(톤 +17), 스트레스 LOW 0/8. DRIVER VERDICT: primary Broad Risk-Off +53 CONFIRMED · secondary AI Narrative +36 · 상쇄 Macro/Rates −40 CONTRADICTED · 반도체 사이클 +19 NOT YET CONFIRMED. 리더십 Equipment(+9.1%p)·Packaging·Networking·Compute, 후미 Software·Memory/HBM. 전파: HBM +65 STRONG · Equipment +50 · Narrative +42 · Foundry +31 · Compute +22, Commodity Memory·EPS NO DATA. 센티먼트 게이지 67 GREED(FUNDAMENTALS 73 · NARRATIVE 71). TOP STOCK SIGNALS: 한미반도체·Ciena·AMAT RELATIVE BREAKOUT, AppLovin RELATIVE BREAKDOWN, Sandisk FUNDAMENTAL LEADING; 레이더 CONFIRMED LEADERS 삼성전자·Micron. 프런트 fixture(`__fixtures__/ai_regime.json`) 교체에 맞춰 실데이터 값 단언 4곳을 10/6 값으로 바꿨다(70/70).
- 메모리 가격 수집기를 이 세션에서 한 번 더 돌려 10/6 줄 추가(DRAM 46.321 · DDR5 58.167 · NAND 19.396 · DXI 1,114,235 — 3봉). HBM4 계약가 추정은 10/1 행 36.11 $/GB. 애널리스트 뷰는 새 확인 건이 없어 9/28 MU·AMAT 2건(8D)만 — 새로 만들지 않았다.
- 정적 배포본 `build_dash.py` 의 CAP 을 10/6 캡처로 바꾸고 상단 안내문을 "장 마감 후 기준·FRED 10/2·항셍/니케이/코스피200 결측" 으로 고쳤다. 8개 탭 모두 1440/390 에서 가로 스크롤·페이지 오류 없음.

### 2026-10-07 갱신 (9차 수기 캡처, `data/captures/2026-10-07-manual/`)
- 기준 시각 10/7 04:23 UTC(13:23 KST 장중). 한국 봉은 장중값, 미국 지수·VIX·MOVE·섹터 ETF 는 10/6 종가. FRED DGS 계열은 10/5 가 마지막(배지 "2거래일 전"), BE10Y·BE5Y 는 10/6. 시장 41/54 — 코스피200·항셍·니케이 결측. 파이프라인은 10/6 과 같은 순서(`fetch_1007.py` → 금리 병합 → `rebuild_snap_1007.py` → `manual_tags_v9.py` + `build_manual_snapshot_v9.py` → investment(이전 = 10/6) → scenario/oil/rates → history(모든 캡처 이벤트 병합) → ai_regime(`--fetch` 52/52) → cockpit). 키 값은 어디에도 출력·저장하지 않았다.
- 뉴스: RSS 80건 중 34건 + 웹검색으로 확인한 해외 기사 2건(Yahoo 10/6 마감, Investing.com 삼성·하이닉스 하락) 수기 태깅. 본문을 못 읽은 기사는 넣지 않았다.
- 판정 **판정 없음 41%**(Risk-On 3일 뒤 해제) — 미국 지수는 사상 최고(S&P 7,818.93 +0.58%, 나스닥 27,599.79)지만 하루 z 가 Utilities +3.6σ·USD/CNH −2.2σ·MOVE −1.7σ 로 위험선호 축이 흐려졌다. 온도계 +8(중립), 가격 +13 / 뉴스 +1. 괴리 1(상관 체제 98), 알림 5. 재생 이력: 판정 없음 9 · Liquidity Stress 6 · Risk-On 4 · Policy Driven 2 · Growth Shock 1, 전환 13회.
- 국내는 삼성전자 10/8 잠정실적(컨센서스 105.5~106조, 8월 114조에서 원화 강세로 하향)과 15조 자사주 매입 종료(10/6), 반도체 ETF 리밸런싱이 겹친 경계 국면 — 코스피 6,882(−0.85%), 외국인 8,838억 순매도(10:40), SK하이닉스 −1.8%, LG전자는 3분기 잠정 영업이익 7,818억(추정 −17%)에 −7.7%. 미국은 AMD +2.8%·브로드컴 +3.7%·마벨 +5.8% vs 마이크론 −1.7%·하이닉스 ADR −6.4% 로 AI 가속기와 메모리가 갈렸다. 콘스텔레이션–구글 3,590MW 원전 전력 계약 +12.3%.
- 시나리오 점검: 평시 79% · AI 센티 76% · 메모리 업사이클 4%(MU −0.4σ·하이닉스 반대). 유가 탭 공급 +18 UNCONFIRMED. 물가 탭: 2년물 −1.3σ·2s10s +2.1σ 로 연준 정책 경로 driver 우세(−46).
- AI 센티2: **CONFIRMED AI RISK-ON** — 바스켓 +0.9σ(5일 +4.8%), Nasdaq 대비 +1.9%p OUTPERFORM(상대 z +0.7σ), breadth 20일선 88%(1주 +26%p), 뉴스×가격 CONFIRMED, 스트레스 LOW. DRIVER VERDICT: primary AI Narrative +28 · secondary Broad Risk-Off +25, 반도체 사이클·AI 고유 스트레스는 NOT YET CONFIRMED, 상쇄 압력 없음(Macro/Rates −5). 리더십 Networking(+7.0%p)·Power/DC(+5.9%p), 후미 Memory(−4.8%p) — BASKET READ 가 처음으로 rotation 을 확정했다(Semis → Networking, 5조건 중 4개 이상). 전파: HBM +49 STRONG, DC Infra +30, Narrative +32, Compute +25, Equipment +20, Foundry +12 MIXED. 게이지 68 GREED. TOP STOCK SIGNALS: Ciena·Credo·AMD CONFIRMED, Sandisk FUNDAMENTAL LEADING, Constellation·Vistra RELATIVE BREAKOUT, AppLovin·UMC·효성중공업·HD현대일렉트릭 RELATIVE BREAKDOWN. 프런트 fixture 교체에 맞춰 실데이터 단언 4곳을 10/7 값으로(70/70).
- 메모리 가격 수집기 10/7 행 추가(DRAM 46.357 · DXI 1,115,853 — 4봉). 애널리스트 뷰는 레이더 종목 중 PWR(Bernstein 9/24, 13D) 1건만 — 새로 만들지 않았다.
- 정적 배포본 CAP → 10/7, 안내문 "장중 기준·미국 10/6 종가·FRED 10/5". 8개 탭 1440/390 확인.

### 2026-10-07 — 모든 History 를 저장 후 고정(Daily snapshot history)
- 원칙: PAST + SNAPSHOT EXISTS → 유지·LOCKED / PAST + SNAPSHOT MISSING → 그 날짜까지의 데이터와 현재 모델로 1회 계산 → BACKFILLED·LOCKED / TODAY → LIVE → Daily Finalization(16:10 KST) → RECORDED·LOCKED. 모델·룰·데이터가 바뀌어도 과거 불변. silent overwrite 금지(`LockedSnapshotError`), 수정은 `correct()` 의 audit trail 로만.
- 구현 `marketpulse/history/`(store JSON dir/SQLite · manager · calculators · assemble · integrate · migrate · CLI), `config/history.yaml`(탭 6개 taxonomy·finalize_time·footnote·logic_files), `models/daily_history.py`. 기존 `state_history.replay_market_state` 는 `replay_point` + `summarize_points` 로 나눠 backfill 과 RECOMPUTED HISTORY(`?mode=recomputed`)가 같이 쓴다. `ai_sentiment.DayValues` 로 날짜별 입력을 분리. `StateHistoryPoint`/`SentimentPoint`/`RegimeDay` 에 source·calculated_at·model_version·logic_version·locked.
- API `HistoryService`: `/history/{tab}`, `/history`, stored 기본의 `/market-state/history`, cockpit·ai-regime 의 history 도 stored. producer 서비스는 오늘 값만 즉시 기록하고 과거 backfill 은 `/history/{tab}` 첫 요청 때 1회(AI 판정 22일 ≈ 11초). MOCK 은 메모리 저장소 + `mock-{scenario}-` 접두. 주기 실행기도 틱마다 기록.
- 캡처: `capture_daily_history.py --market`(migration + 시장 sync → state_history.json) → investment(메모리) → rates/oil → ai_regime(센티먼트·AI 판정) → `--assemble`(daily_history.json). 저장소 `data/history/*.json` 커밋. 10/7: RECORDED 10 캡처일 + BACKFILLED 로 22일 창 완성.
- 프런트: `DailyHistoryStrip`/`DailyHistoryPanel`(AI 센티2 AI TRADE REGIME HISTORY, 물가·유가 STATE HISTORY, 메모리 MEMORY CYCLE HISTORY), 기존 띠·REGIME HISTORY·1M SENTIMENT 에 출처 툴팁·각주 "각 거래일 최종 snapshot 기준 · 저장 후 고정". 테스트: 백엔드 +14(RT1~7 포함) · 프런트 +7(77/77).

### 2026-10-07 — 실시간 2 MARKET TONE SNAPSHOT
- MARKET REGIME HISTORY 와 TODAY'S MARKET DRIVERS 사이. 화면은 실시간 탭의 시장 온도(`SentimentGauge`)를 같은 `snapshot.thermometer` 로 그대로 보인다(폭만 560px 제한) — 두 탭의 숫자·눈금·재료 스트립·문장이 동일. `MarketToneCard`, 그리드 `.ck-tone` 템플릿 3단계.
- 백엔드 `Cockpit.tone: MarketTone`(`engines/market_tone.py` + `config/cockpit.yaml tone`): 온도계를 regime 과 대조한 상태 taxonomy·재료 의미·1W 변화·PRICE vs NEWS·REGIME CONFIRMATION·2문장 READ. API 소비자용(화면은 온도계 그대로). 테스트 백엔드 +3 · 프런트 +2(79/79).

### 2026-10-07 — 실시간 2 CURRENT REGIME 단일 출처 (OFFICIAL vs RAW)
- History CURRENT 와 MARKET NOW 가 다르게 보이던 문제 수정. 공식 regime 은 `stabilize()` 의 인과적 확인 규칙(연속 2거래일 같은 raw 또는 확신 ≥ 80)으로 하나만 정하고, 두 카드와 drivers·cross-asset·tone·what-matters 가 같은 값을 쓴다. 오늘 룰의 판정은 RAW SIGNAL(raw · RAW PERSISTENCE · STATUS CONFIRMED/UNCONFIRMED TRANSITION/TRANSITION WATCH/CHANGED/NO HISTORY)로 분리.
- NO REGIME 은 raw 후보일 뿐 확정 전까지 직전 공식 regime 유지. "Change" 는 공식 전환일에만, 그 외 "Transition watch RISK-ON → NO REGIME". REGIME DURATION(공식) vs RAW SIGNAL PERSISTENCE(raw) 이름 분리, Conviction 은 regime 과 별개(41% · MEDIUM · WEAKENING). MARKET READ 문장 템플릿(`cockpit.yaml now_read`). 오늘 셀은 LIVE 로 공식 regime 을 따라가고 장중 LOCK 없음.
- MARKET NOW 핵심 변수 문장의 조사("진정가" → "진정이")를 `fix_particles` 로 고침.

### 2026-10-07 — AI 센티2 표시 수정
- AI BASKET GROUPS 상대 %p 막대: 숫자를 막대가 없는 반대쪽 절반에 둔다(+ 는 왼쪽, − 는 오른쪽). 막대가 길어져도 숫자가 가려지지 않는다.
- EXPECTATIONS VS FUNDAMENTALS: 줄마다 "시장 기대 94 / 펀더멘털 64" 로 이름·숫자를 붙이고 gap 에 라벨, 범례에 각 축의 재료(가격: 상대 z·1개월·breadth / 뉴스 driver 톤·메모리·EPS)를 적었다. 계산은 그대로.

### 2026-10-07 — 탭 정리
- `실시간`(기존 그리드)·`AI 센티`·`메모리 업사이클` 탭 제거. 남은 탭(순서·이름 변경 후): 실시간 · AI 센티 · 금리 · 유가 · 평시 (실시간 2 → 실시간, AI 센티2 → AI 센티, 물가 충격 → 금리, 유가 급등 → 유가; `scenario_checks.yaml` title·키 순서). 기존 그리드는 cockpit Details 와 대체 화면으로, AI 기본 화면·반도체 합의 엔진은 `scenario_checks.yaml tab: false` 뒤에 그대로 남는다.

### 2026-10-12 — 10차 캡처 (연휴 뒤 첫 거래일, 15:09 KST 장중)
- 새 캡처 `data/captures/2026-10-12-manual/`. 수집·태깅·스냅샷 스크립트가 이제 이 폴더 안의 `build_manual_snapshot.py`(9/15 원본의 `run_tick` 을 옮긴 것)와 `manual_tags_v10.py` 만 읽는다 — 컨테이너 재시작으로 scratchpad 가 지워져도 다시 돌릴 수 있다. RSS 29건 + 웹검색 확인 미국 기사 2건 수기 태깅(LLM 없음).
- 실시간: 공식 regime RISK-ON → NO REGIME 전환(raw NEUTRAL 10/9 · 10/12 연속 2일). 코스피 −3.17%(13:00), 외국인 1.56조 순매도, OpenAI 매출 보도·후티/호르무즈. AI 센티 CONFIRMED AI RISK-ON / FUNDAMENTALS WEAK, 게이지 61. 금리 Term Premium, 유가 Geopolitical Premium.
- History: 10/7 LIVE → RECORDED(payload 동일), 10/8 · 10/9 BACKFILLED, 10/12 LIVE — 6개 탭 모두 과거 날짜 변경 없음을 HEAD 대비로 확인.
- ANALYST VIEW 수기 파일 `data/analyst_views/manual/2026-10-12.json`(SK하이닉스 메리츠 김선우, 삼성전자 KB 김동원 — 원문에서 확인된 것만).
- `cockpit.yaml` 의 전환 문장 두 개(`now_read.changed`, `history.transition.changed`)를 "(으)로" 대신 화살표로 — 영문 라벨 뒤 조사를 정할 수 없어 "NO REGIME(으)로" 가 그대로 보이던 것.

### 2026-10-12 — 금리 탭 상단 정리 + POLICY & MACRO EVENTS
- 순서: RATES REGIME → CURRENT RATES ANALYSIS → STATE HISTORY · 1M → POLICY & MACRO EVENTS → 기존 하단 그대로. `RatesRegime.top · current_analysis · events`(옛 캡처는 None → 예전 화면).
- REGIME: 방향(↓ FALLING) · LONG-END YIELD · TERM PREMIUM / SUPPLY DRIVEN · 10Y · CONFIDENCE · PRIMARY · INFLATION REPRICING, MARKET READ ≤2문장, DRIVER READ(PRIMARY −67 · COUNTER Growth +27 · NOT CONFIRMED Inflation / Fed Policy). 계산은 그대로(같은 입력이면 기존 필드 동일 — 확인).
- CURRENT RATES ANALYSIS: Driver DOMINANT · Bull Flattening / Long-end led · Real Yield ↓ · Breakeven ↓ + 한 줄, compact WHAT IS DRIVING RATES(누르면 근거).
- POLICY & MACRO EVENTS: FED 9/16 +25bp 3.75–4.00%(12–0) · ECB 9/10 +25bp 2.50% · BOJ 9/18 +25bp 1.25%(7–2) · BOK 8/27 +25bp 3.00%. 8월 CPI HOT(근원 0.3 vs 0.2, 2Y +7bp) · 8월 PCE COOL · 9월 NFP WEAK(29k vs 84k, 그래도 2Y +5bp · 10Y +4bp). 다음: CPI 10/14 · PPI 10/15 · BOK 10/22 · FOMC 10/27–28 · ECB 10/29 · BOJ 10/29–30 · NFP 11/6. 공식 사이트는 이 환경에서 막혀 둘 이상의 보도로 대조했다.

### 2026-10-13 — 12차 캡처 (09:12 KST 장 초반)
- 새 캡처 `data/captures/2026-10-13-manual/` · 태그 `manual_tags_v11.py`(RSS 29건, LLM 없음) · 정책 이벤트 `data/policy_events/2026-10-13.json`(BOK 총재 국감 발언 추가).
- Yahoo 가 10/12 일봉 종가를 null 로 두고 meta 에만 시장가를 준 계열(^KS11 · ^KQ11 · SOXX · XLU · XLK) — `YahooProvider.parse` 가 meta 시각과 같은 날짜의 빈 봉 하나만 meta 값으로 채운다(테스트 추가). 일시 실패로 오래된 CSV 로 떨어진 계열은 `refetch_stale.py` 로 한 번 더 받아 더 최근 봉이면 바꾼다(USDKRW).
- 실시간 NO REGIME 2일째 · 온도 −19, AI 센티 MACRO-DRAGGED AI WEAKNESS(반도체 사이클 −60), 금리 Term Premium 4일째, 유가 Geopolitical 2일째. History 10/12 LIVE → RECORDED(payload 동일), 10/13 LIVE.

### 2026-10-13 — 금리 탭 MARKET READ 를 LLM 투자 해석으로
- `ai/rates_read.py` + `config/rates_read.yaml`: 결정적 컨텍스트(금리 · 커브 · 실질/기대인플레 · 기간 프리미엄 proxy · regime · 매크로 실제치 · 정책 · cross-asset · 헤드라인, 계열별 OK/STALE/MISSING) → 구조화 출력 + 적응형 사고(`LLMClient.interpret`, 거절 시 서버측 대체 모델) → 검증(숫자 대조 · 개수 · 금지어 · 상투 문구 · 인과 단정 · 문장 수, 1회 재시도) → 실패 시 규칙 기반 + 이유.
- `RatesTop.market_read_meta`, 화면 `AI INTERPRETATION` / `RULE-BASED` 태그 · 테마 태그 · 데이터 주의. API 는 백그라운드 생성(그동안 '생성 중'), MOCK 은 생략.
- 규칙 기반 문장에서 "주된 원인은 …" · "아직 확인되지 않았습니다" · "반대 방향으로 뚜렷한 driver 는 없습니다" 를 뺐다.
- 오늘 API 호출은 계정 크레딧 부족(400)으로 실패 — 10/13 캡처의 MARKET READ 는 같은 컨텍스트·프롬프트·검증으로 세션에서 생성한 것이고 화면에 `세션 생성` 으로 표시된다. History 는 10/13 LIVE 행의 logic_version 만 바뀌었다(과거 행 변화 없음).

### 남은 것
- 롤오버 판정은 여전히 임계 기반이라 실제 2σ 충격도 물음표가 붙는다(다음 봉에서 풀린다).
- 컨센서스·수급·메모리 현물은 CSV 를 넣기 전까지 빈 채로 남는다.
- 정적 배포본은 서버가 없어 '지금 업데이트' 가 비활성.

---

## 커밋 이력 (최신순)

```
(이 커밋) NEW_EVENT 배지를 종목 지목 기사로 좁히고 롤오버 다음 봉 판정과 프런트 렌더 테스트를 더한다
50ab17f Real-data capture, manual commentary and polish for Investment Intelligence
2ddabcf Add Investment Intelligence tests and move remaining thresholds to config
b536584 Add Investment Intelligence layer below the existing dashboard
5996c23 docs: 세션 작업 정리 (2026-09-16)
6cc7962 2026-09-16 실데이터 3차 수기 캡처
c4c061a LLM 배지를 '뉴스 판단 없음/수기/API' 세 상태로 바꾸고 '지금 업데이트' 버튼을 단다
c210205 GOAL Kickstart 에서 빌린 여덟 가지를 화면과 엔진에 넣는다
3e3afae 모의 'AI 괴리' 탭을 'AI 센티' 로 바꾼다
c22bb7f 수급 신호를 끄고 그 자리를 뉴스 감성에 맡긴다
69212c2 좁은 화면에서 테마 히트맵의 테마명이 사라지던 것을 고친다
3d86fef 테마 히트맵 행을 누르면 관련 기사 4건이 펼쳐지고, 기사에 원문 링크를 단다
755c085 API 크레딧 없이 수기 태깅으로 뉴스 구조화 결과를 캡처한다
01dda86 LLM 없이 도는 괴리 테스트는 LLM 을 명시적으로 끈다
4b3ef46 LLM 실패 사유를 화면에 올리고 웹검색 타임아웃을 분리한다
f83ad5e LLM 켠 실데이터 캡처 3차 (2026-09-15)
800fa05 LLM 켠 실데이터 캡처 (2026-09-15) — SKIPPED
462eab6 MARKETPULSE_ANTHROPIC_API_KEY 로도 LLM 을 켤 수 있게 한다
017fa6d LLM 실데이터 캡처 미실행 기록 (2026-09-14): ANTHROPIC_API_KEY 미설정
19c9eb3 ANTHROPIC_API_KEY 가 있으면 LLM 을 자동으로 켠다
81bfca9 네트워크가 열린 뒤 드러난 실데이터 오류 셋을 고친다
f7a8d29 LLM 웹검색으로 기사를 찾고 센티멘트 온도계를 Market State 옆에 붙인다
645a053 과거 재생으로 신호를 채점하고 look-ahead 와 과신 두 건을 고친다
d87080b 베타: 막힌 네트워크에서 GitHub 미러로 실데이터를 붙인다
9f98157 CSV 적재 경로를 실사용 가능하게 고치고 목록을 정리한다
cf70a76 P4: 실데이터 어댑터 · RSS · WebSocket · 신호 백테스트
685b509 테마 방향과 감성 톤을 분리한다
14c8e3a Impact Map 레이아웃 교체 — 전파 단계 열 + 실측 반응
df1a07d P3: Impact Map · LLM 이벤트 추출 · AI 시장 요약
ace00ed feat(P2): Divergence · Alert · Confirmation Matrix · 저장소 · 스케줄러
2628e37 feat(P1): Market State Engine · Theme Score · Sentiment · 룰 추출
f92364d feat(P0): 대시보드 프론트엔드 + 실행 문서
bb16287 feat(P0): Market Pulse AI 데이터 계약·MOCK 파이프라인·API·CLI
4340d75 docs: Market Pulse AI 사전 분석 및 아키텍처 설계서 추가
32b7b36 Initial commit: upbit_cursor.py + upbit_trading 모듈
```

### 2026-10-13 — 금리 탭 아래 세 패널 재구성 + 분해 날짜 맞춤
- `engines/rates_panels.py` + `config/rates_panels.yaml` → `RatesRegime.inflation_map · curve_move · yield_breakdown`(옛 캡처 None → 예전 패널). 화면 `RatesLowerPanels.tsx`.
- INFLATION PRESSURE MAP: COOLING BIAS · PARTIAL(3/5), STATE → SCORE → EVIDENCE, DATA MISSING, 점수 눈금, READ 는 LLM(`ai/inflation_read.py`, 숫자 없음 검증) — 오늘은 API 크레딧 부족으로 세션 생성.
- TREASURY CURVE: 오늘·5D 전 곡선, 5D bp 모양 MILD BULL STEEPENING(2s10s +1bp)과 5D σ 이례성(10Y −0.9σ, 평소 범위)을 분리, 1D 모양(BULL FLATTENING, 2s10s −4bp)은 한 줄로 — 상단 칸은 하루 기준.
- YIELD MOVE BREAKDOWN: 5Y REAL YIELD ↓ · 10Y REAL + INFLATION EXP. ↓, MODEL REAL / OBSERVED TIPS 분리. 기대인플레가 하루 먼저 나오는 날 날짜가 섞이던 버그를 공통 날짜 맞춤으로 고쳤다(10Y 실질 +1 → −1, TIPS 와 일치).

### 2026-10-13 — 신뢰도 기반 macro fallback data layer
- `adapters/macro_fred.py` · `engines/macro_fallback.py` · `models/macro_data.py` · `config/macro_sources.yaml`. 급: PRIMARY(FRED API) → MIRROR(FRED CSV) → SECONDARY(보도 확인 수기 파일) → PROXY(대체 조합) → UNAVAILABLE, NEWS 는 별도 펄스.
- 10/13: CPI 3.35% · Core CPI 2.45% · PCE 3.42% · Core PCE 3.01%(YoY, FRED SA) — 모두 PRIMARY(BLS 9/11 · BEA 9/30 발표). 3M 연율은 CPI 0.2% · PCE 1.0% → Realized Inflation COOLING −72.
- Wage / Services PROXY −41 EASING(AHE · ECI · Services CPI · Core Services PCE, 모두 PRIMARY 입력) — "둔화 속도가 전체 물가보다 느림". Inflation News Pulse MILD UPWARD +15(NEWS, 신호 미반영).
- INFLATION SIGNAL COOLING BIAS · PARTIAL · Official data 4/5 · Proxy 1 · News 1. 물가 압력 해석은 크레딧 부족으로 세션 생성(출처 급 규칙 포함 프롬프트·검증 통과).
- History: 10/13 LIVE 행의 inflation:realized · wages 점수만 채워졌다(과거 행 변화 없음).

### 2026-10-14 — 13차 캡처 (10:26 KST 장 초반)
- 새 캡처 `data/captures/2026-10-14-manual/` · 태그 `manual_tags_v12.py`(RSS 30건, LLM 없음) · 정책 이벤트 `data/policy_events/2026-10-14.json`(9월 CPI 발표 시각 · CNBC 컨센서스 추가).
- 보정: `fill_prev_close.py` — Yahoo 일봉에서 10/13 봉이 통째로 빈 계열을 같은 공급자의 previousClose 로 하나만 채움(코스피 6,035.35 = 보도 종가). 환율(=X)·휴장 이월값(MOVE)은 제외 규칙. `refetch_fx.py` — 환율 3종 단독 재수집.
- 버그 수정: `adapters/macro_fred.py` 의 FRED realtime 날짜를 미국 중부시간으로(한국 오전 실행 시 400) · `policy_events` 의 오늘 일정은 `release_utc` 전까지 UPCOMING 에 남김 · cockpit NEUTRAL 문장의 "없지만 있지만" 중복.
- 실시간 NO REGIME 3일째 · 온도 −7, AI TRADE MIXED, 금리 Term Premium 5일째(INFLATION SIGNAL MIXED — 환율 전가 +32), 유가 Supply. History 10/13 LIVE → RECORDED(payload 동일), 10/14 LIVE.

### 2026-10-15 — 14차 캡처 (08:32 KST 개장 전)
- 새 캡처 `data/captures/2026-10-15-manual/` · 태그 `manual_tags_v13.py`(RSS 28건, LLM 없음) · 정책 이벤트 `data/policy_events/2026-10-15.json`(9월 CPI 결과 — 전년 3.7% vs 3.6%, 근원 2.6% · 0.3% 상회; 헤드라인 전월치는 FRED 지수로 확인).
- 버그 수정: `load_events_file` 이 시각을 받으면 한국 날짜로 파일을 고른다(`policy_events.yaml file_timezone`) — UTC 날짜로 찾으면 한국 오전에 하루 전 파일을 읽었다. 테스트 추가. `fetch_macro.py` 는 live.json 대신 fetch_report 의 as_of 로 돈다.
- 실시간 NO REGIME → LIQUIDITY STRESS(92%), AI-specific De-risking, 금리 RISK-OFF FLIGHT TO QUALITY(위험·유동성 −59), 물가 압력 MIXED(기대인플레 +48 · 실제 물가 −25), 유가 Supply.
- History: 스냅샷 날짜가 UTC 라 이 수집은 10/14 의 마감 기록 — 10/14 LIVE(잠기지 않음)가 마감 데이터로 RECORDED 확정·잠금. 잠긴 행 변화 없음(HEAD 대비 확인).

### 2026-10-15 — AI 탭 데스크톱 전용 레이아웃
- 범위: `@media (min-width: 1100px)` 와 확장 AI 탭 루트 `.ai.ai-ext` 에만 적용(`theme/layout.css` 끝). 1100px 미만 규칙·카드 구성·순서·문구·접힘은 그대로. 분석·데이터·history 로직 변경 없음.
- 원인: 전역 `.span-3` 가 1400px 이상에서만 켜져 1101~1399px 에서 큰 섹션이 3열 그리드의 한 칸(≈419px)으로 떨어짐 → 글자가 세로로 끊기고(Driver verdict) 가로 스크롤(1280px 에서 scrollWidth 1390) 발생.
- 데스크톱 흐름(최대 2열, `grid-template-areas`): AI Trade Regime(왼쪽 regime·핵심 수치 / 오른쪽 Regime Read·Key tension / 아래 상태 타일 5열) → Sentiment | Regime History(History 는 sticky) → AI vs Market(35/65) → What Is Driving AI?(verdict + 2열 카드, 증거·Price check 는 카드를 펼칠 때) → Chain Snapshot → Transmission | Expectations vs Fundamentals → Semiconductor Confirmation → Value-Chain Leadership → Basket Groups → Breadth → Stock Impact Map(2열) → Stock Radar(2열) → News(점수·헤드라인 | value chain·종목·가격 반응 한 줄, 상세는 클릭) → Narrative × Price → Macro Confirmation(FACTOR·MOVE·EXPECTED AI IMPACT·STATUS 머리줄) → Stress → What Matters → What Changes → Details.
- DOM: 루트에 `ai-ext` 클래스, DriverCard 섹션에 `dv-sec-ev`·`dv-sec-pc` 훅 클래스, Macro 표 머리줄 `.ai-mac-h.desktop-only`(1100px 미만에서는 `display: none`).
- 검증: 390/430/768px 전체 화면 스크린샷 해시·모든 요소 위치/크기/글꼴/여백 해시가 변경 전과 동일. 1100/1280/1440/1920px 가로 스크롤 없음, 세로 글자 없음. vitest 95개 통과.
- 후속: Sentiment · Regime History 를 좌우 2열에서 각각 전체 폭 단독 섹션으로 세로 배치(State → Sentiment → History → AI vs Market). History 의 sticky 를 없애고 `position: static !important` 로 명시 — 스크롤을 따라붙지 않는다. 전체 폭 Sentiment 아래 줄은 원래 3칸(drivers | 1M | Read)이라 1M 차트가 과하게 커지지 않는다. 카드 간격 16px. 390/430/768px 해시 동일.

### 2026-10-21 — Daily Full Dashboard Archive + 날짜별 과거 화면 조회 (P1)
- 역할 분리: 기존 daily history(`data/history`, DailySnapshotManager · locked snapshot)는 그대로 — 탭별 상태 strip 용 일별 판정 기록. 새 archive(`data/archive/YYYY/MM/YYYY-MM-DD.json`)는 그날 **화면 전체**를 재현하는 저장본 — 대시보드가 쓰는 API 응답 전체(snapshot · cockpit · market_state_history · ai/rates/oil regime · investment · scenario_checks · analyst_views · daily_history · news)를 날짜별 JSON 하나로. HTML 이 아니라 raw 응답이라 UI 가 바뀌어도 재사용된다.
- 백엔드: `marketpulse/archive/`(store · service · collect · CLI), `config/archive.yaml`(schema_version "1" · archive_time 07:30 · Asia/Seoul · weekdays_only · bundle_max_dates 8), `settings.archive_dir`. 쓰기는 `.tmp` → 재검증 → hard link(같은 날짜가 있으면 실패) — 정기 저장은 절대 덮어쓰지 않고, `correct` 만 교체하며 이전 파일은 `superseded/`, `meta.corrections` 에 이유·작성자. 섹션 실패는 null + `errors` + `archive_status: PARTIAL`, snapshot 실패는 파일을 남기지 않는다. 하위 섹션 as_of 가 snapshot 과 다르면 `meta.consistency.mismatched` 에 남기고 PARTIAL(investment 는 자기 계산 시각이라 snapshot 뒤 900초 안 허용).
- API(읽기 전용): `GET /api/v1/archive/dates` · `/index` · `/latest` · `/{date}`(없으면 404 + 가장 가까운 저장일). 저장은 HTTP 로 열지 않는다 — `python -m marketpulse.archive capture [--if-due]`, 스케줄러 `--archive`, `.github/workflows/daily-archive.yml`(평일 07:35 KST, 기본 브랜치에서만).
- 첫 저장본: 커밋된 캡처 디렉터리 10/12~10/15 를 `import-capture` 로 가져옴(created_by `capture_import:…`, generated_at = snapshot.as_of).
- 프론트: ARCHIVE MODE 에서는 모든 API 호출(`client.get`, `useInvestment`)이 저장본에서 답을 받는다 — 없는 섹션은 NOT ARCHIVED 로 실패하고 지금 값으로 메우지 않는다. 화면 본체는 모드별 key 로 다시 마운트(LIVE 상태가 섞이지 않음). 폴링(5초 snapshot · 60초 investment) 없음, '지금 업데이트' 숨김. 상단 바 `[● LIVE ▾]` / `[ARCHIVE 2026-10-15 ▾]` — 저장 목록 · 날짜 입력 · 이전/다음 저장일, 좁은 화면은 아래 시트. 과거 화면 띠(데이터 기준 · 저장 시각 · PARTIAL · 없는 섹션 · LIVE로 돌아가기). 주소 `#2026-10-15` 로 바로 열기. 정적 배포본은 최근 저장본을 함께 넣고 archive 경로도 가로챈다.
- 테스트: pytest `tests/test_archive.py` 11개(저장 · 덮어쓰기 금지 · 부분 실패 · 필수 실패 시 파일 없음 · as_of 불일치 · due · correction · 날짜 정렬 · 404 · 쓰기 엔드포인트 없음), vitest `archive.test.tsx` 6개. P2(History 날짜 클릭 연동 · correction UI · diff)는 이번에 하지 않음.

### 2026-10-21 — Daily Snapshot 정비: 평일만 · 누락 평일 backfill · 날짜 탐색
- 조사(작업 전): daily history(`data/history`, JsonDirStore · 탭별 JSON, SQLite 미사용)는 09/04~10/14(UTC 날짜) 6개 탭 모두 LOCKED. full archive 는 10/12~10/15(KST 날짜, 커밋된 캡처에서 가져옴). 누락 평일 10/16 · 10/19 · 10/20 · 10/21, 주말 10/17 · 10/18. 화면이 10/15 를 보인 이유는 정적 배포본의 LIVE 데이터가 10/15 캡처였기 때문(하드코딩된 선택 날짜 없음).
- 평일 규칙: `archive.is_snapshot_day`(weekday < 5, `holidays` 확장 자리) — 정기 저장·backfill·수동 capture 모두 토·일이면 SKIPPED. history 도 `weekdays_only` — 한국 월요일 07:30(= UTC 일요일) 기록은 만들지 않고 금요일 미국 장은 다음 계산의 backfill 이 채운다. 이미 있는 주말 파일은 그대로.
- backfill(`archive/backfill.py` · `reconstruct.py` · `pit.py`): `plan` 이 기존 최소 날짜~until 을 EXISTING / MISSING / SKIPPED_WEEKEND 로 나누고, MISSING 만 오름차순으로 그 날짜 07:30 KST cutoff 재구성 → 미래 데이터 검증 → 원자적 저장. 시계열은 지금 한 번 받아 '봉이 끝나 공개된 시각 ≤ cutoff' 만 남긴다(미국·아시아 주식 개장+7h, 유럽 +9h, VIX +14h, 선물 +18h, 환율 +24h, FRED 금리는 다음 평일 22:00Z). 거시 지표는 FRED realtime(그날 vintage), 기사는 발행 시각 ≤ cutoff(날짜만 확인된 웹 기사 1건은 그날 미국 동부 자정으로 보수적 배치, DATE_ONLY 표시), Analyst View 는 그 날짜 이전 수기 파일만, 해설은 그 뒤 작성분 제외. LLM API 는 인증 실패라 금리 MARKET READ · 물가 해석은 그 날짜 컨텍스트만으로 같은 프롬프트·검증을 통과한 세션 생성본.
- 결과: 10/16 · 10/19 · 10/20 historical_backfill COMPLETE, 10/21 latest_update COMPLETE(16:00 KST 데이터). 기존 저장본 4개·잠긴 history 168행 바이트 동일. 새 history 30행(10/15~10/20 RECORDED/BACKFILLED 잠금, 10/21 LIVE — 내일 07:30 실행이 미국 마감으로 확정). 과거 저장본의 cutoff 이후 시각은 처리 시각(computed_at)과 예정 일정뿐.
- 화면: 상단 `[◀][2026-10-21 ▾][▶][LIVE]`(좁은 화면은 `[날짜 ▾][LIVE]`) · 날짜 검색(주말이면 '토요일로 Daily Snapshot 생성 대상이 아닙니다' + 이전·다음 저장일) · 달력(저장된 평일만 선택, 토·일 비활성) · `?date=` 로 새로고침·공유·뒤로가기 유지 · 과거 화면 폴링 없음. 감사용 스크린샷 `data/archive/screenshots/YYYY-MM-DD.jpg`(ARCHIVE MODE 렌더링).
- 운영: `.github/workflows/daily-archive.yml` cron `30 22 * * 0-4`(= 평일 07:30 KST) → `capture --if-due`(앱에서 요일 재확인) → `validate` → 커밋. index.json = {latest, dates, entries}.

### 2026-10-21 — History 날짜 기준: KST Daily Snapshot 날짜 / 미국 장 날짜 분리
- 원인: history 저장 키(`snapshot_date`)는 as_of 의 **UTC 날짜**다. 07:30 KST 기록은 전날 UTC 날짜 행(= 그 미국 장)이 되고, KST 낮에 돈 기록은 그날 UTC 날짜 행(미국은 전날 종가)이 된다. 그래서 (1) 10/20 화면의 끝 칸은 '10/19', 10/21(16:00 KST 저장) 화면은 '10/20 BACKFILLED + 10/21 LIVE' 두 칸으로 끝났고, (2) 키는 달라도 같은 미국 장을 쓴 행이 겹쳤다(09/14·09/15, 09/17·09/18, 09/22·09/23, 09/25·09/28, 10/05·10/06, 10/09·10/12, 10/20·10/21 LIVE). 10/20 화면의 '10/19' 두 번은 저장 중복이 아니라 마지막 칸의 전환 ▲ 날짜 글자와 끝 날짜 라벨이 같은 칸을 가리킨 것, 10/21 화면의 겹침은 10/19 전환 ▲ 글자가 끝 라벨 10/21 과 맞닿은 것.
- 규칙(`history/dates.py`, `history.yaml date_view`): market_date = data_asof 에 이미 끝난 미국 정규장(16:00 ET, 평일), snapshot 날짜 = market_date 다음 평일(= 그 종가를 처음 반영하는 KST 07:30 Daily Snapshot). 같은 snapshot 날짜의 저장 행은 하나 — 맨 끝 LIVE 는 daily 에서 빼 intraday 로, 그 밖은 RECORDED > BACKFILLED > 07:30 에 가까운 것. 빠진 행은 `merged` 에, 저장 행이 없는 평일은 `gaps` 에(값을 채우지 않음).
- 적용: 저장 데이터·아카이브 파일은 그대로. 화면 view 만 — 새로 조립하는 history(`assemble.py` 의 state/daily/sentiment view, cockpit regime history)는 처음부터 KST 날짜, 예전 저장본은 `/api/v1/archive/*` 가 읽을 때 `history/legacy_view.py` 로 바꿔 보낸다(`?view=stored` 면 파일 그대로). 날짜별 값(판정·확신·점수·factor)은 저장 행 그대로이고, 구간·전환·비중·공식(display) regime 은 그 daily 점에서 같은 규칙으로 다시 센다. 실시간 MARKET NOW 의 공식 판정은 daily 뒤에 장중 LIVE 를 이어 본 결과(`include_intraday`) — 장중 값은 daily 칸을 덮지 않는다.
- 화면: Market Regime History 에 `Daily Snapshot 2026-10-21 · Cutoff 07:30 KST · US data through 2026-10-20 close`, 장중 LIVE 줄(시각 · raw · 장중 공식 · daily 에 넣지 않음), 저장 snapshot 없는 평일 각주. x축은 KST 날짜 한 기준 — 칸이 30px 라벨보다 넉넉하면 모든 날짜, 아니면 첫·끝을 두고 고르게 솎음(라벨만, 칸은 그대로), 전환 ▲ 는 글자 없이, 같은 날짜 라벨은 한 번(데이터에 중복이 오면 경고 줄). 툴팁·상세에 `Snapshot 10/21 KST · US 10/20 close · data 10/21 08:59 KST · 저장 키`. 공용 strip 들도 같은 날짜·intraday·각주.
- 결과: 10/20 화면 …10/15 · 10/16 · 10/19 · 10/20, 10/21 화면 …10/16 · 10/19 · 10/20 · 10/21(+ 장중 LIVE 16:00 KST 별도). 테스트 pytest `test_history_dates.py` 12개(전체 835 통과), vitest `historyDates.test.tsx` 6개(전체 111 통과).
- 남은 것(승인 전 미실행): 10/21 아카이브는 cutoff 16:00:21 KST 의 latest_update — Daily Snapshot 규칙(07:30 KST)과 다르다(correction 후보). 저장 키가 UTC 날짜라 KST 낮의 기록이 잠기면 다음 날 07:30 snapshot 이 빠지는 구조(09/21 · 09/24 · 09/30 · 10/08 · 10/14 공백의 원인) — 저장 키를 KST snapshot 날짜로 바꾸는 것은 별도 결정.

### 2026-10-22 — 되돌림(V79) + 10/22 Daily Snapshot
- 되돌림: 대시보드를 V79 화면(853fa1d 빌드)으로 되돌리고(아티팩트 V81), 저장소도 af6b486 을 revert(7aecf23)해 화면과 코드를 맞췄다. 10/22 는 V79 코드로 만들었다.
- FRED 점검(04:22~04:48 UTC 무렵 응답 HTML 점검 페이지)으로 기대인플레·TIPS·HY OAS·거시 발표값을 받을 수 없어, 복구를 기다린 뒤 입력을 다시 받았다(기본 41/54 · 종목 94 · AI 바스켓 52 · RSS 123).
- 10/22 07:30 KST cutoff 재구성(`build_one`, latest=False → historical_backfill · `data/captures/2026-10-22-backfill/`): 미국 10/21 종가 · 한국 10/21 종가 · 미국채/TIPS/BE/HY OAS 는 FRED 다음 평일 22:00Z 규칙으로 10/20 관측까지. RSS 창 10/21 07:00Z~10/21 22:30Z 53건 중 19건 수기 태깅. 금리 MARKET READ · 물가 해석은 API 401 이라 같은 컨텍스트·검증의 세션 생성본.
- 결과: 시장 NEUTRAL 34%(온도 +11) · 10/21·10/22 두 Daily Snapshot 연속 Neutral → 공식 Risk-On → Neutral / Mixed 전환(MARKET NOW 와 History 같은 값 — 07:30 저장이라 장중 LIVE 없음). AI LEADERSHIP NARROWING(센티 61), 금리 LONG-END RATE / TERM PREMIUM SHOCK(물가 리프라이싱 미확인, 강세 평탄화), 물가 압력 MIXED, 유가 Supply UNCONFIRMED.
- history: 10/21 LIVE 6행이 07:30 기록으로 RECORDED·잠금(data_asof 10/21 22:30Z = 10/22 07:30 KST → 화면 날짜 10/22). 그 밖의 잠긴 행 · 기존 아카이브 9개 바이트 동일. 아카이브 COMPLETE · validate 통과 · 미래 데이터 검증 통과. 감사용 스크린샷 `data/archive/screenshots/2026-10-22.jpg`.

### 2026-10-22 — History 는 저장 당시 그대로 (KST 날짜 view 철회)
- 사용자 확인: 10/15 화면의 History 가 발표 자료(PPT)의 원래 화면과 달랐다(9월 말 Liquidity Stress 구간이 Risk-On 으로). 원인은 10/21 의 KST 날짜 view — 같은 미국 장을 쓴 저장 행 6쌍 중 하나를 버리면서(예: 9/28 칸에서 미국 9/25 종가 Liquidity 80% 대신 그날 오후 기록 Neutral) 이틀 연속 조건이 깨졌고, 화면마다 계산 시작일도 달랐다.
- 결정(옵션 1): History 는 저장 키(as_of 의 UTC 날짜 — 대부분 미국 장 날짜) 기준, 저장 당시 판정 그대로. 853fa1d 의 백엔드(assemble · integrate · regime_history · cockpit · history.yaml date_view · legacy_view · dates)를 그 이전으로 되돌렸다. 프론트의 x축 정리(폭 기반 라벨 솎기 · ▲ 글자 제거 · 중복 라벨 경고)는 유지 — KST 전용 칸(Daily Snapshot 줄 · 장중 줄 · 공백 각주)은 date_basis 가 kst_snapshot 일 때만 보여서 지금은 나오지 않는다.
- 10/22 저장본(그 사이 KST view 로 저장됨)은 파일을 고치지 않고, 읽을 때 같은 날짜까지의 잠긴 저장 기록으로 예전 방식 history 를 다시 조립한다(`history/storage_view.py` — API `/api/v1/archive/*` 와 정적 배포본, `?view=stored` 면 파일 그대로). MARKET NOW 등 나머지 섹션은 저장본 그대로.
- 결과: 10/15 = 발표 자료와 같은 화면(Liquidity Stress · 전환 6 · 비중 36%). 10/20 끝 10/19, 10/21 · 10/22 끝 10/21(10/22 07:30 기록 = 미국 10/21 종가). 같은 날짜의 판정은 화면 사이에 같고, 다른 것은 각 화면 첫 칸뿐(계산 시작점). 테스트 `test_storage_view.py`.
- 후속(같은 날): 10/22 화면의 MARKET NOW 'Official regime · 1M' 띠가 10/21 화면과 달랐다 — 10/22 저장본의 MARKET NOW 는 KST view 로 계산돼 저장됐고(09/15 시작 · 9월 말 Risk-On), storage_view 가 History 섹션만 다시 조립했기 때문. MARKET NOW 의 history 파생 칸을 `cockpit.now_history_fields` 로 분리해 build_cockpit 과 storage_view 가 같이 쓴다 — 10/22 의 띠·지속·전환 문장이 History 와 같은 sequence(09/22~10/21)가 됐다(판정 라벨·핵심 변수·해석은 저장본 그대로, 바뀐 칸은 띠뿐). 10/21 · 10/22 화면에서 같은 날짜의 띠 색이 모두 같다.

### 2026-10-23 — 10/23 Daily Snapshot (07:30 KST)
- 입력: 23:53Z 수집(기본 41/54 · 종목 94 · AI 바스켓 52 · RSS 138, FRED 정상). 07:30 KST cutoff 재구성(`data/captures/2026-10-23-backfill/`) — 미국 10/22 종가 · 한국 10/22 종가 · 미국채/TIPS/BE/HY OAS 10/21 관측까지. RSS 창(10/22 07:30~10/23 07:30 KST) 88건 중 19건 수기 태깅. 금리 MARKET READ · 물가 해석은 API 401 이라 같은 컨텍스트·검증의 세션 생성본.
- 결과: 시장 raw RISK_OFF 49%(온도 −34) — 나스닥 −2.9% · 반도체(SOXX) −6.8% · VIX +14% · 코스피 −3.5%. 공식 regime 은 Neutral / Mixed 유지(2일째), Liquidity Stress / Risk-Off 후보 1일(TRANSITION WATCH) — MARKET NOW 와 History 같은 값. AI-SPECIFIC DE-RISKING(센티 30), 금리 GROWTH-LED RATES(물가 리프라이싱 반박), 물가 압력 MIXED, 유가 Demand CONTRADICTED(브렌트 +4%).
- history: 10/22 LIVE 없이 07:30 기록으로 6개 탭 RECORDED·잠금(data_asof 10/22 22:30Z). 다른 잠긴 행 · 기존 아카이브 10개 바이트 동일. 아카이브 COMPLETE · validate · 미래 데이터 검증 통과. 10/22 · 10/23 화면의 같은 날짜 History · Official regime 띠 차이 0. 스크린샷 `data/archive/screenshots/2026-10-23.jpg`.

### 2026-10-23 — 반도체 사이클 탭 (P1)
- 새 탭 '반도체 사이클'(AI 센티 다음). 다른 탭의 계산·화면은 손대지 않았다 — 별도 엔진(`engines/semiconductor_cycle.py`) · 설정(`config/semiconductor_cycle.yaml`) · 서비스(`api/semi_service.py`) · 라우트(`GET /api/v1/semiconductor-cycle`) · 화면(`SemiconductorCycleView.tsx` · `theme/semiconductor.css`).
- 데이터: DRAMeXchange 공개 홈 현물(DDR5 16Gb · DDR4 16/8Gb · eTT 3종 · NAND TLC 웨이퍼 3종)과 계약가(DRAM 칩·모듈, NAND MLC)를 기존 수집기에 `--only semi` 로 붙였다(`data/semiconductor/{spot,contract}`, 공개 시각 updated_at 기준 PIT). HBM3E/HBM4 앵커는 기존 replay CSV, 한국 반도체 수출은 관세청·산업부 발표의 인용 보도(`data/semiconductor/exports.json` — 공식 사이트는 이 환경에서 막혀 있다). EPS·ASP·재고·가동률은 공급원이 없어 NO DATA.
- Spot Premium = 현물 ÷ 그 시점까지 공개된 비교 가능 계약가 − 1. DDR4 16/8Gb = 같은 칩(HIGH), DDR5 16Gb = 8GB SO-DIMM 계약가 ÷ 4칩(LOW → PROXY PREMIUM, 가중 0.4), NAND TLC = 비교 계약 없음(계산 안 함). 계약 기준월 표시 · 45일 넘으면 STALE.
- 수출 나우캐스트: 1~20일(또는 1~10일) 누적 + 남은 조업일 × 일평균 페이스 × 월말 배수(작년 같은 달·직전 확정 달의 21일~말일/1~20일 일평균 비, 평균=중심 · 최소~최대=범위). 10월: 중심 552.7억$(YoY +251%, 범위 +188~+315%), 1~20일 일평균 YoY +160.5%, 1~10일 기준 대비 수정 −16.8pp. 단가·물량 분해는 공식 통계가 없어 정성 표시만.
- 국면: 증거 9개(−100~+100)의 가중 평균. 없는 증거는 분모에서 빼고, 확보 비율 < 0.4 이거나 메모리 가격 증거가 없으면 INSUFFICIENT DATA. 10/23: UPSWING(composite +37, 신뢰도 45) — 현물 프리미엄 큼·HBM 앵커 상승·수출 강세 vs 메모리주 1M −22~−34%(DIVERGENCE)·계약가 STALE.
- Market Read: API 401 → 같은 컨텍스트·프롬프트·검증(숫자 대조·금지어·2~4문장)의 세션 생성본, 없으면 규칙 문장. History: 새 daily snapshot 탭 `semiconductor_cycle` — 10/22(=10/23 07:30) RECORDED, 그 전 21거래일은 그 날짜까지 공개된 가격·수출·주가로 1회 BACKFILLED(뉴스 제외) 후 잠금.
- Archive: `semiconductor_cycle` 섹션 추가(07:30 재구성 13단계 · live collector). 기존 저장본 10개는 그대로 — 그 날짜들은 'SEMICONDUCTOR CYCLE NOT ARCHIVED FOR THIS DATE'(지금 값으로 메우지 않는다). 10/23 저장본에 넣으려면 승인 후 correction 경로로만.
- 테스트: 백엔드 `test_semiconductor_cycle.py` 25개(+ archive 픽스처에 새 섹션), 프론트 `semiconductor.test.tsx` 13개. 데스크톱 2열 · 모바일 1열(제품 드롭다운), 가로 넘침 0.

### 2026-10-23 — 반도체 사이클: 1년 가격 이력(Spot · Contract · Premium)
- 조사: DRAMeXchange 공식 과거 차트(chart.dramexchange.com)는 MI 회원 전용, TrendForce 가격 페이지의 page=N 은 과거가 아니다. 공개 원천은 DRAMeXchange **Daily Express**(매 거래일 시황, 이 세션에서 접근)와 TrendForce **주간 Memory Spot Price Update** 기사(이 세션 네트워크 차단 → GitHub Actions 러너로 수집).
- 저장(`data/memory_history/`, 데일리 아카이브와 분리): dram/DDR4_8G_SPOT · DDR4_8G_ETT_SPOT(2025-03-04~, Daily Express 407 + 주간 50), nand/NAND_512G_TLC_WAFER(2025-08-06~, 주간 48), contract/DDR4_8G_CONTRACT(2025-07~2026-09 월간, DRAMeXchange 홈 + 보도 인용 · 출처 링크 · 전월 대비 변화율 연쇄 일치). 행마다 관측일 · 공개 시각 · 출처 URL · 원문 문장. 연도 오기 글 2건 제외, 중복 0, 10배 급변 0, 주간값과 일간값의 날짜 귀속 차이는 충돌로 세지 않음(`validation.json`).
- 계산: RAW SOURCE HISTORY 와 평일 DAILY MARKET STATE(그날까지 공개된 최근 값, 갱신 사이 CARRIED_FORWARD)를 분리. 계약가는 공개 뒤부터 다음 공개 전까지 anchor(9월분은 10/3 보도부터). Premium(t)=그날 알려진 현물÷그날 알려진 계약가−1. 1Y z-score·percentile 은 RAW premium 20개 이상일 때만(DDR4 8Gb: RAW 248 → z −0.75 · 33%). 변화율 기준일 관측이 오래되거나 그 사이 새 관측이 없으면 계산하지 않음. MA20/60 · 6M · 1Y · 전환점(EARLY TIGHTENING/SOFTENING) 추가.
- coverage: DDR4 8Gb · DDR4 8Gb eTT = 1M/3M/6M/1Y GOOD. NAND 512Gb = 1M/3M GOOD, 6M/1Y PARTIAL(2026-04-13~05-13 30일 공백 — 그 주 기사에 웨이퍼 문장 없음). DDR5 16Gb(2026-09-29~) · DDR4 16Gb · NAND 256/128Gb = PARTIAL(공개 과거 출처 없음, 다른 제품 값으로 메우지 않음). DDR5 8Gb 는 공개 원천 없음.
- 화면: 기본 제품 = 1Y GOOD 인 DDR4 8Gb · 기본 기간 1Y. 현물 실선 · 계약 anchor 점선 계단(토글) · premium 옅은 면(우축) · 툴팁에 원천 관측일과 RAW/CARRIED_FORWARD. 기간별 coverage 와 PARTIAL 사유, Data Quality 에 제품별 coverage 표. 과거 날짜 화면은 그날 as_of 로 잘린 값만(2026-04-01 기준이면 차트 끝 4/01 · 계약 anchor 2월분).
- 수집: `collect-memory-history` workflow(평일 04:10 UTC) — Daily Express 새 글 · TrendForce 주간 기사, append-only. 10/23 캡처의 반도체 섹션을 새 엔진으로 다시 만들었고(UPSWING 44.5), 잠긴 10/22 history 행(UPSWING 37.3, 이전 엔진)은 그대로다.

### 2026-10-26 — 반도체 사이클: DDR5 · NAND 1Y 이력 — 보존된 공개 화면으로 재구성
- 원칙: 유료 DRAMeXchange Historical Download · 회원 페이지 · 로그인은 쓰지 않는다(환경변수·credential 에 DRAMeXchange/TrendForce 라이선스 접근 없음 확인). chart 이미지 OCR 없음. Internet Archive 에 보존된 **공개 화면**(dramexchange.com 홈, trendforce.com/price/dram/dram_spot · /price/flash/wafer_spot)에 그날 표시된 표 값만 — 행의 'Last Update' 시각이 관측일·공개 시각, 캡처보다 늦은 시각은 버림.
- 저장: 행마다 `source_type`(DIRECT_PUBLIC_REPORT/ARTICLE/SNAPSHOT · ARCHIVED_PUBLIC_SNAPSHOT) · `grade`(A 직접 공개 · B 보존 공개 · C 공개 고정 참고 · D 보도 인용 · E 기타) · `archive_url` · `original_url` · `snapshot_timestamp`. source 를 하나의 RAW 로 섞지 않고 같은 날은 순위로 하나만 쓴다. 엔진 RAW 는 A/B 만. 공개 월간 참고값(DDR5 16Gb 2026-05 계약 +7.1%, ZDNet 이 인용한 TrendForce · D)은 `memory_history/validation/` 에 따로 — 대조만(raw +6.84% → CONSISTENT).
- 수집(`collect-memory-history`): 보존본 단계를 대상마다 나누고 5개마다 저장, 표 없는 캡처는 `archive_empty.txt` 에 적고 같은 날 더 이른 캡처(최대 4개)를 읽는다. 검증 보고가 실패해도 읽은 행은 커밋(검증 보고가 validation/ 참고값을 RAW 로 읽어 실패하던 버그 수정).
- coverage 점수: 기간 40% · 주간 밀도 30% · 원천 등급 20% · 공백 10%. GOOD = 1Y 의 90% 이상을 덮고 관측 주 85% 이상, 모든 달에 관측이 있으면 MONTHLY COVERAGE GOOD. 분류 FULL(A 위주 원천 그대로) / RECONSTRUCTED GOOD(보존본 비중 25% 이상) / PARTIAL / UNAVAILABLE.
- 결과(as_of 2026-10-22 22:30Z): DDR4 8Gb FULL(RAW 251, 52/53주). DDR5 16Gb 2025-07-01~ RECONSTRUCTED GOOD(RAW 109/평일 261, 46/53주, 최대 공백 20일, B 104 · A 5). NAND 512Gb RECONSTRUCTED GOOD(RAW 63/53, 49/53주, 공백 14일, A 40 · B 23). NAND 256/128Gb PARTIAL · MONTHLY COVERAGE GOOD(RAW 43, 43/53주, 공백 21일 — 보존본이 없는 주는 빈 칸). DDR4 16Gb PARTIAL(보존된 공개 표에서 2026-02 부터).
- 화면: 차트 위 1Y HISTORY 줄(분류 · RAW 수 · 원천 · Internet Archive 비중) · VALIDATION 줄, coverage 표에 RAW/기대 · 관측 주 · 최대 공백 · 분류. 차트 기본 제품은 FULL 이력(DDR4 8Gb).
- 10/23 캡처 반도체 섹션 재생성(UPSWING 46.2) · 세션 Market Read 를 새 컨텍스트로 다시 써 같은 검증 통과. 잠긴 history 행은 그대로.

### 2026-10-26 — 10/26 Daily Snapshot (07:30 KST)
- 입력: 05:53Z 수집(기본 41/54 · 종목 94 · AI 바스켓 52 · RSS 117, FRED 정상). 07:30 KST cutoff 재구성(`data/captures/2026-10-26-backfill/`) — 미국 10/23(금) 종가 · 한국 10/23 종가 · 미국채/TIPS/HY OAS 10/22 관측까지(10/23 관측은 cutoff 뒤 공개). 주말을 포함한 RSS 창(10/23 07:30~10/26 07:30 KST) 47건 중 22건 수기 태깅. 금리 MARKET READ · 물가 해석 · 반도체 MARKET READ 는 API 401 이라 같은 컨텍스트·검증의 세션 생성본. DRAMeXchange 공개 홈 표를 다시 받았고, 10/26 11:00(GMT+8) 갱신분은 cutoff 뒤라 화면에 들어가지 않는다(DDR5 16Gb 마지막 값 = 10/23 $61.267).
- 결과: 시장 raw LIQUIDITY_STRESS 52.5%(온도 −22) — S&P −0.5% · 나스닥 보합 · SOXX +0.5% · VIX +2.2% · 브렌트 +3.1% · 금 −1.3% · 코스피 +0.3% · 코스닥 −1.6%, 하이일드 스프레드 확대. 공식 regime 은 Neutral / Mixed → Liquidity Stress / Risk-Off(CHANGED, 1일) — MARKET NOW 와 History 같은 값. AI MACRO-DRAGGED AI WEAKNESS, 금리 LONG-END RATE / TERM PREMIUM SHOCK(물가 리프라이싱 미확인, 10/22 미국채 전 구간 급락), 물가 압력 MIXED, 유가 Supply CONFIRMED, 반도체 사이클 UPSWING 45.2.
- history: 10/23(금) 행은 6개 탭 + 반도체 탭 BACKFILLED·잠금(data_asof 10/23 23:59:59Z — 10/16 금요일과 같은 규칙). 다른 잠긴 행 · 기존 아카이브 바이트 동일. 아카이브 COMPLETE · validate · 미래 데이터 검증 통과. 10/23 · 10/26 화면의 같은 날짜 History · Official regime 띠 차이는 각 화면 첫 칸(09/24, 계산 시작점)뿐. 스크린샷 `data/archive/screenshots/2026-10-26.jpg`.

### 2026-10-27 — 10/27 Daily Snapshot (07:30 KST)
- 입력: 01:08Z 수집(기본 41/54 · 종목 94 · AI 바스켓 52 · RSS 125). 07:30 KST cutoff 재구성(`data/captures/2026-10-27-backfill/`) — 미국 10/26(월) 종가, 미국채/TIPS/HY OAS 10/23 관측, 원자재 10/23. **코스피 · 코스닥 10/26 봉은 Yahoo 일봉에 없다**(10/23 다음이 10/27 장중) — 결측 그대로 두고 메우지 않았다(기사상 10/26 코스피 −1.46%). RSS 창(10/26 07:30~10/27 07:30 KST) 67건 중 22건 수기 태깅. DRAMeXchange 공개 홈 10/26 18:10(GMT+8) 값 수집(DDR5 16Gb $61.333). 금리 · 물가 · 반도체 해석은 API 401 이라 같은 컨텍스트·검증의 세션 생성본.
- 결과: 시장 raw RISK_ON 82%(온도 +19) — S&P +0.7% · 나스닥100 +1.1% · SOXX +2.9% · VIX −5.5%, 앤트로픽 IPO 신고. 공식 regime 은 Liquidity Stress / Risk-Off → Risk-On(CHANGED, 1일) — MARKET NOW 와 History 같은 값. AI LEADERSHIP NARROWING(센티 53), 금리 LONG-END RATE / TERM PREMIUM SHOCK(물가 리프라이싱 반박), 물가 압력 MIXED, 유가 Macro / Liquidity UNCONFIRMED, 반도체 사이클 UPSWING 45.9.
- history: 10/26 행은 7개 탭 RECORDED·잠금(data_asof 10/26 22:30Z). 다른 잠긴 행 · 기존 아카이브 바이트 동일. 아카이브 COMPLETE · validate · 미래 데이터 검증 통과. 10/26 · 10/27 화면의 같은 날짜 History · Official regime 띠 차이 0. 스크린샷 `data/archive/screenshots/2026-10-27.jpg`.

### 2026-11-02 — 10/28 Daily Snapshot (07:30 KST, 사후 재구성)
- 요청: 지난주 수요일(10/28) 기준. 11/02 00:50Z 에 전체 이력을 받아 10/28 07:30 KST cutoff 로 잘라 재구성(`data/captures/2026-10-28-backfill/`, historical_backfill) — 미국 10/27 종가 · 한국 10/27 종가(코스피 +3.1%) · 미국채/TIPS/HY OAS 10/26 관측(FRED 공개 지연 규칙). 시장 계열은 지금 받은 값이라 vintage 미보장(manifest 에 표시), 거시 발표치는 FRED realtime.
- 뉴스: RSS 는 최근 기사만 남아 11/02 수집분에는 창(10/27 07:30~10/28 07:30 KST) 기사가 2건뿐 — 10/27 01:08Z 수집분과 합쳐 31건, 15건 수기 태깅. 10/27 01:00~15:50Z 사이 기사는 피드에서 빠져 없다(메우지 않음).
- 메모리: Daily Express 새 글 4건(10/27~10/30) 수집 — 10/28 화면에는 10/27분만. DDR5 16Gb 는 10/26 값 이후 공개 관측이 없어 CARRIED_FORWARD(보존본 수집 workflow 수동 실행은 403).
- 결과: 시장 raw RISK_ON 95%(온도 +34) — S&P +0.6% · 나스닥100 +1.3% · SOXX +3.9% · VIX −4.7% · 코스피 +3.1% · 코스닥 +2.3% · 브렌트 −1.7%. 공식 regime Risk-On CONFIRMED(2일). AI LEADERSHIP NARROWING(센티 65), 금리 LONG-END RATE / TERM PREMIUM SHOCK(물가 리프라이싱 미확인), 물가 압력 MIXED(기대인플레만 약한 상승), 유가 Supply CONFIRMED, 반도체 UPSWING 45.7. 해석 3종은 API 401 → 세션 생성본.
- history: 10/27 행 7개 탭 RECORDED·잠금(data_asof 10/27 22:30Z). 다른 잠긴 행 · 기존 아카이브 바이트 동일. COMPLETE · validate 통과. 10/27 · 10/28 화면의 같은 날짜 Official regime 띠는 09/28~10/05 가 다르다 — 화면마다 1M 창 첫날부터 전환 확인 규칙을 다시 적용하기 때문(10/27 화면은 09/25 Liquidity Stress, 10/28 화면은 09/28 Neutral 에서 시작)이고, 첫 확정 전환(10/06 Risk-On)부터는 같다. 저장된 행은 그대로.
- 참고: 10/27 저장본에 없던 코스피 10/26 봉이 지금은 Yahoo 에 있다 — 10/27 저장본은 고치지 않는다(수정은 승인 후 correction 경로로만).

### 2026-11-02 — MARKET REGIME HISTORY 공식 regime 띠 고정 · 10/28 저장본 correction
- 문제: 10/28 화면의 09/28~10/05 공식 regime 띠가 10/27 화면(Liquidity Stress)과 달랐다(Neutral). 원인 — `stabilize` 가 1M 창(22거래일) 첫날을 raw 그대로 두고 판정을 다시 시작해, 창 첫날이 바뀌면 첫 확정 전환 전까지의 과거 칸이 화면마다 달라졌다.
- 수정: 공식 regime 은 저장 sequence 첫날(09/04)부터 한 번만 판정한다 — 창 앞의 저장 기록(lead-in, `history/integrate._lead_in` → `MarketStateHistory._lead_in`, 직렬화 안 함)을 판정에만 쓰고 화면에는 창만 보인다(`engines/regime_history.build_regime_history`). 잠긴 행 위의 인과적 판정이라 같은 날짜의 띠는 어느 화면에서나 같고, 뒤에 날이 붙어도 바뀌지 않는다. 이 값은 10/13~10/27 저장본의 띠와 각 화면 첫 칸을 빼고 모두 같다.
- 10/28 저장본: 사용자 요청으로 correction(`archive correct`, 이전 파일 `archive/superseded/2026-10-28.*.json`, meta.corrections 에 이유). cockpit 섹션만 교체(띠 · blocks · share 표기), 다른 섹션은 기존 파일 그대로. 잠긴 history 행 · 다른 저장본 바이트 동일. 10/27 · 10/28 화면의 같은 날짜 띠 차이 0.
- 테스트: `test_storage_view.py::test_official_regime_is_fixed_per_date_across_screens` 추가. 10/21 저장본 첫 칸(그때 창 첫날 판정) 비교 제외, 반도체 섹션 미보유 검사는 10/26 이전 저장본만.

### 2026-11-02 — 10/29 Daily Snapshot (07:30 KST, 사후 재구성)
- 입력: 11/02 00:50Z 에 받은 전체 이력(10/28 재구성과 같은 입력)을 10/29 07:30 KST cutoff 로 잘라 재구성(`data/captures/2026-10-29-backfill/`) — 미국 10/28 종가(FOMC 동결일) · 한국 10/28 종가(코스피 +6.6%) · 미국채/TIPS/HY OAS 10/27 관측(FRED 공개 지연). 시장 계열 vintage 미보장, 거시 발표치는 FRED realtime.
- 뉴스: RSS 피드에 남은 창(10/28 07:30~10/29 07:30 KST) 기사는 3건뿐(CNBC FOMC 관련) — 모두 태깅. 웹 검색으로 10/28(KST) 기사 2건(코스피 6%대 급등 마감, SK하이닉스 3분기 사상 최대 실적·주주환원 100조 원 계획)을 extra_news 로 더했다. 원문 사이트는 이 세션 네트워크에서 열리지 않아 발행 시각 미확인 → DATE_ONLY, 10/28 KST 마지막 시각(14:59Z, cutoff 전)으로 보수적으로 두었고 코스피 수치는 시장 계열(6012.44 · +6.63%)과 대조. 그 밖의 당일 기사 공백은 메우지 않았다.
- 결과: 시장 raw NEUTRAL 34%(온도 +31) — S&P +0.3% · 나스닥100 +0.6% · SOXX +2.1% · VIX −3.5% · 코스피 +6.6% · 코스닥 +3.7% · WTI +2.9%. 공식 regime Risk-On 3일째, raw 가 Neutral 로 갈려 TRANSITION WATCH. AI LEADERSHIP NARROWING(센티 66), 금리 LONG-END RATE / TERM PREMIUM SHOCK(물가 리프라이싱 미확인), 물가 압력 MIXED(에너지·환율만 상승 압력), 유가 Macro / Liquidity CONFIRMED, 반도체 UPSWING 52.8(공급 뉴스 반영). 해석 3종은 API 401 → 세션 생성본.
- history: 10/28 행 7개 탭 RECORDED·잠금(data_asof 10/28 22:30Z). 다른 잠긴 행 · 기존 아카이브 바이트 동일. COMPLETE · validate 통과. 10/27 · 10/28 · 10/29 화면의 같은 날짜 공식 regime 띠 차이 0(저장 sequence 첫날부터 판정).

### 2026-11-02 — 10/30 Daily Snapshot (07:30 KST, 사후 재구성)
- 입력: 11/02 00:50Z 에 받은 전체 이력을 10/30 07:30 KST cutoff 로 잘라 재구성(`data/captures/2026-10-30-backfill/`) — 미국 10/29 종가(3분기 GDP · 9월 PCE 발표일) · 한국 10/29 종가 · 미국채/TIPS/HY OAS 10/28 관측(FOMC 날, FRED 공개 지연). 시장 계열 vintage 미보장, 거시 발표치는 FRED realtime.
- 뉴스: RSS 피드에 남은 창(10/29 07:30~10/30 07:30 KST) 기사 4건(ECB 동결 · 라가르드 조기 퇴임 · Warsh 분석 · GDP/PCE) 모두 태깅. 웹 검색으로 10/29 한국 기사 2건(삼성전자 3분기 확정 실적, 코스피 실적 발표 뒤 하락 전환)을 extra_news 로 더했다 — 원문 사이트는 이 세션에서 열리지 않아 발행 시각은 기사 URL 의 시각(15:52 · 16:35 KST, URL_TIME), 수치는 시장 계열과 대조(코스피 −1.24% · 삼성전자 −4.13% · SK하이닉스 +2.62%).
- 결과: 시장 raw NEUTRAL 34%(온도 +2) — S&P −0.3% · 나스닥100 −1.4% · SOXX −1.6% · VIX +1.7% · 코스피 −1.2% · 코스닥 −2.3%. 공식 regime Risk-On → Neutral / Mixed(CHANGED, raw Neutral 2일). AI MACRO-DRAGGED AI WEAKNESS(센티 43), 금리 INFLATION REPRICING(확인 — FOMC 날 bear steepening, 기대인플레·실질금리 동반 상승), 물가 압력 UPSIDE BIAS, 유가 Macro / Liquidity UNCONFIRMED, 반도체 UPSWING 49.1. 해석 3종은 API 401 → 세션 생성본.
- history: 10/29 행 7개 탭 RECORDED·잠금(data_asof 10/29 22:30Z). 다른 잠긴 행 · 기존 아카이브 바이트 동일. COMPLETE · validate 통과. 10/28 · 10/29 · 10/30 화면의 같은 날짜 공식 regime 띠 차이 0.

### 2026-11-03 — 11/02 Daily Snapshot (07:30 KST, 사후 재구성)
- 입력: 11/02 00:50Z 에 받은 전체 이력(cutoff 11/01 22:30Z 직후 수집)을 11/02 07:30 KST cutoff 로 잘라 재구성(`data/captures/2026-11-02-backfill/`) — 미국 10/30(금) 종가 · 한국 10/30 종가 · 미국채/TIPS/HY OAS 10/29 관측(FRED 공개 지연). 시장 계열 vintage 미보장, 거시 발표치는 FRED realtime.
- 뉴스: 주말 포함 RSS 창(10/30 07:30~11/02 07:30 KST) 66건 중 25건 수기 태깅. 10/30 낮(KST) 기사는 피드에서 빠져 없다(메우지 않음).
- 결과: 시장 raw LIQUIDITY_STRESS 64%(온도 −50) — 10/30 S&P −1.8% · 나스닥100 −3.5% · SOXX −8.2%(인텔 −29%) · VIX +12.9% · MOVE +7.1% · 금 −3.3% · 브렌트 +2.4% · 코스피 −3.5% · 코스닥 −3.8% · SK하이닉스 −7.1%. 공식 regime Neutral / Mixed 2일째, raw 가 Liquidity Stress 로 갈려 TRANSITION WATCH. AI MACRO-DRAGGED AI WEAKNESS(센티 30), 금리 RISK-OFF FLIGHT TO QUALITY(물가 리프라이싱 미확인), 물가 압력 MIXED(기대인플레 급락 vs 실제 물가·환율·에너지 상승), 유가 Macro / Liquidity Risk-Off CONTRADICTED, 반도체 UPSWING 46.6(주가 확인 −89). 해석 3종은 API 401 → 세션 생성본.
- history: 10/30(금) 행 7개 탭 BACKFILLED·잠금(data_asof 10/30 23:59:59Z — 월요일 저장의 금요일 규칙). 다른 잠긴 행 · 기존 아카이브 바이트 동일. COMPLETE · validate 통과. 10/29 · 10/30 · 11/02 화면의 같은 날짜 공식 regime 띠 차이 0.
- 정적 배포본 13.6MB(아티팩트 한도 16MB) — 저장본이 날마다 늘어 몇 주 안에 한도에 닿는다.

### 2026-11-03 — 11/03 Daily Snapshot (07:30 KST)
- 입력: 01:21Z 수집이 Yahoo 요청 제한(429)으로 기본 35/54 · 바스켓 40/52, 01:28Z 재수집은 기본 37 · 종목 22 · 바스켓 0. 세 수집분(11/03 두 번 + 11/02 00:50Z)을 계열마다 합쳐 마지막 봉이 가장 늦은 것을 썼다(기본 41/54 · 종목 94 · 바스켓 52; 11/02 수집분에서 온 계열 기본 1 · 종목 6 · 바스켓 12 는 마지막 봉 10/30 → STALE 로 보인다). 07:30 KST cutoff 재구성(`data/captures/2026-11-03-backfill/`) — 미국 11/02 종가 · 미국채/TIPS/HY OAS 10/30 관측. **코스피 · 코스닥 · 브렌트 · WTI · 금 · 구리의 11/02 봉은 Yahoo 일봉에 없다**(10/30 다음이 11/03 장중) — 결측 그대로(기사상 11/02 코스피 2%대 상승 마감, 유가 급락).
- 메모리: DRAMeXchange 공개 홈 11/02 18:10(GMT+8) 현물(DDR5 16Gb $61.50) · NAND 512Gb 웨이퍼 10/26 주($16.883, −9.2%) · 9월 계약가 표(Last Update 9/30) 수집, Daily Express 11/02분. 
- 뉴스: RSS 창(11/02 07:30~11/03 07:30 KST) 103건 중 25건 수기 태깅. 금리 · 물가 · 반도체 해석은 API 401 → 세션 생성본.
- 결과: 시장 raw RISK_OFF 53%(온도 −25) — S&P −0.5% · 나스닥100 −1.4% · SOXX −3.8% · VIX +8.9% · 금융·경기민감 상승. 공식 regime Neutral / Mixed → Liquidity Stress / Risk-Off(CHANGED, raw 위험회피 2일). AI AI-SPECIFIC DE-RISKING(센티 30), 금리 RISK-OFF FLIGHT TO QUALITY, 물가 압력 MIXED, 유가 Macro / Liquidity Risk-Off CONTRADICTED, 반도체 UPSWING 41.3(NAND 512Gb 1M −13% WEAK, 주가 확인 −99, 계약 anchor 9월분으로 갱신).
- history: 11/02 행 7개 탭 RECORDED·잠금(data_asof 11/02 22:30Z). 다른 잠긴 행 · 기존 아카이브 바이트 동일. COMPLETE · validate 통과. 11/02 · 11/03 화면의 같은 날짜 공식 regime 띠 차이 0. 정적 배포본 14.0MB(한도 16MB).

### 2026-11-03 — STOCK RADAR · MARKET LEADERSHIP: 제목 한 줄
- STOCK RADAR 카드 기본 화면 = 종목명 · 1D 수익률 · **판단 제목 한 줄**(25자 이내) · 보조 한 줄 · 작은 상태(POSITIVE / WATCH / MIXED / NEGATIVE). 카드를 누르면 기존 WHY · SYSTEM 축 · ANALYST VIEW · RELATED MARKET ISSUES 가 펼쳐진다(다른 카드에서 종목으로 이동하면 자동으로 펼침). 엔진 코드(RETURN_SPIKE · NEWS_DRIVEN_MOVE 등)는 기본 화면에 없다. 데스크톱 2열(카드 최소 330px)로 제목이 꺾이지 않게.
- 제목은 카드에 이미 있는 값으로만 만든다(`components/radarTitle.ts`, 새 판단 없음): 연결된 Leadership 의 실제 동인(유가 ↓ · 지정학) → 펀더멘털 축(세그먼트 개선/둔화 × 상대강도 · 그날 방향) → 같은 테마 Leadership · 테마 확인 → AI 세그먼트 상대강도(펀더멘털 미확인 표시) → 시장 대비 상대강도 → 단순 가격 이상("급등 포착 · 추가 확인 필요", "뉴스성 움직임 · 원인 확인 중" — 원인을 만들지 않는다). 급등·급락은 하루 |z| ≥ 2 일 때만 쓴다. 펀더멘털이 개선이어도 그날 내렸으면 "개선에도 주가 조정"(MIXED).
- MARKET LEADERSHIP 행마다 왜 강(약)한지 한 줄(예: Airlines ↑↑ "유가 하락 수혜로 상대강도 확대", Defense ↑↑ "지정학 리스크 확대로 방산주 강세") — 기존 System view 문장은 detail 패널(System read)에 남는다.
- 화면에서 만들어 저장본을 고치지 않고 과거 날짜 화면에도 같은 규칙이 적용된다. 테스트 `radarTitle.test.ts`(저장된 모든 날짜: 25자 · 엔진 코드/금지어 없음 · 11/03 대표 종목 문장), `cockpit.test.tsx` 갱신.
- 후속(11/04): 가격 계열이 하나뿐인 Leadership 줄(섹터 ETF 전부 · Geopolitical Risk 처럼 주식 자산이 ITA 하나인 테마)은 breadth 가 그 지수 하나의 20일선 위·아래(0 / 100)일 뿐이라 종목 확산으로 읽지 않는다. 화면 제목: "종목 전반 확산" · "수혜주 동반 강세" 를 쓰지 않고(Geopolitical Risk ↑ → "지정학 긴장 속 상대강도 확대"), Radar 보조 줄은 "항공주 전반 상승 · breadth 100%" 대신 "항공주 지수 시장 대비 +4.1σ (1주)". 엔진(`leadership_intel`, 다음 저장본부터): BREADTH 확인 줄 = "단일 지수 · 20일선 위/아래"(DATA MISSING, 확산 여부 알 수 없음), WHY 의 breadth 문장 · BROADENING/NARROW 품질 · System view 의 breadth 문장 · Leadership read 의 breadth 문장에서 단일 지수 제외. 기존 저장본의 detail 문장은 그대로.

### 2026-11-04 — 11/04 Daily Snapshot (07:30 KST)
- 입력: 04:02Z 수집(기본 41/54 · 종목 93 · 바스켓 52 · RSS 123 — 이번엔 요청 제한 없음). 07:30 KST cutoff 재구성(`data/captures/2026-11-04-backfill/`) — 미국 11/03 종가(중간선거일) · 한국 11/03 종가 · 미국채/TIPS/HY OAS · 원자재 · 환율 11/02 관측. Yahoo 에 11/02 봉이 다시 들어왔다(11/03 저장본에는 없던 값 — 그 저장본은 고치지 않는다). RSS 창(11/03 07:30~11/04 07:30 KST) 78건 중 22건 수기 태깅. DRAMeXchange 공개 홈은 수집 시점에 11/04 장중 값만 보여 DDR5 16Gb 11/03 종가는 없다 → 11/02 값 CARRIED_FORWARD. Daily Express 11/03분 수집.
- 결과: 시장 raw NEUTRAL 34%(온도 −1) — 11/03 S&P +0.4% · 나스닥100 +0.7% · SOXX +2.5% · VIX −1.5% · 코스피 −3.6% · 코스닥 −4.1% · SK하이닉스 −5.0%, 11/02 브렌트 −10.9% · WTI −7.4%. 공식 regime Liquidity Stress / Risk-Off 2일째, raw Neutral → TRANSITION WATCH. AI AI-SPECIFIC DE-RISKING(센티 32), 금리 RISK-OFF FLIGHT TO QUALITY(기대인플레 급락), 물가 압력 COOLING BIAS, 유가 Supply CONFIRMED, 반도체 UPSWING 41.2. 해석 3종은 API 401 → 세션 생성본.
- 단일 지수 breadth 규칙(11/04 수정)이 이 저장본부터 엔진 문장에 적용 — Leadership 의 BREADTH = "단일 지수 · 20일선 위/아래", Leadership read 에 breadth 문장 없음.
- history: 11/03 행 7개 탭 RECORDED·잠금(data_asof 11/03 22:30Z). 다른 잠긴 행 · 기존 아카이브 바이트 동일. COMPLETE · validate 통과. 11/02~11/04 화면의 같은 날짜 공식 regime 띠 차이 0. 정적 배포본 14.3MB(한도 16MB).

### 2026-11-04 — China 테마 = 중국 주식 7지수 종합
- China 테마 점수 · Leadership 을 H지수 하나 대신 홍콩 3(항셍 `HANGSENG` · H지수 `HSCEI` · 항셍테크 `HSTECH`) + 본토 4(상해종합 `SHCOMP` · 심천성분 `SZCOMP` · CSI 300 `CSI300_ETF` · 창업판 `CHINEXT`) 동일가중으로 본다. Leadership breadth = 7개 중 20일선 위 비중.
- 항셍테크 · CSI 300 · 창업판은 Yahoo 지수 이력이 1봉뿐이라 같은 지수를 추종하는 현지 상장 ETF(3033.HK · 510300.SS · 159915.SZ)로 대신한다(이름에 "(ETF)"). 구리 · 위안화는 테마 점수에서 빼고 driver 연결 · 매크로 factor 에 남긴다.
- 기존 아카이브는 그대로(잠금) — 다음 스냅샷부터 적용. 11/04 cutoff 기준으로 계산해 보면 홍콩 대형(H지수 +2.3% · 항셍 +2.1%, 1주)만 강하고 본토·성장(심천 −3.3% · 창업판 −6.7%)은 약세, 7개 모두 20일선 아래.

### 2026-11-04 — 금리 · 유가 탭 DESKTOP 레이아웃
- 원인: `.rr`/`.or` 는 1101px 부터 3열인데 `.span-3` 은 1400px 부터만 3칸 → 1101–1399px(iPad 가로)에서 큰 카드가 한 칸(≈120–140px)으로 떨어져 글자가 세로로 쪼개지고 카드가 3,000px 넘게 늘어났다. ≥1400px 에서는 반대로 모든 카드가 한 줄 전체.
- ≥1024px 에만 12열 grid(`layout.css` 끝 블록) — 모바일(<768) · 태블릿(768–1023) 규칙 · DOM 순서는 그대로. 카드마다 자리 class(`g-regime` · `g-ca` · `g-events` · `g-imap` · `g-curve` · `g-yb` · `g-conf` · `g-div` · `g-imp` · `g-changes` · `g-diag` / 유가 `g-drivers` · `g-nar` · `g-watch`).
- 금리 ≥1280: [Regime 4 (두 줄)][Current Analysis 8 / History 8] · [Policy & Macro 7 → Treasury Curve 7][Inflation Map 5 → Yield Breakdown 5] · [Market Confirmation 8][Key Divergence 4] · [Implication 5][What Changes 7] · [Diagnostics 12]. 1024–1279 은 같은 흐름을 6:6. 긴 카드(Regime · Inflation Map) 옆에 짧은 카드를 쌓아 빈 칸을 줄였다(행 단위 4/5/3 · 6/6 보다 1440px 기준 높이 −220px · 빈 칸 −600px).
- 유가 ≥1280: [Regime 6][History 6] · [Driving Oil 8][Confirmation 4] · [Narrative 5][Watch Next 7] · [Diagnostics 12]. 1024–1279 은 Driving 7 / Confirmation 5.
- Diagnostics 는 접혀 있으면 한 줄 바, 펼치면 한 줄 전체. 높이는 내용대로(`align-items: start`). 카드 안쪽은 container query 로 카드 폭에 맞춰 열을 줄인다(확인표 400px ↓ 두 줄, 이벤트 640px ↓ 한 열, Regime 머리 600px ↓ 한 열). 확인표 ellipsis 제거 · `word-break: keep-all` + `overflow-wrap: anywhere` · 읽는 문장 13px 이상.
- 유가 What To Watch Next 를 제목(엔진 문장의 "머리:") · 현재 값 · 기준(작게) · 설명(작게)으로 나눠 보인다 — 문장 · 조건은 그대로(테스트로 원문 복원 확인).
- 계산 · 데이터 변경 없음. 1440×900 · 1366×768 · 1180×820 · 1024×768 · 390×844 에서 가로 스크롤 0 · 세로로 쪼개진 글자 0 · 페이지 오류 0. 390 금리 화면 높이 이전과 동일.

### 2026-11-04 — 실시간 · 금리 · 유가: 처음 3개 section = 한 장의 큰 카드
- 범위: 웹 화면 CSS 만(`frontend/src/theme/layout.css` 끝 블록). 실시간 · 금리 · 유가 탭의 위에서 첫 3개 section. 계산 · 데이터 · API · 백엔드 변경 없음. AI 센티 · 반도체 사이클 · 평시 탭은 손대지 않았다 — 변경 전후 전체 화면 픽셀 해시가 1440 · 1180 · 390 에서 모두 같다.
- 실시간: MARKET NOW · MARKET REGIME HISTORY · 1M · MARKET TONE SNAPSHOT. raw signal 회색 상자(두 카드) · 최근 전환 상자 3개 → 구분선 줄. Tone 은 ≥1024 에서 [온도 · 눈금 · 설명][재료 스트립] 두 칼럼으로 카드 폭을 쓴다(같은 온도계, 그 카드 안에서만).
- 금리: INFLATION & RATES REGIME · CURRENT RATES ANALYSIS · STATE HISTORY. 10Y · CONFIDENCE · PRIMARY DRIVER · INFLATION REPRICING 4칸과 DRIVER · CURVE · REAL YIELD · BREAKEVEN 4칸 → "이름 | 값 | 보조" 줄, DRIVER READ 회색 띠 → 구분선 줄, driver chip → 상태색 막대 + 글자, history 안 회색 상자 제거. 데스크톱 배치 [REGIME 6][CURRENT 6] / [HISTORY 12], 4번째부터는 기존(Policy 7 → Curve 7 / Inflation 5 → Breakdown 5 …).
- 유가: OIL MARKET REGIME · OIL STATE HISTORY · WHAT IS DRIVING OIL?. chip 상자 → 막대 + 글자, history 회색 상자 제거, driver 상자 4개 → 구분선 줄(지배 driver 는 왼쪽 강조선, 넓은 카드에선 [이름 · 상태][점수 막대] 한 줄 + 증거 줄). 데스크톱 [REGIME 6][HISTORY 6] / [DRIVING 12], 4번째부터 [CONFIRMATION 5 ─ 두 줄][NARRATIVE 7 / WATCH 7] · [DIAGNOSTICS 12].
- 확인: 1440 · 1366 · 1180 · 390 에서 세 탭 첫 3개 카드 안의 테두리·음영 sub-box 0(변경 전 실시간 1·4·0 / 금리 10·4·1 / 유가 4·1·4), 가로 스크롤 0, 세로로 쪼개진 글자 0, 페이지 오류 0. 모바일은 1열 그대로.
- 후속(11/04): 실시간 · 금리 탭은 맨 위 첫 줄도 나누지 않는다 — 첫 3개 카드를 한 장씩 전체 폭으로 쌓는다(실시간 MARKET NOW → HISTORY → TONE, 금리 REGIME → CURRENT ANALYSIS → HISTORY). 전체 폭이 된 MARKET NOW · CURRENT RATES ANALYSIS 는 카드 한 장 그대로 안쪽만 두 칸으로 흘린다(상태·지표 | 해석 문장 / DRIVER~BREAKEVEN 줄 | What Is Driving Rates). 유가 탭은 [REGIME][HISTORY] / [DRIVING] 그대로. 제외 탭 픽셀 동일, 가로 스크롤 0.

### 2026-11-04 — 정적 배포본에 저장 화면 전부(10/12~)
- 원인: 배포본(아티팩트 파일 하나, 한도 16MB)에 저장본을 원본 JSON 으로 넣어 최근 8일(`bundle_max_dates: 8`)만 담겼다 — 하루 1.2~1.6MB, 8일로 14.6MB. 저장소의 저장본 18일치는 그대로 있었다.
- 수정: 날짜별 저장본을 gzip+base64 로 넣고, 화면이 날짜를 고를 때 그 날짜만 브라우저에서 푼다(`DecompressionStream`, 푼 것은 기억). `bundle_max_dates: 0` = 전부. 18일치를 넣어도 배포본 7.6MB.
- 내용은 저장본 그대로 — 푼 결과가 이전 배포본 8일치와 객체 단위로 같고, snapshot · rates · oil · semiconductor · investment · news 섹션이 저장 파일과 같다. 18일 모두 `?date=` 로 열림 · 페이지 오류 0.

### 2026-11-04 — 날짜 펼침 창 잘림
- 원인: 펼침 창(320px)이 날짜 버튼의 오른쪽 끝에 붙어 있어, 머리줄이 두 줄로 접혀 버튼이 왼쪽에 오는 폭(iPad · 1180px 등)에서 화면 왼쪽 밖으로 나갔다(left −89px).
- 수정: 열 때 버튼 위치를 재서 오른쪽 기준으로 왼쪽 밖이면 왼쪽 끝에 붙인다(`popSide`), 폭은 화면 안(`max-width: 100vw − 16px`). 640px 이하는 원래대로 아래에서 올라오는 시트. 1000 · 1024 · 1180 · 1366 · 1440 · 800 · 390 에서 창 전체가 화면 안.

### 2026-11-04 — RECENT TRANSITIONS: 레짐 전환 이유를 문장으로
- 화면(`components/transitionWhy.ts` · `RegimeHistoryCard`)만 바꿨다. regime 계산 · 전환 날짜 · persistence · history · 저장본 값 · 다른 탭은 그대로.
- 근거 풀: 전환 기록의 factor 변화 · 주도 변수, 그리고 그 행(시장일 D)의 데이터를 담은 저장 스냅샷(D 다음 평일 07:30 KST 저장본)의 Today's Market Drivers(신용 · 주식 · 변동성 · 장기/단기금리 · 유가 · AI·반도체 · 한국 · 금) · 지표/정책 이벤트 · 태깅 뉴스. 스냅샷이 없는 10/12 이전은 factor · 주도 변수로만 쓰고 "이벤트 없음" 을 단정하지 않는다.
- 고정 우선순위 없음: 모든 후보를 같은 저울(그날 움직인 크기 × 새 regime 쪽으로 미는가)에 올려 2~3개. 이벤트 · 뉴스는 그 자체 점수가 없고 이어지는 시장 반응이 실제로 컸을 때만 그 크기로 후보가 되며, 문장에는 그 사건과 이어진 반응만 사건의 결과로 쓴다. 유가처럼 방향은 다르지만 그날 가장 크게 움직인 것은 맥락("물가 부담은 덜었지만") 한 마디로.
- Look-ahead 없음: 스냅샷은 history 마지막 행이 D 인 D 이후 첫 저장본만(테스트로 확인), 이벤트는 (직전 행, D] 발표분, 뉴스는 그 스냅샷 cutoff 이전 · 직전 행 이후 발행분.
- 표시: 날짜 · 전환 → 왜 바뀌었나(먼저) → 근거 칩 2~3개 → 시장 의미 · 누르면 MARKET EVIDENCE(원자료 · 어느 저장본인지). 예: 10/14 "예상보다 높은 CPI 이후 주식 전반의 급락과 신용 스프레드 확대가 겹치면서 유동성 스트레스 쪽 신호가 우세해졌습니다."
- 테스트 `transitionWhy.test.ts`: 저장된 18개 날짜 화면의 모든 전환 — 문장이 결론으로 끝, ticker · σ · 엔진 코드 · 금지어 없음, 근거 1~3개, 쓴 스냅샷이 D 이후 · 화면 날짜 이전 · 마지막 행 D, 같은 전환은 어느 날짜 화면에서도 같은 문장.

### 2026-11-04 — MARKET NOW 문장 "유가 하락·유가 하락"
- 원인: 핵심 변수 문장(`cockpit.py`)이 변수별 문구를 이어 붙일 때 같은 문구를 거르지 않았다 — 브렌트 · WTI 가 둘 다 "유가 하락". 기대인플레이션(BE5Y · BE10Y)은 문구가 없어 빠졌다.
- 수정: 같은 문구는 한 번만, `clauses` 에 BE5Y · BE10Y("기대인플레이션 상승/하락") 추가. 11/04 핵심 변수로 다시 만들면 "유가 하락·기대인플레이션 하락이 겹친 유동성 경색 · broad risk-off 환경이다." 다음 스냅샷부터 적용. 사용자 승인으로 11/04 저장본(archive correct · 이전 파일 superseded/2026-11-04.20261104T073408Z.json · meta.corrections 에 이유)과 LIVE 캡처의 그 문장 한 칸만 같은 규칙의 문장으로 교체 — 다른 값은 바이트 단위로 같음, validate COMPLETE.

### 2026-11-04 — MARKET REGIME v2: 주식 투자자 관점의 regime 선택
- 구조: factor(그대로) → 후보(state_rules require = 자격) → 미국 · 한국 · Global 주식 확인 → cross-asset · history · coverage → LLM 선택(자격 있는 후보 또는 NEUTRAL / MIXED 중에서만) → 기존 history persistence(2거래일, 확신 80 이상 즉시 — 과거 공식 판정을 바꾸지 않으려고 규칙은 그대로) → OFFICIAL.
- 코드: `config/regime_select.yaml`(regime 별 주식 확인 신호 · 업종 바스켓 · 상태 기준 · 정량 confidence 가중) · `engines/regime_select.py`(후보 · 주식 확인 · 컨텍스트 · LLM 스키마/프롬프트/검증 · 정량 대체 선택) · `models/regime_select.py` · `MarketState.selection` · `MarketNow.selection`. 일일 저장 파이프라인(`reconstruct`)에서 investment 다음에 선택해 market_state.primary_label(= history raw)로 쓴다. 세션 생성본은 캡처 폴더 `regime_select_session.json`(같은 검증).
- 데이터 없음 = EXCLUDED: support 조건 · 주식 신호 모두 분모에서 빼고 coverage 에만. confidence 와 DATA COVERAGE 를 따로 보인다(정량 confidence 에 coverage 를 넣지 않는다).
- 주식 확인: 미국 = SPX · NDX · RUT · SOXX · CYC_DEF · 섹터 ETF(XLF · XLU · XLE · XLY · XLK) · ITA · JETS(상대강도 포함, 1일 z 와 5일 z 7:3). 한국 = KOSPI · KOSDAQ · KOSDAQ/KOSPI · 대표 종목 35개(16업종) 상승 비율 · 중앙값 − KOSPI(대형주 쏠림) · 업종 바스켓 상대강도. STRONG / CONFIRMED / PARTIAL / CONTRADICTED, Global 은 두 시장이 엇갈리면 MIXED.
- 데이터 조사: AVAILABLE — SPX · NDX · RUT · SOXX · XLF/XLU/XLE/XLY/XLK · ITA · JETS · VIX · MOVE · HY OAS · DXY · 유가 · 금 · 구리 · BE · TIPS · 중국 7지수 · KOSPI · KOSDAQ · USDKRW. PARTIAL — 한국 업종(대표 종목 2~4개), 한국 breadth(대표 종목 기준), 은행(XLF). UNAVAILABLE · EXCLUDED — US breadth(SPX_ADV_RATIO), Equal Weight · High Beta · Low Vol · Industrials · IG spread(미설정), KOSPI200 · KRX 반도체(봉 없음), KOSPI/KOSDAQ breadth, KOSDAQ150, VKOSPI, 한국 금리, 한국 수급(외국인 · 기관 · 개인) · 거래대금.
- 화면(MARKET NOW): REGIME CONFIDENCE · DATA COVERAGE · PRIMARY SIGNAL · (공식과 다르면) PENDING CANDIDATE · TRANSITION n/2 · EQUITY CONFIRMATION US/KOREA/GLOBAL · WHY, 펼침에 신호별 방향 · EXCLUDED · 후보 · persistence. 화면에 NO REGIME 을 쓰지 않는다(NEUTRAL / MIXED, 예전 저장본 문구도 보일 때만 바꾼다).
- 테스트 `tests/test_regime_select.py`(요청서 case A–J + 자격 없는 선택 · 금지어 차단 · LLM → 세션 → 정량 흐름), `frontend/src/__tests__/regimeSelection.test.tsx`.
- 11/04 다시 판단(LIVE 화면 · 캡처만, 11/04 저장본 · history 는 그대로): 자격 있는 후보 없음(가장 가까운 Growth −0.62 / 기준 −1.0, Risk Appetite +0.43 / +0.8) → NEUTRAL / MIXED · confidence 58 · coverage 76% · US PARTIAL · KOREA CONTRADICTED · GLOBAL PARTIAL. 공식은 Liquidity Stress 유지(전환 후보 1/2). API 401 → 같은 컨텍스트 · 검증의 세션 생성본.

### 2026-11-04 — 금리 탭 POLICY & MACRO EVENTS: 10/15 이후 결정이 빠져 있던 문제
- 원인: 이벤트는 수기 확인 파일(`data/policy_events/YYYY-MM-DD.json`)에서만 오고, 스냅샷은 그 날짜 이하의 가장 최근 파일을 읽는다. 10/15 뒤로 파일을 만들지 않아 10/16~11/04 스냅샷이 모두 10/15 파일(FED 9/16 인상 · NEXT 10/28 …)을 보여줬다.
- 수정: `2026-11-04.json` 추가 — 10/22 BOK 3.00% 만장일치 동결 · 10/28 FOMC 3.75–4.00% 동결(10–2, Cook · Hammack 인상 주장) · 10/29 ECB 예치 2.50% 동결 · 10/30 BOJ 1.25% 동결(8–1, Takata 1.5% 제안) · 9월 PCE(헤드라인 3.6% vs Dow Jones 3.7% → COOL, 근원 3.1% 예상 수준). 다음 회의 FED 12/8–9 · ECB 12/17 · BOJ 12/17–18 · BOK 11/26, 일정 11/06 고용 · 11/10 CPI · 11/13 PPI · 11/17 소매판매 · 11/25 PCE. 확인하지 못한 값(ECB 표결 · 8월 PCE 전월 수정치 · 연준 12월 경로 가격)은 비움. 톤은 네 곳 모두 neutral(동결 · 데이터 의존) — 인상 쪽 반대표는 guidance_basis 에 적었다.
- 적용: 11/05 스냅샷부터 자동. 11/04 저장본은 잠금 그대로(승인 시 archive correct 경로로만).
- 사용자 승인으로 11/04 화면에도 적용: 같은 엔진 · 같은 PIT 계열(cutoff 11/03 22:30Z)로 10/15 파일을 넣으면 저장된 events 가 바이트 단위로 재현되는 것을 먼저 확인한 뒤, 새 파일로 만든 `rates_regime.events` 한 칸만 저장본(archive correct · 이전 파일 superseded/2026-11-04.20261104T130321Z.json · meta.corrections 에 이유)과 LIVE 캡처에서 교체. 다른 섹션 · 금리 regime 판정 · 점수는 그대로, validate COMPLETE. 매크로 패널 컨센서스 · regime 선택 컨텍스트처럼 판정 입력으로 쓰인 곳은 바꾸지 않았다.

### 2026-11-04 — 정책·지표 이벤트 파일 매일 자동 갱신
- `marketpulse/scripts/policy_events_update.py`: `draft`(직전 파일을 오늘 KST 파일로 이어 쓰기 · 지난 일정 정리 · 조사 목록 출력) · `due` · `validate`(형식 · look-ahead · 금리 산술 · 출처 · 직전 파일 대비 누락 + FRED 발표일 vintage 대조: CPI/PCE/고용 actual, 연준 목표 상단 · ECB 예치금리). 값은 만들지 않는다.
- 절차 `docs/policy-events-daily-update.md`. 평일 06:40 KST 예약 작업(매번 새 세션)이 draft → 웹검색으로 둘 이상 출처 확인한 값만 채움 → validate · 테스트 → 이벤트 파일만 커밋 · push. 저장본 · 캡처는 건드리지 않는다.
- 기존 파일 5개 모두 validate 통과(FRED 대조 포함). 틀린 숫자(PCE 3.9 · NFP 55 · 연준 3.50–3.75%)를 넣으면 FAIL 로 막히는 것 확인. 테스트 `tests/test_policy_events_update.py`.

### 2026-11-04 — 금리 탭 아래 네 카드 길이 맞춤 · TREASURY CURVE 한 칸
- 원인: 데스크톱(≥1024)에서 EVENTS · INFLATION MAP · CURVE · BREAKDOWN 을 줄 번호로 두 칼럼에 흘려, 칼럼마다 높이가 달라 한쪽에 큰 빈칸이 생겼다(1180 에서 INFLATION MAP 아래 470px).
- 수정(화면만): [POLICY & MACRO EVENTS 12] / [INFLATION MAP 6][CURVE 6 → BREAKDOWN 6] — 오른쪽 둘을 한 칼럼(`rp-col`)으로 묶고 두 칼럼 끝을 맞춘다(짧은 쪽 마지막 카드가 늘어난다). 1024 · 1180 · 1280 · 1366 · 1600 모두 두 칼럼 끝이 같은 y, 카드 겹침 0, 가로 스크롤 없음. 1024 미만은 `rp-col` 이 display: contents 라 예전 순서 그대로. 옛 저장본(흐름 없는 화면)은 예전 줄 번호 규칙.
- Central Banks 4곳은 3 + 1 대신 2 × 2.
- TREASURY CURVE 판정: CURVE MOVE · MOVE INTENSITY 두 상자를 한 칸으로(모양 → 방향 · 가장 크게 움직인 만기 σ · 이례성). 값 · 계산 그대로. 다른 탭 변경 없음.
- 배포 주소 정정: 위 두 변경(11/04 이벤트 · 금리 탭 배치)을 처음에 예전 대시보드 주소(YJ43T5NFBoLDoCS8Bua5am)에 올렸다. 사용 중인 대시보드는 https://claude.ai/artifact/3ERLmXjNkcrbGmfdjwbHzS — V108 로 다시 올림. 앞으로 배포는 이 주소로만.

### 2026-11-05 — 11/05 Daily Snapshot (07:30 KST)
- 입력: 05:20Z 수집이 Yahoo 요청 제한(429)으로 S&P 500 · MOVE · XLF · 종목 12개가 빠져, 05:24Z 재수집 · USD/KRW 단독 재수집(첫 두 번은 FRED 주간 계열 10/30 으로 대체됨)과 계열마다 합쳤다(마지막 봉이 가장 늦은 것 — 기본 47/60 · 종목 94 · 바스켓 52). 07:30 KST cutoff 재구성(`data/captures/2026-11-05-backfill/`, historical_backfill 규칙 — 오늘이지만 '지금 데이터' 저장이 아니다) — 미국 11/04 종가(중간선거 다음 날) · 한국 11/04 종가 · 미국채/TIPS/HY OAS · 원자재 · 환율 11/03 관측(11/04 봉은 cutoff 에 끝나지 않음). RSS 창(11/04 07:30~11/05 07:30 KST) 77건 중 25건 수기 태깅. DRAMeXchange 11/05 11:00(GMT+8) 값은 cutoff 뒤라 화면 밖(DDR5 16Gb 마지막 값 11/04 $61.50).
- 결과: 미국 중간선거 민주당 압승 · 트럼프 패배 인정 — S&P +1.6% · Russell +1.6% · XLF +3.5% · 경기민감 대 방어 +3.8% · VIX −20% · SOXX −3.1%(텍사스 AI 데이터센터 건설 중단 우려), 한국 대표 종목 78% 상승. REGIME v2 선택 RISK_ON 78(세션 — 정량 86.5 보다 낮게: 하루짜리 정치 이벤트 반응 · 반도체/나스닥 미확인 · 신용/원자재 반응 미반영), US · KOREA · GLOBAL CONFIRMED, coverage 81%. 공식 regime Liquidity Stress / Risk-Off 유지, PENDING Risk-On 1/2. AI AI-SPECIFIC DE-RISKING(센티 28), 금리 GROWTH-LED RATES(물가 리프라이싱 반박), 물가 압력 MIXED(환율 전가 ↔ 기대인플레·에너지), 유가 Geopolitical Premium UNCONFIRMED, 반도체 UPSWING 41.2. 해석 4종(금리 · 물가 · 반도체 · regime 선택)은 API 사용 불가 → 같은 컨텍스트·검증의 세션 생성본.
- 정책 이벤트: 11/05 파일(06:40 KST 예약 작업, 이어 쓰기) — 금리 탭 하단 '수집 2026-11-05'.
- history: 11/04 행 7개 탭 RECORDED·잠금. 다른 잠긴 행 · 기존 아카이브 바이트 동일(삽입만). COMPLETE · validate · 테스트 통과. 스크린샷 `data/archive/screenshots/2026-11-05.jpg`. 정적 배포본 8.3MB.

### 2026-11-06 — 11/06 Daily Snapshot (07:30 KST)
- 입력: 23:16Z 수집이 Yahoo 요청 제한(429)으로 바스켓 0/52 · 종목 22개 · 기본 계열 일부(SOXX · 항셍 · 닛케이 …)를 못 받아, 재수집 + 빠진 계열만 4~10초 간격으로 하나씩 받아(`scratchpad/fetch_missing.py`) 계열마다 합쳤다(기본 47 · 종목 94 · 바스켓 52). **SOXX · ITA 는 공급자 응답이 분할 조정 단위가 섞여(마지막 봉이 앞 봉의 약 1/3 — SOXX 450.41 → 131.90, ITA 212.84 → 68.11) 이번 스냅샷에서 뺐다(결측, 보정하지 않음)** — 같은 날 SOX 지수 −12.2% · SMH −11.2% 는 정상 계열. 기록 `captures/2026-11-06-backfill/input_merge_report.json`. 07:30 KST cutoff 재구성 — 미국 11/05 종가 · 한국 11/05 종가 · 미국채/TIPS/HY OAS · 원자재 · 환율 11/04 관측. RSS 창(11/05 07:30~11/06 07:30 KST) 138건 중 27건 수기 태깅. DRAMeXchange 11/05 18:10(GMT+8) 값 반영(DDR5 16Gb $60.667).
- 결과: 11/05 AI 기술주 투매 — S&P −4.4% · 나스닥100 −6.4% · Russell −4.5% · VIX +70%, 코스피 · 코스닥 5%대 급락(매도 사이드카), 11/04 브렌트 −8.7% · 금 +3.4%. REGIME v2 선택 RISK_OFF 72(세션 — 정량 1위 GROWTH_SHOCK 76.8 은 대안: 유가 · 금리 하락은 선거 다음 날 관측이고 주식 급락의 출발점은 AI 데이터센터 규제 우려), US · KOREA · GLOBAL STRONG. 공식 Liquidity Stress / Risk-Off 유지(같은 묶음 — 11/04 Risk-On 은 하루로 끝). AI AI-SPECIFIC DE-RISKING(센티 23), 금리 GROWTH-LED RATES, 물가 압력 MIXED, 유가 Supply CONFIRMED, 반도체 UPSWING 35.8(현물 모멘텀 FLAT). 해석 4종은 API 사용 불가 → 세션 생성본.
- 화면 수정: MARKET NOW 의 PENDING CANDIDATE 가 선택(RISK_OFF)과 공식(LIQUIDITY_STRESS)을 이름으로만 비교해, 같은 'Liquidity Stress / Risk-Off' 묶음인데도 전환 후보로 보였다 → taxonomy 묶음으로 비교(`CockpitView.regimeGroup`), 테스트 2개.
- history: 11/05 행 7개 탭 RECORDED·잠금(삽입만). COMPLETE · validate · 백엔드 · 프론트(153) 테스트 통과. 스크린샷 `data/archive/screenshots/2026-11-06.jpg`.

### 2026-11-09 — 11/09 Daily Snapshot (07:30 KST)
- 입력: 01:25Z 수집 한 번에 기본 47 · 종목 94 · 바스켓 52(요청 제한 없음). 단위 불연속 검사: SOXX · ITA 는 이제 분할 조정이 일관되게 들어와(11/05 SOXX −12.1% · ITA −4.0%) 정상 — 11/06 저장본(두 계열 결측)은 그대로. 07:30 KST cutoff 재구성 — 미국 11/06(금) 종가 · 한국 11/06 종가(코스피 −6.0%, 서킷브레이커) · 미국채/TIPS/HY OAS 11/05 관측. 주말 포함 RSS 창(11/06 07:30~11/09 07:30 KST) 78건 중 27건 수기 태깅. DRAMeXchange 11/06 18:10(GMT+8) · NAND 웨이퍼 11/02 주 값.
- 결과: 미국 11/06 반도체 중심 반등(SOXX +3.5% · VIX −9%) · 10월 고용 +16.5만 명, 한국 11/06 급락(대표 종목 6%만 상승), HY OAS +16bp · 달러 +2.4σ · 원화 약세. REGIME v2 선택 LIQUIDITY_STRESS 55 TENTATIVE(세션 — 정량 1위 POLICY_DRIVEN 52.3 은 대안: 금리 하락은 기술주 급락에 따른 안전자산 선호), US PARTIAL · KOREA CONFIRMED · GLOBAL PARTIAL. 공식 Liquidity Stress / Risk-Off 유지. AI AI-SPECIFIC DE-RISKING(센티 27), 금리 RISK-OFF FLIGHT TO QUALITY, 물가 압력 MIXED, 유가 Macro / Liquidity Risk-Off UNCONFIRMED, 반도체 UPSWING 32.2(현물 FLAT · Spot Premium COMPRESSING · 주가 확인 BROAD). 해석 4종 세션 생성본.
- 수정 1 — 월요일 금요일 행: 월요일 07:30 KST 화면(= UTC 일요일)은 저장하지 않고 금요일 행을 replay(v1 규칙, REGIME v2 선택 없음)로 따로 계산해, 같은 화면의 MARKET NOW(LIQUIDITY_STRESS 55)와 history 마지막 행(POLICY_DRIVEN 28.6)이 갈렸다. market_regime 은 평일처럼 그 화면 판정을 직전 평일 행으로 RECORDED 기록(`history/integrate.sync_market`, 행 날짜 = 금 · as_of = 실제 판정 시각). 다른 탭의 금요일 행은 기존 규칙(BACKFILLED, data_asof 금 23:59:59Z). 잠긴 과거 행 변화 없음. 테스트 `test_history_monday_row.py`.
- 수정 2 — PRIMARY SIGNAL: 정량 1위 후보의 Trigger 를 썼다(11/06 화면: 선택 Risk-Off 인데 'Growth −2.28') → 선택한 regime 의 Trigger(`regime_select.finalize`). 이 저장본부터 — 11/06 저장본은 잠금 그대로. 테스트 추가.
- history: 11/06(금) 행 7개 탭 잠금(삽입만). COMPLETE · validate · 백엔드 테스트 통과. 스크린샷 `data/archive/screenshots/2026-11-09.jpg`.

### 2026-11-10 — 11/10 Daily Snapshot (07:30 KST)
- 입력: 00:42Z 수집 한 번에 기본 47 · 종목 94 · 바스켓 52, 단위 불연속 없음. 07:30 KST cutoff 재구성 — 미국 11/09(월) 종가 · 미국채/TIPS/HY OAS · 환율 · 원자재 11/06 관측. **코스피 · 코스닥 · 브렌트의 11/09 일봉은 Yahoo 에 없다**(11/06 다음이 11/10 장중) — 결측 그대로(기사상 11/09 코스피 −0.81% 5018.85, 유가 7% 급락). 그래서 한국 주식 확인은 11/06 값 위에 있다. RSS 창(11/09 07:30~11/10 07:30 KST) 104건 중 27건 수기 태깅. DRAMeXchange 11/09 18:10(GMT+8).
- 결과: 미국 11/09 급반등 — S&P +2.4% · 나스닥100 +3.4% · SOXX +7.5% · Russell +3.2% · VIX −22%(엔비디아 −4.3% 에도). REGIME v2 선택 RISK_ON 72(세션 — 정량 83.9 보다 낮게: 급락 직후 하루 반등 · 한국 확인은 11/06 값 · 신용/달러는 금요일 관측), US STRONG · KOREA CONTRADICTED · GLOBAL MIXED. 공식 Liquidity Stress / Risk-Off 유지, PENDING Risk-On 1/2. AI LEADERSHIP NARROWING(센티 54), 금리 INFLATION REPRICING(미확인 · 금요일 고용 뒤 단기물 상승), 물가 압력 MIXED, 유가 Macro / Liquidity UNCONFIRMED, 반도체 UPSWING 32.3(현물 약세 지속). 해석 4종 세션 생성본.
- history: 11/09 행 7개 탭 RECORDED·잠금(삽입만). COMPLETE · validate · 백엔드 테스트 통과. 스크린샷 `data/archive/screenshots/2026-11-10.jpg`. 정적 배포본 9.4MB.

### 2026-11-11 — 11/11 Daily Snapshot (07:30 KST) · 매일 아침 루틴
- 입력: 00:40Z 수집 한 번에 기본 47 · 종목 94 · 바스켓 52, 단위 불연속 없음. 07:30 KST cutoff — 미국 11/10 종가(10월 CPI 발표일) · 미국채/TIPS/HY OAS · 환율 · 원자재 11/09 관측. **코스피 · 코스닥 · 브렌트의 11/10 일봉은 Yahoo 에 없다**(11/09 다음이 11/11 장중) — 결측 그대로(기사상 11/10 코스피 +4.39% 5239.13). RSS 창 102건 중 25건 수기 태깅. DRAMeXchange 11/10 18:10(GMT+8).
- 결과: 미국 11/10 CPI 예상 상회 뒤 S&P −0.4% · 나스닥100 −0.6% · MOVE +7.5%. 자격 후보 없음 → REGIME v2 NEUTRAL / MIXED 58(세션), 공식 Liquidity Stress / Risk-Off 유지 · PENDING Neutral 1/2(Risk-On 후보는 하루로 끝). AI AI TRADE MIXED(센티 42), 금리 RATES IN RANGE(물가 리프라이싱 쪽), 물가 압력 MIXED, 유가 Supply CONFIRMED, 반도체 UPSWING 32.1(범용 DRAM 현물 약세 확대). history 11/10 행 7개 탭 잠금(삽입만), COMPLETE · 테스트 통과.
- 도구 이동: 배포본 빌더 · 입력 병합 · 빠진 계열 재수집 · 날짜별 재구성 · 단위 검사 · 화면 점검을 세션 scratchpad 에서 저장소 `tools/daily_snapshot/` 로(상대 경로, 화면 점검은 CJS `require('playwright')`). 절차 `docs/daily-snapshot-procedure.md`.
- 루틴: 사용자 요청으로 평일 07:47 KST 예약 작업 'Market Pulse Daily Snapshot 매일 갱신'(이 세션으로 깨움) — 절차 문서 1~12 그대로, 배포는 3ERLmXjNkcrbGmfdjwbHzS 로만. 정책 이벤트 파일 예약(06:40 KST)은 그대로 먼저 돈다.

### 2026-11-11 — 평시 탭 제거 (사용자 요청)
- `config/scenario_checks.yaml` baseline 에 `tab: false` — AI 센티 · 메모리 업사이클(10/07)과 같은 방식이다. 시나리오 점검 목록에서만 빠지고 평시(calm) 판정 엔진 · 설정 · 화면 코드는 남는다.
- 화면: `useScenarioChecks` 가 `focus: calm` 점검을 거른다(`visibleChecks`). 그래서 11/11 이전에 평시가 들어간 채 저장된 날짜(`?date=`)를 열어도 탭이 보이지 않는다. 저장본 · 캡처 파일은 손대지 않았다.
- 탭 순서: AI 센티 → 반도체 사이클 → 금리 → 유가. 다른 탭 화면 · 판정은 바뀌지 않았다. 일일 점검 스크립트(`check_screen.cjs`)에서도 평시를 뺐다.
- 테스트: 탭 목록을 기대하던 2건(`test_ai_regime`, `test_scenario_check`)을 고치고, 평시 단건 판정이 여전히 NEUTRAL 인지 확인하는 검사를 남겼다. visibleChecks vitest 를 추가했다.
