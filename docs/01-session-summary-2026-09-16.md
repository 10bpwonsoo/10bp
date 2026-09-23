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
