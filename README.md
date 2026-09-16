# 10bp

한 리포지토리에 독립적인 두 시스템이 있다. 서로 import 하지 않는다.

| 시스템 | 위치 | 성격 |
|---|---|---|
| **Market Pulse AI** | `marketpulse/`, `frontend/` | 멀티에셋 시장 인텔리전스 (읽기 전용 분석·대시보드) |
| **Upbit Trading Bot** | `upbit_cursor.py`, `upbit_trading/` | 업비트 암호화폐 자동매매 (주문 실행) |

---

## Market Pulse AI

뉴스 내러티브와 실제 가격·수급을 대조해 시장이 무엇을, 왜 움직이는지,
그리고 둘이 어긋나는 지점이 어디인지 판별하는 Market Intelligence System.

설계 문서: [`docs/00-analysis-and-architecture.md`](docs/00-analysis-and-architecture.md)

### 현재 상태 — 베타 (P4 완료)

| 단계 | 범위 | 상태 |
|---|---|---|
| **P0** | 데이터 계약, MOCK 파이프라인, FeatureEngine, API, CLI, 대시보드 골격 | ✅ 완료 |
| **P1** | Market State Engine, Theme Score, Sentiment, 룰 추출, Theme Heatmap | ✅ 완료 |
| **P2** | Confirmation, Divergence, Alert, 저장소, 스케줄러 | ✅ 완료 |
| **P3** | Impact Map, 관계 그래프, LLM 이벤트 추출, AI 요약 | ✅ 완료 |
| **P4** | 실데이터 어댑터, RSS, WebSocket, 신호 백테스트 | ✅ 완료 |

**그럴듯한 가짜 숫자로 채우지 않는다.** 못 가져온 종목은 빈칸이고,
coverage 와 confidence 가 그만큼 떨어진다.

### 실행

```bash
# 1. 의존성
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# 2. 백엔드
.venv/bin/python -m uvicorn marketpulse.api.main:app --reload
#    → http://127.0.0.1:8000/docs

# 3. 프론트엔드 (별도 터미널)
cd frontend && npm install && npm run dev
#    → http://127.0.0.1:5173
```

프론트엔드 없이 터미널만으로도 전체 파이프라인을 볼 수 있다.

```bash
.venv/bin/python -m marketpulse.cli snapshot
.venv/bin/python -m marketpulse.cli snapshot --scenario inflation_shock
.venv/bin/python -m marketpulse.cli scenarios
.venv/bin/python -m marketpulse.cli features SOXX   # 한 종목의 파생 지표 검증
```

`snapshot` 출력에는 **발동한 룰과 관측값이 그대로** 찍힌다.

```
  발동 룰
    ✓ [require] Inflation >= 1.0         관측 +1.70
    ✓ [support] Rates >= 0.8             관측 +1.42
    ✓ [support] RiskAppetite <= -0.5     관측 -1.33
```

### Impact Map

열은 노드의 **종류**가 아니라 사건으로부터의 **전파 단계**다. 왼쪽에서
오른쪽이 곧 인과 순서이고, 노드 면색은 **실측 z** 다.

관계 그래프만 그리면 지도는 가설만 보여준다. 예상 부호 옆에 실측을 두어야
"뉴스의 내러티브와 실제 가격이 일치하는가" 에 지도가 답한다. 예상과 반대로
움직인 노드에는 경고가 붙는다.

| 채널 | 표현 |
|---|---|
| 가격 방향 | 노드 면색 — 상승 적, 하락 청 (한국 관례) |
| 관계 부호 | ⊖ 표식. 선 색으로 쓰지 않는다 |
| 관계 출처 | 실선 = 사전 정의, 점선 = LLM 제안 |

사건에서 테마로 뻗는 첫 가지의 부호는 **기사가 말하는 방향**에서 온다.
감성이 아니다. 호재냐 악재냐와 오르냐 내리냐는 독립된 두 축이고, 네 조합이
모두 존재한다 — "물가 둔화"(감성 +, 방향 ↓), "물가 부담 확대"(감성 −,
방향 ↑). 기사에서 방향을 못 읽으면 `ambiguous` 로 두고 아래 연쇄를 판정하지
않는다. 감성으로 대신 채우지 않는다.

예상 부호는 **대표 경로 하나**의 관계 부호 곱이다. 대표 경로는 한 단계 앞
노드에서 들어오는 관계 중 `strength` 가 가장 큰 것이고, `via_edge_id` 로
근거를 추적한다. 다른 경로가 반대 부호를 주면 `sign_conflict` 를 세우고
**판정하지 않는다.** `|z| < 0.5` 는 `muted` — 0.3σ 로 내러티브의 옳고
그름을 말하지 않는다. 대표 경로의 **가장 약한 고리**(`path_strength`)가 `0.5` 에 못 미쳐도
판정하지 않는다 — 스스로 약하다고 적어 둔 관계를 놓고 "예상과 반대" 라고
말하는 것은 과장이다.

실측은 종목과 매크로 factor 에만 붙는다. 테마 점수는 뉴스를 섞은
합성값이라 '실측 가격 반응' 자리에 넣으면 내러티브를 내러티브로 검증하게
된다. 비워 둔다 — 0 으로 채우지 않는다.

옆의 **단계별 실측 반응**은 단계가 깊어질수록 충격이 살아남는지 보여주고,
**목록** 보기는 같은 데이터를 들여쓰기 트리로 낸다(좁은 폭 대체 표현).

### 실데이터

```bash
# 무엇이 되고 무엇이 왜 안 되는지 먼저 본다
python -m marketpulse.cli probe --mode DELAYED

MARKETPULSE_DATA_MODE=DELAYED uvicorn marketpulse.api.main:app
```

**막힌 네트워크에서도 실데이터가 나온다.** 조직 정책이 마켓데이터 호스트를
막아도 GitHub 은 열려 있는 경우가 많다. `github` 공급자가 CBOE·EIA·연준
H.10 의 공개 자료를 매일 미러링하는 저장소를 읽어 8종목을 채운다.

| 종목 | 출처 | 원본 |
|---|---|---|
| `VIX` | `datasets/finance-vix` | CBOE |
| `WTI` `BRENT` | `datasets/oil-prices` | EIA |
| `NATGAS` | `datasets/natural-gas` | EIA |
| `USDKRW` `USDJPY` `EURUSD` `USDCNH` | `datasets/exchange-rates` | 연준 H.10 |

미러라서 원본보다 1~2영업일(환율은 최대 일주일) 늦다. 그 사실을 숨기지
않는다 — 기준을 넘으면 화면이 문장으로 말한다.

> 4개 종목의 데이터가 기준 신선도를 넘었다. 가장 오래된 것은 USDKRW 로
> 7.7일 전 값이다. **지금 시장이 아니라 그때 시장을 보고 있는 것이다.**

일별 주가지수는 이 경로로 구할 수 없다. 없는 것은 없는 대로 두고
coverage 가 떨어진다.

`instruments.yaml` 이 "무엇을 본다" 면 `sources.yaml` 은 "어디서 가져온다" 다.
공급자는 **우선순위 목록**이라 앞에서부터 시도하고 실패하면 다음으로 넘어간다.

| 공급자 | 키 | 담당 |
|---|---|---|
| `yahoo` | 불필요 | 지수·ETF·FX·원자재·VIX. 커버리지가 가장 넓다 |
| `stooq` | 불필요 | Yahoo 장애 시 대체 |
| `fred` | `FRED_API_KEY` | 금리·크레딧·기대인플레이션의 정본 |
| `krx` | 불필요 | 한국 수급·업종지수. 공개 계약이 아니라 불안정하다 |
| `github` | 불필요 | 공개 저장소의 CSV 미러. 다른 호스트가 막혔을 때의 경로 |
| `csv` | – | `data/replay/<id>.csv`. 자동으로 마지막 후보가 된다 |

전부 실패하면 그 종목은 **빠진다.** 0 으로 채우지 않는다. 어느 종목이 어떤
이유로 실패했는지는 화면의 경고와 `probe` 출력에 그대로 남는다.

> **LIVE 는 실시간이 아니다.** 무료 공급자는 일봉 종가만 준다.
> `MARKETPULSE_DATA_MODE=LIVE` 로 두면 데이터는 DELAYED 로 표시되고 그
> 사실이 경고로 화면에 남는다. 지연 데이터를 실시간이라 표시하는 것은 이
> 시스템이 피하려는 바로 그 부정직함이다.

**네트워크가 막혀 있다면** `data/replay/` 에 CSV 를 넣는다. `sources.yaml` 을
고칠 필요가 없다 — 파일이 있으면 자동으로 후보에 붙는다. 형식은
[`marketpulse/data/replay/README.md`](marketpulse/data/replay/README.md).

뉴스는 `feeds.yaml` 의 RSS 를 읽는다. 피드 하나가 죽어도 나머지는 나오고,
전부 죽어도 정량 대시보드는 그대로 동작한다.

### WebSocket

```
ws://127.0.0.1:8000/api/v1/stream?scenario=baseline
```

폴링을 **대체하지 않고 보탠다.** 첫 메시지는 전체 스냅샷이고 그 뒤로는
바뀐 것만 보낸다. 소켓이 끊겨도 5초 폴링이 화면을 유지한다.

### 신호 백테스트

```bash
python -m marketpulse.cli backtest --db data/snapshots.db \
    --stream MOCK:baseline --benchmark SPX --horizon 5
```

**매매 전략이 아니라 신호를 채점한다.** 이 시스템은 주문을 내지 않는다.
검증할 것은 "Market State 판정과 괴리가 실제로 무언가를 앞섰는가" 다.

세 가지를 지킨다.

- 같은 판정이 20틱 이어져도 **신호는 하나**다. 매 틱을 독립 표본으로 세면
  표본 수가 부풀고 지표가 거짓말을 한다.
- 괴리는 **방향 없는 신호**다. 어느 쪽으로 수렴할지 말하지 않으므로
  적중률을 계산하지 않는다.
- 표본 10건 미만은 지표 옆에 그렇게 적힌다. 5건짜리 적중률 60% 는 숫자가
  아니라 인상이다.

진입가는 **판정 시각 이하의 마지막 봉**이다. 그 이후 봉을 쓰면 판정 시점에
없던 정보를 쓰는 것이다.

### 설정 파일

스코어링 수치는 코드에 없다. 전부 YAML 이고 코드 수정 없이 조정한다.

| 파일 | 내용 |
|---|---|
| `instruments.yaml` | 관측 대상 47종목. 요구 3 의 6개 카테고리 |
| `themes.yaml` | 13개 테마와 테마-자산 매핑 |
| `factors.yaml` | 11개 매크로 factor 의 부호 가중 구성 |
| `state_rules.yaml` | Market State 의 require + support 룰셋과 기대 반응표 |
| `divergence_rules.yaml` | 괴리 규칙과 설명 템플릿 |
| `scoring.yaml` | 모든 가중치와 임계값 |
| `lexicon.yaml` | 감성 사전 + 방향 사전. 두 축은 독립이다 |
| `relationships.yaml` | 사건→테마→매크로→업종→자산 사전 정의 관계 46개 |
| `calendar.yaml` | 중앙은행 회의 일정. `verified` 가 거짓이면 화면에 `(미확인)` |
| `sources.yaml` | 종목별 공급자 우선순위. "어디서 가져오는가" |
| `feeds.yaml` | RSS 뉴스 피드 |
| `scoring.yaml` 의 `relationship` | 실측 반응을 판정하는 최소 \|z\| |

> 이 값들은 매크로 상식에 기반한 **초기 제안값**이며 통계적으로 추정된 값이
> 아니다. 실데이터가 붙는 시점에 재검토 대상이다.

### 환경변수

시크릿은 환경변수로만 받는다. **코드나 추적 대상 파일에 넣지 않는다.**

```bash
cp .env.example .env
```

| 변수 | 기본값 | 설명 |
|---|---|---|
| `MARKETPULSE_DATA_MODE` | `MOCK` | `LIVE` / `DELAYED` / `MOCK` |
| `MARKETPULSE_SCENARIO` | `baseline` | MOCK 모드에서 재생할 시나리오 |
| `MARKETPULSE_LLM_ENABLED` | 키가 있으면 `true` | `ANTHROPIC_API_KEY` 가 있으면 자동으로 켜진다. 명시하면 그것이 우선. false 면 정량 파이프라인만 동작 |
| `MARKETPULSE_LLM_MODEL` | `claude-opus-5` | 이벤트 추출·요약·웹검색에 쓰는 모델 |
| `MARKETPULSE_NEWS_SEARCH` | `auto` | LLM 웹검색으로 기사 찾기. `auto` RSS 가 0건일 때만 / `on` 항상 병합 / `off` |
| `MARKETPULSE_HTTP_TIMEOUT_SEC` | `8` | 실데이터 공급자 타임아웃 |
| `MARKETPULSE_HISTORY_BARS` | `300` | 어댑터에 요청하는 히스토리 봉 수. 1년 백분위(252)와 한 분기 전 상관(60+63)에 필요하다 |
| `MARKETPULSE_LLM_SEARCH_TIMEOUT_SEC` | `90` | LLM 웹검색 호출 타임아웃. 서버 측 검색이 여러 번 돌아 추출(8초)보다 훨씬 길다 |
| `MARKETPULSE_NEWS_LIMIT` | `60` | 실데이터에서 받을 기사 수 |
| `ANTHROPIC_API_KEY` | – | LLM 을 켤 때만 필요. 있으면 자동으로 켜진다 |
| `MARKETPULSE_ANTHROPIC_API_KEY` | – | 실행 환경이 `ANTHROPIC_API_KEY` 를 따로 다루거나 걸러낼 때의 우회로. 같은 효과 |
| `FRED_API_KEY` | – | 금리·크레딧을 FRED 에서 받을 때만 필요 |

어떤 모드에서도 **모의 데이터가 실데이터 이름표를 달고 나가지 않는다.**
MOCK 은 MOCK 으로, 지연 데이터는 DELAYED 로 표시된다.

### 시연 통제

시나리오는 결정론적이다. 같은 시나리오는 언제나 같은 화면을 만든다.

```bash
curl 'http://127.0.0.1:8000/api/v1/snapshot?scenario=baseline'
```

시나리오 파일은 60일치 숫자 대신 **체제(regime)와 충격(shock)만** 선언하고
히스토리는 고정 시드로 생성한다. `"SOXX": 1.25` 라고 적으면 FeatureEngine 이
계산한 `z_1d` 가 정확히 `+1.25` 가 된다.

| 시나리오 | 내용 |
|---|---|
| `baseline` | 평시. 어느 상태 룰도 발동하지 않는다 (판정 없음) |
| `inflation_shock` | 요구 14 의 검증 케이스. Oil +2σ / Rates +1.5σ / VIX +1.5σ / Equity −1.2σ → Inflation Shock / Risk-Off |
| `ai_divergence` | 요구 7 의 예시. AI 뉴스·가격은 강한데 외국인 수급이 빠진다. 수급 신호를 끈 현재 설정(`theme.use_flow: false`)에서는 수급 괴리 대신 뉴스↔가격·테마↔자산 괴리만 잡힌다 |
| `ai_sentiment` | 수급을 끈 설정에서의 요구 7 예시. AI 뉴스 톤은 강하게 긍정적인데 반도체·AI 가격은 제자리 → NEWS_VS_PRICE(무반응) 괴리, 온도계 '뉴스가 가격보다 뜨겁다'. 대시보드의 'AI 센티' 탭 |

> **괴리와 알림은 두 틱이 필요하다.** 한 틱짜리 격차는 노이즈와 구분되지
> 않아 표시하지 않고, 알림은 직전 틱과 비교해야 "변화" 를 말할 수 있다.
> CLI 는 `--warmup` 으로 미리 돌리고(기본 1), 화면은 폴링하면서 자연히
> 채워진다. 데모 전에 스케줄러를 몇 분 돌려 두면 첫 순간부터 채워진다.

```bash
# 히스토리를 쌓아 두는 주기 실행기
.venv/bin/python -m marketpulse.scheduler.runner \
    --scenario ai_divergence --interval 60 --db data/snapshots.db
```

### LLM

LLM 은 **선택 사항**이다. 켜면 뉴스 이벤트 추출과 시장 요약 한 문단을
맡고, 꺼지거나 실패하면 그 두 가지만 룰 기반으로 되돌아간다. 정량
대시보드(상태·테마·확인·괴리·알림·영향 경로)는 어느 쪽이든 동일하다.

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # 이것만으로 켜진다. 끄려면 MARKETPULSE_LLM_ENABLED=false
```

세 가지 안전장치를 걸어 두었다.

| 장치 | 동작 |
|---|---|
| 회로 차단기 | 연속 3회 실패하면 5분간 호출을 멈춘다. 인증 실패는 영구 차단 |
| 스키마 검증 | 모델이 만든 테마·종목 ID 중 레지스트리에 없는 것은 버리고, 보정한 필드를 전부 기록한다 |
| 숫자 검증 | 요약문의 모든 숫자가 결정론적 계산 결과에 실재해야 한다. 하나라도 지어내면 템플릿 문장으로 되돌린다 |

키 없이 `MARKETPULSE_LLM_ENABLED=true` 로 켜도 화면 전체가 동작하고
`data_health.llm_status` 가 `failed` 로, 서술 출처가 `template` 로 표시된다.
이것은 `tests/test_llm.py` 에 고정되어 있다.

#### LLM 웹검색으로 기사 찾기 (P5)

RSS 호스트가 전부 막힌 네트워크에서는 뉴스가 0건이 되고 뉴스 감성·괴리·
Impact Map 사건 노드가 함께 잠긴다. LLM 이 켜져 있으면 Claude 의 `web_search`
도구로 기사를 찾는다. 검색은 Anthropic 서버가 수행하므로 `api.anthropic.com`
하나만 열려 있으면 된다.

- **검색 결과 블록만 믿는다.** 제목·URL·게시 시각은 검색 엔진이 돌려준 실재
  페이지의 것이고, 모델이 쓴 문장은 버린다. 존재하지 않는 기사가 섞일 경로가 없다.
- 게시 시각을 모르는 결과와 48시간이 넘은 결과는 버린다. 본문이 없으므로
  `DataMeta.quality` 는 `PARTIAL` 이다.
- 검색어는 `config/feeds.yaml` 의 `search.queries` 다.

```bash
# 키가 맞는지, 결과가 오는지, 무엇이 왜 버려지는지 한 화면에
MARKETPULSE_LLM_ENABLED=true .venv/bin/python -m marketpulse.cli probe --mode DELAYED --llm-search
```

#### 센티멘트 온도계 (P5)

Market State 패널 오른쪽의 게이지. −100(결빙) ~ +100(과열) 한 눈금 위에 바늘
셋을 놓는다 — **가격이 말하는 온도**(이미 계산된 매크로 factor 의 부호·가중
평균), **뉴스가 말하는 온도**(기사 감성의 감쇠·영향도·출처 가중 평균), 그
둘의 **종합**(0.6 / 0.4). 두 바늘의 거리가 임계(30)를 넘으면 내러티브 괴리로
표시한다. 새 데이터는 쓰지 않고, 한쪽이 없으면 나머지로만 재며 그 사실을
문장과 신뢰도에 남긴다. 가중치는 `config/scoring.yaml` 의 `thermometer` 절.

### GOAL Kickstart 에서 차용한 것 (2026-09-15)

GS 의 주간 크로스에셋 리포트 *GOAL Kickstart* 의 표·차트 관례 여덟 가지를
옮겼다. 전부 결정론이고, 새로 붙은 외부 데이터는 없다 — 이미 받던 시계열을
더 길게(300봉) 받아 더 많이 읽을 뿐이다.

| # | 무엇 | 어디에 | 근거 |
|---|---|---|---|
| 1 | **장기 백분위 + 3개월 변화** — 60일 z 옆에 "역사 속 위치" | What's Moving 열, Main Drivers | `MarketFeature.percentile_1y` · `percentile_observations`(252 미만이면 라벨에 봉 수) · `ret_3m` |
| 2 | **재료 스트립** — 온도를 만든 factor·뉴스를 한 눈금 위에 ● 현재 / ◇ 1주 전 | 온도계 아래 | `SentimentThermometer.components` |
| 3 | **1주 전 표식** — 가격에서 나오는 값은 시계열(5봉 전)에서, 뉴스가 섞인 값(온도계 뉴스·종합, 테마 점수)은 저장된 1주 전 스냅샷에서만 | 온도계 ◇, 히트맵 Δ1w 열, What's Moving 막대 ◇, Main Drivers | `z_1d_week_ago` · `FactorScore.week_ago` · `SnapshotRepository.at_or_before()` |
| 4 | **상관 레짐 대조** — 사전 정의 관계를 두 끝 대표 자산의 60일 변화량 상관으로 대조. 확인/약화/뒤집힘. 뒤집힘과 감시 쌍의 분기 대비 부호 반전은 `CORRELATION_REGIME` 괴리 | Impact Map 긴 점선, Divergence | `MarketSnapshot.correlations`(CorrelationBook) · `RelationshipEdge.corr_check` · `divergence_rules.yaml correlation_regime` |
| 5 | **지배 축** — 후보 중 \|z\| 최대 자산과 그것에 ±0.3 이상 연동된 자산 | Market State | `MarketState.dominant_axis` · `scoring.yaml market_state.axis_*` |
| 6 | **이벤트 달력** — 중앙은행 회의 D-2 안이면 confidence 의 지속성 가중 ×0.5, 급변 알림 임계 ×1.25. 판정은 안 바꾼다 | Market State 배지 | `config/calendar.yaml` · `IntelligenceSnapshot.calendar` · 날짜 `verified` 플래그 |
| 7 | **변동성 프리미엄** — VIX − S&P 20일 실현변동성 (연율 %p) | Volatility factor, `risk_event_without_vol_premium` 괴리, What's Moving | 파생 op `vol_premium` · `VIX_RV_SPX` · `VKOSPI_RV_KOSPI` |
| 8 | **경기민감/방어** — XLY ÷ XLU | RiskAppetite factor | `CYC_DEF` |

세 가지 정직성 규칙이 그대로 적용된다. 결측은 0 이 아니다(스트립의 결측 재료는
값 없이 줄만 남고, 저장 스냅샷이 없으면 Δ1w 는 빈 칸이다). 상관은 인과가
아니다(지배 축 문장이 그렇게 말한다). 미확인 날짜는 `(미확인)` 을 달고 나간다.
임계값은 전부 `config/scoring.yaml` 의 `correlation` · `calendar` ·
`market_state.axis_*` 절에 있다.

빌리지 않은 것 — 자산배분 추천표, 로짓 침체·드로다운 확률, PCA 위험선호.
앞의 둘은 이 도구의 범위 밖이고, PCA 는 `factors.yaml` 머리말이 거부한 이유
그대로다("PC1 이 0.7 이라 Risk-Off 입니다" 는 운용자에게 정보가 아니다).

### Investment Intelligence (2026-09-16)

기존 대시보드 **아래**에 붙은 두 번째 층이다. 기존 엔진·스냅샷·API·WebSocket·
컴포넌트는 손대지 않았고, 새 층은 자기 API(`/api/v1/investment`)와 자기
캐시(MOCK 4초, DELAYED/LIVE 15분)로 돈다. 사슬은
MARKET → ALTERNATIVE DATA → INDUSTRY → STOCK → PRICE/FLOW → FUNDAMENTAL → ANALYST → CLAUDE.

| # | 패널 | 엔진 | 무엇을 말하나 |
|---|------|------|---------------|
| 1 | Today's Market Drivers | `investment.py` | 임계(\|z\| ≥ 0.8) 이상 움직인 시장 변수와 그것에 민감한 종목 |
| 2 | Alternative Data Pulse | `alternative_data.py` | 41개 대체지표를 1D/1W/1M/3M·z·백분위 + **왜 중요한가·누가 영향받나** 로. 없는 것은 MISSING 으로 남긴다 |
| 3 | Market → Stock Impact | `stock_exposure.py` `stock_impact.py` | 충격 × 노출 × 통계 신뢰 × 사업 관련성 × 현재 관련성. 20/60/120일 beta·상관과 `stock_exposures.yaml` 의 사업 노출을 나란히 |
| 4 | Semiconductor Intelligence | `semiconductor.py` | 메모리 현물 · 글로벌 peer · 국내 3사 · EPS 의 방향 합의 |
| 5 | Commodity → Industry → Stock | `commodity_impact.py` | 원자재 z → 산업 → 매출/원가/수요 경로별 수혜·피해와 실측 반응 |
| 6 | Unusual Stock Movers | `stock_anomaly.py` | 수익률·거래량·상대 z. 뉴스 없는 거래량 급증은 UNEXPLAINED_ACTIVITY — '매집' 이라고 하지 않는다 |
| 7 | Theme → Stock | `investment.py` | 기존 테마 점수가 종목에서 확인되는가(confirmed/muted/mismatch) |
| 8 | Analyst Revision Monitor | `analyst.py` | EPS·목표가·투자의견 변화. 공개 API 가 없어 `data/replay/analyst/<ID>.csv` 적재만 |
| 9 | Price vs Fundamental Divergence | `stock_divergence.py` | 가격↓/EPS↑, 가격↑/산업데이터↓, 업종↑/종목↓ 등. 지속 틱마다 severity 가 오른다 |
| 10 | Stock Intelligence | `stock_explanation.py` | WHAT / WHY / WHAT CHANGED / WHAT NEXT 를 먼저. 원인은 CONFIRMED_DATA … UNKNOWN 6종에 확신 HIGH/MEDIUM/LOW |
| 11 | Watchlist Intelligence | `investment.py` | 20종목 한 줄 + 배지(NEW_EVENT, EPS_REVISION, ALTERNATIVE_DATA_SIGNAL, COMMODITY_IMPACT, UNUSUAL_MOVE, THEME_*) |
| 12 | Claude Commentary | `commentary.py` | API 를 부르지 않는다. `data/commentary/<date>.json` 의 수기 해설을 FACT/NEWS/ANALYST/INTERPRETATION/UNKNOWN 으로 분리해 보여준다 |

설정은 `config/universe.yaml`(36종목·41대체지표), `config/stock_exposures.yaml`
(사업 노출), `config/intelligence.yaml`(모든 임계·가중치)에 있다. 코드에
숫자를 박지 않았다.

**실데이터.** 종목·미국 peer·원자재·중국 지수·대리 ETF 는 Yahoo 차트 API 로
받고 `alt_daily` 테이블에 일별 upsert 한다. 같은 날 이미 받은 계열은 다시
받지 않고, 공급자가 실패하면 저장된 마지막 값을 **STALE** 로 돌려준다.
DRAM·NAND 현물, BDI·SCFI, 중국 PMI, 석탄·니켈·아연·나프타, 외국인·기관 수급,
애널리스트 컨센서스는 공개 API 가 없거나 이 환경에서 차단된다 — 화면에
'없음' 으로 남기고 억지로 채우지 않는다. CSV 를 `data/replay/alternative/<ID>.csv`
(date,close) 또는 `data/replay/analyst/<ID>.csv` (date,broker,rating,target_price,eps_fy1)
에 넣으면 그 자리가 채워진다.

**말하지 않는 것.** 상관을 인과로 쓰지 않는다(lead/lag 는 "역사적으로 앞서는
경향" 까지). 거래 주체를 단정하지 않는다. 통계 부호와 사업 노출 부호가
다르면 점수를 깎고 '상충' 을 남기되 어느 쪽이 맞다고 하지 않는다.

MOCK 시나리오 6개가 추가됐다: `commodity_shock` `memory_upcycle` `oil_spike`
`china_stress` `rates_stock_divergence` `eps_price_divergence`.

### 수급(flow) 신호는 꺼져 있다

`config/scoring.yaml` 의 `theme.use_flow: false`. 국내 수급(외국인·기관 순매수)은
무료 공급자가 없어 항상 결측이었고, 2026-09-15 사용자 결정으로 뉴스 감성이 그
역할을 맡는다 — 테마 점수 가중치의 수급 0.20 을 뉴스 감성이 흡수했고(0.45),
히트맵·확인 매트릭스의 Flow 열과 뉴스↔수급·가격↔수급 괴리 짝을 뺐다.
수급 데이터가 붙는 날 `use_flow: true` 로 돌리고 가중치와 `divergence_rules.yaml`
의 두 짝(git 이력)을 복원하면 된다. 코드는 그대로 남아 있다.

### 테스트

```bash
.venv/bin/python -m pytest
```

네트워크 없이 돈다. 엔진이 순수 함수이기 때문이다.

프런트 렌더 테스트(Investment Intelligence 12패널 + App 에서 기존 패널이 먼저 오는지):

```bash
cd frontend && npm test
```

> ⚠️ 루트 `conftest.py` 가 `upbit_trading/` 수집을 막는다. 그 안의
> `test_sql_load.py` 는 이름만 테스트일 뿐 **import 되는 순간 SQL Server 에
> 접속해 데이터베이스를 만들고 라이브 Upbit API 를 호출하는** 스크립트다.
> 이 가드를 제거하지 마라.

### 구조

```
marketpulse/
├── models/      데이터 계약 7종 + 공통 타입 (pydantic v2)
├── config/      instruments · themes · factors · state_rules · scoring
│                lexicon · divergence_rules · relationships
├── adapters/    MarketAdapter / NewsAdapter
│                http(회로 차단기) · market/{mock,live,providers}
│                news/{mock,rss}
├── engines/     features · normalize · scoring · factors · market_state
│                confirmation · sentiment · direction · theme · divergence
│                alert · relationship · korean · orchestrator
├── ai/          rule_extractor(기준선) · client · validation
│                event_extractor · summarizer
├── analysis/    신호 백테스트
├── storage/     SnapshotRepository + SQLite 구현
├── scheduler/   주기 실행기
├── vendor/      technical_indicators.py 이식본
├── api/         FastAPI 라우트
├── data/mock/   시나리오 파일
├── data/replay/ 로컬 CSV (네트워크가 막혔을 때의 실데이터 경로)
└── cli.py       터미널 대시보드
frontend/        React 19 + TypeScript + Vite
```

---

## Upbit Trading Bot

업비트 자동매매 시스템. Market Pulse AI 와 독립적으로 동작한다.

### 설정

1. `.env.example` 을 `.env` 로 복사한다.
2. **모든 API 키와 시크릿은 `.env` 에 넣는다.** `upbit_trading/config.py` 는
   전부 환경변수에서 읽으므로 소스 파일에 키를 적을 필요가 없고, 적어서도
   안 된다 — 그 파일은 git 추적 대상이다.

```
UPBIT_ACCESS_KEY=...
UPBIT_SECRET_KEY=...
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
```

3. 매매 파라미터(시크릿이 아닌 값)는 `upbit_trading/config.py` 에서 조정한다.

### 실행

```bash
pip install pyupbit python-telegram-bot requests pandas numpy \
            sqlalchemy pyodbc PyJWT yfinance finance-datareader python-dotenv
python upbit_cursor.py
```

DB 는 MS SQL Server 를 쓰며 `DB_SERVER` 등 환경변수로 지정한다.

### 구조

```
upbit_cursor.py               메인 리포트 스크립트
upbit_trading/
├── config.py                 설정 (환경변수 로드)
├── trader.py                 주문 실행
├── trading_engine.py         매매 엔진
├── scalp_engine.py           스캘핑
├── strategies.py             시그널 계약 (Signal / TradeSignal / Strategy)
├── strategy_box_range.py     박스권 전략
├── strategy_historical_low.py 역사적 저점 전략
├── price_momentum.py         가격 모멘텀 분석
├── data_collector.py         Upbit / Binance 수집
├── db_manager.py             SQL Server 접근
├── backtester.py             백테스트
├── risk_manager.py           리스크 관리
├── position_tracker.py       포지션 추적
├── notification_manager.py   알림 포맷
├── telegram_bot.py           텔레그램 전송
├── telegram_commands.py      텔레그램 명령
├── technical_indicators.py   기술적 지표
└── rate_limiter.py           API 요청 제한
```
