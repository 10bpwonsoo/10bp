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
