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

### 실시간 2 탭 — decision cockpit (2026-09-29)

실시간 탭은 `실시간 2` 하나다(2026-10-07 에 기존 화면 탭 `실시간` 을 지웠다 — 아래
"탭 정리" 절). 기존 화면(Market State → 히트맵 → What's Moving → … → Investment
Intelligence)은 cockpit 아래 Details 안에, 그리고 cockpit 집계를 못 받을 때의 대체
화면으로 그대로 남아 있다. `실시간 2` 가 아래의 decision cockpit 이다.
`실시간 2` 는 22일 히스토리·히트맵·What's Moving·해설·알림 타임라인을 앞에 늘어놓지
않는다. `engines/cockpit.py` 가 `config/cockpit.yaml` 로 스냅샷·Investment·히스토리·
AI/금리/유가 판별 결과를 한 화면으로 고른다. 순서는 MARKET NOW(판정·확신 HIGH/MEDIUM/LOW·
지속 일수·이전 판정·핵심 변수 ≤4·한 문장·작은 스파크라인·커버리지) → TODAY'S MARKET
DRIVERS(≤5. |z| 순이 아니라 강도 × 커버리지 + 판정 확인 + 지속성 + 뉴스 톤에 driver 별
시장 영향 가중을 곱한 importance 순. 각 driver 에 증거 z·why·출처) → CROSS-ASSET
CONFIRMATION(EQUITY/RATES/CREDIT/VOLATILITY/USD/OIL/GOLD 를 판정별 기대 방향과 대조해
CONFIRM / HEADWIND / DIVERGE / FLAT / MISSING, "n / m assets" 는 확률이 아니다) + KEY
DIVERGENCE(≤2, 나머지는 View all) → MARKET LEADERSHIP(주식 테마만, 1D | vs market 1W |
breadth, 리더 ≤4·후미 ≤3) + Compact THEME PULSE(≤6, PRICE/NEWS/REL 화살표) → MARKET →
STOCK TRANSMISSION(driver → 산업 → 종목, 종목 z 로 CONFIRMED / UNCONFIRMED /
CONTRADICTED / NO DATA) → STOCK RADAR(6~8, 이유 한 줄과 why/watch 구분) → LIVE
CATALYSTS(고정 높이·내부 스크롤, 기사 ≤2줄, 클릭하면 WHY / RELATED / PRICE CONFIRMATION,
CRITICAL/HIGH/MEDIUM 은 시장 영향 점수, 유사 기사는 Jaccard 로 묶고 중요 알림을 합침) →
EARNINGS / FLOW PULSE(컨센서스가 있을 때만; 빈 "0/36" 은 그리지 않는다) → WHAT MATTERS
NEXT(≤5, CONFIRMING / WATCH / REVERSING, 달력은 스냅샷에 있는 공식 이벤트만) → Compact
Watchlist(≤5, NEWS/EPS/PRICE/MACRO/ALT 표식) → Data Status 한 줄. 데스크톱은 40|60 ·
50|50 · 100 · 50|50 · 60|40 격자, 모바일은 MARKET NOW → TOP 3 DRIVERS → CROSS-ASSET →
LEADERSHIP → RADAR → CATALYSTS → NEXT 한 열이고 나머지는 접힌다. 기존 Market State·
히트맵·What's Moving·Why·Impact Map·Alert·Data Health·Investment Intelligence 는
"Details / Diagnostics" 아래에 그대로 열린다 — 파이프라인은 하나도 지우지 않았다.
엔드포인트 `GET /api/v1/cockpit`. 보조 계층(AI·금리·유가·히스토리)이 실패해도 cockpit
은 그 부분만 비운 채 뜨고, cockpit 자체가 실패하면 예전 화면으로 돌아간다. 없는 데이터는
빈 칸(MISSING / NO DATA)이고 확률 표현은 쓰지 않는다.

#### 실시간 2 · MARKET REGIME HISTORY · 1M (2026-09-29)

`실시간 2` 에만 붙는 히스토리 층이다(기존 `실시간`·물가·유가·AI 센티 탭은 그대로). MARKET NOW 와
TODAY'S MARKET DRIVERS 사이에 놓여 "현재 regime 이 언제 시작됐고, 직전은 무엇이었고, 한 달
동안 시장의 색이 어떻게 바뀌었고, 무엇이 그 전환을 만들었는가" 에 답한다. 재료는 판정 히스토리
재생(`engines/state_history.py`, 같은 엔진)이고 `engines/regime_history.py` 가 그 위에 두 층을
얹는다. (1) 거래일 스냅샷: 저장소·메모리의 장중 판정 관측이 있으면 그날 가장 오래 유지된
dominant regime 과 마지막 end regime, dwell(유지 비중), 장중 전환 횟수를 남긴다 — 관측이 하루
한 번이면 dwell 은 None 이다(0 이나 100 으로 채우지 않는다). (2) Display Regime: 하루짜리 flip 이
띠의 뜻을 지우지 않게 `config/cockpit.yaml` `history.display` 규칙(연속 2거래일 같은 raw regime,
또는 확신 ≥ 80 인 강한 하루, dwell < 0.5 인 날은 확인으로 세지 않음)으로 안정화한다. Raw State 는
같은 응답의 `days[].raw_state` 에 그대로 있고 날짜를 누르면 보인다. Taxonomy 는 Risk-On ·
Neutral / Mixed · Growth · Inflation · Policy Driven · Liquidity Stress / Risk-Off(RISK_OFF 합침) ·
Geopolitical(있는 날만). 카드 구성은 A CURRENT REGIME CONTEXT(Current · Duration · Previous · 1M
Transitions · 1M Share) → B REGIME BAND(거래일당 셀 하나, 같은 regime 은 블록, 전환일 ▲ 표식,
hover 툴팁 = 날짜·dominant/end·evidence·driver·top evidence 2, 클릭 = raw 판정·dwell·factor 상세)
→ C MARKET COMPOSITE SPARKLINE(선 1개 · 0 기준선 · 현재값 · 5D slope) → D DRIVER HEAT STRIP(Risk
Appetite · Liquidity · Rates · Inflation · Credit factor z 의 농도, 오른쪽 현재 화살표) → E 1M REGIME
SHARE(가로 막대, 일수 비중이지 확률이 아니다) → F RECENT TRANSITIONS(실제 전환일만 최근 3개,
primary driver = 도착 regime 과 결이 맞는 factor 중 변화 최대, confirmation = 그날 주도 변수
1~2, 클릭하면 evidence). 데스크톱은 띠·스파크라인·히트 | 컨텍스트·비중, 아래 전환; 모바일은
컨텍스트·띠·스파크라인만 펴고 drivers / share / transitions 는 접는다. 기간은 1M 이고 3M/6M 은
일별 스냅샷이 그만큼 쌓여야 켜진다 — 없는 기간을 만들지 않는다. 9/29: Neutral 8/27~9/11(11일)
→ Liquidity Stress 9/14 하루(확신 84) → Neutral 3일 → Policy Driven 9/18~22 → Liquidity Stress
9/23~29 4일째, 전환 4회, 현재 regime 비중 23%, composite −39(5D −74).

#### 실시간 2 · STOCK RADAR의 ANALYST VIEW와 WHAT MATTERS NEXT의 전파 경로 (2026-09-29)

두 카드만 확장했고 나머지 구조는 그대로다. **ANALYST VIEW**: radar 종목(최대 8)에 대해서만 외부
애널리스트 코멘트를 한 줄 붙인다 — `이름 · 증권사 · 날짜(freshness nD)` 와 "왜 그렇게 보는가" 한
문장 paraphrase. 누르면 Analyst / Broker / Date / Rating / Target / Key view / Key variable / Source
링크와 **SYSTEM vs ANALYST**(시스템 축 THEME·FUNDAMENTAL·MARKET·MACRO 와 애널리스트 톤을 나란히,
갈리면 FUNDAMENTAL / PRICE GAP 같은 라벨만 — 어느 쪽이 맞다는 결론 없음)가 열린다.
재료는 `data/analyst_views/manual/*.json`(웹에서 이름·증권사·날짜·URL·맥락이 모두 확인된 것만 수기로)과
`data/analyst_views/cache.json`(LLM 웹검색, TTL 12h)이고, `adapters/analyst_view.py` 의 `validate_view`
가 필드가 하나라도 비거나 30일을 넘으면 버린다 — 그 종목은 줄 자체가 없다. 검색 provider 는
`LLMClient.search_structured`(web_search + JSON 스키마)로 돌고 응답의 URL 이 실제 검색 결과에 없으면
버린다. `GET /api/v1/analyst-views` 는 저장된 것을 바로 주고 새 검색은 백그라운드라 radar 가 먼저 뜬다.
키가 없으면 provider 는 꺼지고 저장된 코멘트만 쓴다. 9/29 수기 확인 5/8: SK하이닉스(이수림·DS투자증권
9/29) · Micron(Tristan Gerra·Baird 9/28) · Quanta(Chad Dillard·Bernstein 9/24) · Applied
Materials(Shane Brett·Morgan Stanley 9/28) · 삼성전자(정우성·LS증권 8/31, 29D). Super Micro·Tokyo
Electron 은 실명 노트가 30일을 넘고 Datadog 의 Daiwa 노트는 이름이 확인되지 않아 싣지 않았다.

**WHAT MATTERS NEXT → Issue Monitor**: 항목은 한 줄 그대로이고 누르면 아래에 MARKET TRANSMISSION PATH 가
열린다 — Trigger → First-order → Asset impact → Theme / Industry → Stocks(DIRECT / SECONDARY / TERTIARY,
tier 당 5개 + View all). `config/cockpit.yaml what_matters_next.paths` 가 driver × 방향별 예상 경로이고
`engines/issue_path.py` 가 단계마다 지금 z · AI 세그먼트 상대 z · 테마 가격 모멘텀 · 종목 z 로 CONFIRMED /
PARTIAL / UNCONFIRMED / CONTRADICTED / DATA MISSING 을 붙인다. EXPECTED 와 OBSERVED 를 따로 적고 결론은
관측이 갈리면 그렇게 쓴다("부담은 존재하지만 압력은 A 에 집중, B 는 견조"). WHAT WOULD CONFIRM? 체크리스트
n/m. AI 이슈는 ai_regime 의 value_chain / stocks 를 그대로 재사용한다. 기존 MARKET → STOCK TRANSMISSION
카드("지금 일어나는 전파")는 그대로다. MARKET ISSUE ↔ STOCK 양방향: 경로의 radar 종목엔 RADAR ● 이 붙고
누르면 radar 로, radar 의 Related market issues 를 누르면 그 이슈가 열린다.

#### 실시간 2 · 표현 층 — 영어 상태값 + 한글 의미 (2026-09-30)

CROSS-ASSET CONFIRMATION 과 WHAT MATTERS NEXT(전파 경로 포함)의 판단 로직·계산은 그대로 두고 표현만
바꿨다. 원칙은 `ENGLISH STATUS` 가 먼저, 짧은 한글 의미가 뒤 — 영어를 치환하지 않는다(CONFIRM · HEADWIND ·
DIVERGE · PARTIAL · CONTRADICTED · EXPECTED · OBSERVED · DIRECT / SECONDARY / TERTIARY · WATCH / CONFIRMING /
REVERSING 유지). 화면 순서는 `결론 → 쉬운 한글 해석 → 핵심 근거 → 전문 상세`. `config/cockpit.yaml explain`
(regime_short, 자산별 상태 의미 템플릿, 괴리 짝별 현상·왜 중요한가, 기간 자동 해석, 단계 설명, tier 노출 수)과
프런트 `components/ko.ts`(상태값 한글 사전·모바일 짧은 꼬리·tier 툴팁·용어집·일치도 색)가 표현 층이다.
CROSS-ASSET: 목적 한 줄 → CURRENT MARKET VIEW + "7개 중 5개가 현재 Risk-Off 판단과 같은 방향" → MARKET READ
1~2문장(숫자 반복 없음) → RISK / MACRO / COMMODITY·SAFE HAVEN 그룹에 대표 지표(S&P 500 −1.2σ ↓)와 영어 상태 +
한글 의미 → KEY DIVERGENCE 는 현상 → WHY IT MATTERS → REFERENCE(Expected relationship / Recent correlation) 순
→ 색상 legend("좋고 나쁨이 아니라 일치 여부"). WHAT MATTERS NEXT: 목적 두 줄 → 닫힌 항목엔 영어 상태 + 한글,
CURRENT 1D / 5D / 1M z 와 자동 해석("오늘은 일부 되돌렸지만 최근 5일 상승 흐름은 유지"), WHY IT MATTERS 만 →
열면 SUMMARY(MAIN IMPACT 체인 · n / m stages confirmed · MOST EXPOSED · RELATIVE EXCEPTION) → EXPECTED /
OBSERVED(각각 뜻 한 줄, 테마별 WEAK / RESILIENT + 한 줄 해석) → ① TRIGGER ② TRANSMISSION ③ ASSET IMPACT ④ THEME /
INDUSTRY(영어 단계명 + 왜 이어지는지 한글 + 단계 상태 영어·한글) → STOCK IMPACT(DIRECT 4 · SECONDARY 3 · TERTIARY
접기, 우선순위 radar → |z| → 뚜렷한 확인 → 중요한 contradiction; 종목마다 EXPECTED / OBSERVED / 상태 + 의미,
CONTRADICTED 는 오류가 아니라 "다른 driver 가 더 강하다"는 신호로 설명) → WHAT WOULD CONFIRM?(n / m conditions
confirmed + "확률이 아니라 조건 수" + 한 줄 해석). 전문 용어(Real Yield · Duration · Credit Spread · Relative
Strength · Breadth 등)는 그대로 두고 점선 밑줄 툴팁으로 뜻을 붙였다.

#### 실시간 2 · DRIVER HEAT 의미 층과 MARKET LEADERSHIP → Leadership Intelligence (2026-09-30)

**DRIVER HEAT**: factor 이름을 경제적 의미로 바꿔 부른다 — Risk Appetite(위험선호) · Liquidity Condition(유동성
환경) · Rate Pressure(금리 압력) · Inflation Pressure(인플레이션 압력) · Credit Stress(신용 스트레스). 화살표 옆에
현재 의미를 붙인다("Credit Stress ↑↑ 신용 스트레스 확대", "Rate Pressure ↓ 금리 압력 완화") — 점수 부호의 번역이
아니라 `config/cockpit.yaml history.drivers[].meaning` 의 factor 별 의미다. 대표 계열의 1D / 5D z 를 함께 보이고
(Rates → US 10Y, Credit → HY OAS, Liquidity → MOVE 역방향 …) 단기와 5일이 갈리면 한 줄 해석("오늘 금리는
하락했지만 최근 5일 장기금리 상승 압력은 유지")을 붙인다. legend: COLOR = factor 방향(빨강 +, 파랑 −, 좋고 나쁨
아님) · ARROW = 현재 경제적 의미.

**MARKET LEADERSHIP**: 기본 화면은 그대로 compact(1D z | vs market | breadth)이고 행마다 SYSTEM VIEW 한 줄, 맨 위에
LEADERSHIP READ(판정 · 상대강도 · breadth 종합 한두 문장)가 붙는다. 테마/섹터를 누르면 아래에 LEADERSHIP DETAIL 이
열린다: WHY LEADING?(시장 데이터 기반 1~3개) → MARKET CONFIRMATION(PRICE / RELATIVE STRENGTH / BREADTH / NEWS /
FUNDAMENTAL / DRIVER·MACRO 를 영어 상태 + 한글 의미로, 리더와 후미의 의미를 따로) → SYSTEM VIEW(INTERNAL — 내부
데이터 해석 + DRIVER / QUALITY / RISK; QUALITY 는 BROADENING · NARROW · FUNDAMENTAL-LED · PRICE-LED · MACRO-DRIVEN ·
NEWS-DRIVEN · FRAGILE) → STREET VIEW(EXTERNAL — 기관 · 애널리스트(확인된 경우만) · 날짜 · 원문 한 줄 · 요약 · 핵심
변수 · 출처; 견해가 갈리면 SYSTEM READ 로 나란히, 컨센서스로 합치지 않음; 없으면 영역 숨김) → KEY STOCKS(≤5,
leadership 을 설명하는 종목, RADAR ● 은 radar 로 연결) → WHAT TO WATCH(≤3). 상세는 카드 안이 아니라 MARKET LEADERSHIP 아래 그리드 전체 폭의
Full-width Detail Panel 로 열린다(아래 "Leadership Detail Panel" 항목). 엔진 `engines/leadership_intel.py` 는
새 판정을 만들지 않고 기존 값(1D z · 1주 상대 · breadth · 테마 뉴스 톤 · AI 전파 단계 · 관련 계열 z · 종목 상대 z)을
`config/cockpit.yaml leadership_intel.hints`(driver · links · risk · watch · stocks · view 템플릿)와 합쳐 문장으로
만든다. STREET VIEW 재료는 `data/street_views/manual/*.json`(9/30 수기 확인 6건: JPMorgan Harlan Sur 9/18 · UBS 9/19 ·
DS투자증권 이수림 9/29 · Goldman Sachs Ryan Hammond 9/25 · Deutsche Bank 9/18 · JPMorgan Matthew Lofting 9/23)이고 기관 ·
발행일 · URL · 요약이 없거나 30일을 넘으면 버린다. LLM 문장 생성은 쓰지 않았다 — 템플릿이 데이터만 설명한다.

#### AI 센티2 · STOCK IMPACT MAP · STOCK RADAR · NEWS → VALUE CHAIN → STOCK — 스캔 / 클릭 분석 (2026-10-01)

세 영역의 역할을 나누고 progressive disclosure 로 바꿨다(`config/ai_regime.yaml stock_view`, `engines/ai_stock_view.py`,
`models StockSignal · RadarItem · RadarBucketView · NewsCard · StockView`, 프런트 `AiStockSections.tsx`; 네 축·레이더 버킷·뉴스
체인 계산은 그대로, AI 센티 기본 탭은 영향 없음). **STOCK IMPACT MAP** = "개별 종목에서 지금 특이한 변화가 무엇인가":
50종목 중 anomaly 가 있는 종목만 **TOP STOCK SIGNALS** 8~10 (같은 세그먼트·같은 라벨은 2개까지), 종목마다 대표 anomaly 라벨
하나(CONFIRMED · FUNDAMENTAL LEADING · RELATIVE BREAKOUT / BREAKDOWN · NEWS > PRICE · MACRO RESILIENT · PRICE LEADING ·
MACRO SENSITIVE · PRICE > NEWS · DIVERGENCE — 네 축과 1주 상대 %p 의 조합 규칙, 위에서부터 먼저 걸리는 것) + 신호 한 줄 +
STOCK READ 한 문장(템플릿) + Fundamental / Macro 두 상태 + KEY TENSION("Price Strong / Fundamental Neutral", MIXED 인 이유).
클릭하면 WHAT CHANGED · PRICE / RELATIVE · FUNDAMENTALS · NEWS & SENTIMENT · MACRO EXPOSURE · SYSTEM READ · WHAT TO WATCH(≤3).
선별 순서는 수익률이 아니라 상대강도 크기 · 축 간 괴리 · 뉴스 언급 · 확인 여부로 만든 '특이성'. 네 축 전체 표(50행)는 View all.
**STOCK RADAR** = "그중 다시 확인할 가치가 높은 종목": 버킷을 CONFIRMED LEADERS · IMPROVING SETUPS · DIVERGENCES / WATCH
(narrative_ahead + fundamentals_ahead 합침) · MACRO SENSITIVE 로 바꾸고 버킷마다 설명 한 줄, 종목마다 Relative · Price ·
Fundamental 세 지표 + WHY WATCH 한 줄, 버킷당 기본 3 + View all. 숫자 종합 점수는 만들지 않는다. **NEWS → VALUE CHAIN →
STOCK** = "뉴스가 어디까지 번지는가": `news_impact.top_n` 5 → 12, 같은 catalyst(제목 토큰 Jaccard ≥ 0.3 또는 driver·핵심 종목이
같고 토큰 2개 이상 겹침)는 하나로 묶어 ×n 표시, TOP IMPACT 3 + OTHER RELEVANT(기본 6, View more). 기본 row = 톤 + NEGATIVE /
POSITIVE 라벨 · 제목 · 카테고리 · PRIMARY IMPACT · KEY STOCKS ≤3 · PRICE REACTION(CONFIRMED · CONFIRMED NEGATIVE · NOT PRICED
· RESILIENT · UNCLEAR, 한글 설명). 클릭하면 WHY IT MATTERS(driver 별 템플릿) · PRIMARY / SECONDARY / TERTIARY · KEY STOCKS ·
CURRENT PRICE REACTION · SYSTEM READ · SOURCE. NEWS IMPACT 범례(−100 / 0 / +100, 확률·전망 아님)와 뉴스 × 가격 관계 표를
붙였다. 정렬은 |톤| + 전파 폭 + 가격 반응 확인 + divergence + 묶인 기사 수의 priority. 9/29 TOP STOCK SIGNALS: Tokyo
Electron RELATIVE BREAKOUT(+16.1%p) · HD현대일렉트릭 · SK하이닉스 · 두산에너빌리티 FUNDAMENTAL LEADING · Oracle RELATIVE
BREAKDOWN(−10.1%p) · Ciena · Datadog RELATIVE BREAKOUT · Arm · Digital Realty · AppLovin; NEWS TOP: 엔비디아 자사주(NOT PRICED)
· 삼성 $1bn 투자 ×2(NOT PRICED) · OpenAI 모델 출시 취소(RESILIENT). 테스트 +3(백엔드) +1(프런트).

#### AI 센티2 · BASKET READ · BREADTH READ — 숫자 → 구조 → 의미 (2026-10-01)

AI BASKET GROUPS 와 AI BREADTH 의 자동 코멘트를 바꿨다(`config/ai_regime.yaml basket_read · breadth_read`,
`engines/ai_reads.py`, `Leadership.read` · `Breadth.read`; AI 센티 기본 탭의 예전 문장은 그대로). 두 코멘트는 합치지 않고 각자
자기 카드의 데이터만 쓴다. "1주 리더는 … 1개월 리더는 … 회전 중" 이나 "20일선 위 59% · 5일선 위 12% …" 처럼 화면 숫자를
다시 읽는 문장은 폐기했다. **BASKET READ**(최대 3문장): ① 큰 그림 — Nasdaq 을 실제로 outperform 하는 그룹이 있으면 TRUE
LEADERSHIP, 전부 밑돌면 "뚜렷한 AI leadership 국면이 아니다"(1위라도 Nasdaq 대비 음수면 리더라 부르지 않는다); 1M·1W 1위가
다를 때는 옛 리더 둔화 · 상대격차 ≥ 1%p · breadth · rel z · 1D 지속 다섯 조건 중 4개 이상이어야 rotation, 2개 이상이면
"변화 가능성일 뿐 아직 rotation 으로 확인되지 않았다", 그 아래면 언급하지 않는다. ② 가장 중요한 강점 — 1위 그룹이 실제
outperform 인지 방어적 상대강도인지, breadth 가 좁은지(<50%)로 질을 말하고, 가격은 약한데 20일선 위 비율 ≥ 70% 이고 1M 상대
> 0 인 그룹은 "중기 구조가 훼손되지 않았다" 대비 절. ③ 가장 중요한 약점 — 1W ≤ −0.5%p · 1M ≤ 0 · breadth < 50% 가 겹치면
구조적 laggard, 아니면 단기 약세. **BREADTH READ**(최대 3문장): ① 단기(5DMA · 상승 비율 ≤ 20% → BROAD SELL-OFF, ≥ 80% →
BROAD ADVANCE)와 중기(20DMA ≥ 50% 과반 유지 / ≥ 75% 대부분)를 한 문장에서 분리 ② 그룹별 breadth 는 최대−최소 ≥ 20%p 일
때만 가장 견조한 그룹과 가장 취약한 그룹의 contrast ③ 다음 확인 포인트 — 20DMA 1주 변화 ≤ −15%p 면 "빠르게 줄고 있어 추가
하락 여부가 단기 조정과 구조적 약세를 구분할 핵심 신호", ≥ +10%p 면 확산 지속 여부, 그 외 과반 유지/회복 여부. 9/29 BASKET:
"AI 그룹 전체가 Nasdaq 을 밑돌고 있어 뚜렷한 AI leadership 국면이 아니며, Memory → Software 순위 변동은 아직 rotation 으로
확인되지 않았다. Software 는 peer 대비 가장 선방하지만 breadth 가 좁아 방어적 상대강도에 가깝고, Memory 는 단기 가격은 약하지만
중기 구조가 훼손되지 않았다. Power / Data Center 는 가장 구조적인 laggard." BREADTH: "단기 매도 압력은 전반으로 확산됐지만
20일선 기준 절반 이상이 추세를 유지해 중기 붕괴보다는 급격한 단기 deterioration. Semis · Memory 견조 vs Power · Software 약함.
20DMA breadth 의 추가 하락 여부가 핵심 신호." 테스트 +3(백엔드) +1(프런트).

#### AI FUNDAMENTAL TRANSMISSION 근거 유형 태그 + 메모리 가격 일일 수집 워크플로 (2026-10-01)

전파 단계의 점수가 무엇으로 만들어졌는지 행마다 **NEWS / PRICE / DATA** 태그로 적는다(`TransmissionStage.basis`,
`ChainStage.basis`; 범례 한 줄). NEWS = 기사 톤, PRICE = 세그먼트 주가의 Nasdaq 대비 상대강도, DATA = 메모리 데이터 · EPS
revision. 결측 입력은 태그에서 빠지므로 "산업 데이터" 로 보이는 행이 실제로는 뉴스·주가 기반임이 드러난다. 9/29: HBM 만
DATA(+NEWS), Equipment · Foundry/Packaging · DC Infra · GPU 는 PRICE+NEWS, Hyperscaler Capex 는 NEWS+PRICE, AI Narrative 는
NEWS, Commodity Memory · EPS 는 NO DATA. 그리고 Commodity Memory 가 실제 데이터로 채워지도록
`.github/workflows/collect-memory-prices.yml` 을 추가했다 — 평일 03:40 UTC(12:40 KST, DRAMeXchange 11:00 GMT+8 갱신 뒤)에
`python -m marketpulse.scripts.collect_memory_prices` 를 돌려 `data/replay/alternative/*.csv` 에 그 날 줄을 붙이고 변경이
있으면 커밋한다(키·비밀 없음, `workflow_dispatch` 로 수동 실행 가능; 기본 브랜치에 들어간 뒤부터 스케줄이 돈다). 이 세션에서
수집기를 한 번 돌려 10/1 줄을 더했다(DRAM 46.321 · DDR5 57.90 · NAND 19.883 · DXI 1,112,072; Silicon Analysts 는 이
환경에서 막혀 HBM 앵커는 그대로). 변화율은 2봉부터, z 는 20봉이 차면 나온다.

#### AI 센티2 · AI CHAIN VIEW — Transmission · Leadership · Semi Confirmation 을 한 흐름으로 (2026-10-01)

세 영역의 계산과 데이터는 그대로이고 표시만 바꿨다(`config/ai_regime.yaml chain_view`, `engines/ai_chain_view.py`, 프런트
`AiChainSections.tsx`; AI 센티 기본 탭은 영향 없음). 읽는 순서: **AI CHAIN SNAPSHOT**(FUNDAMENTALS Selective Positive ·
PRICE LEADERSHIP Equipment / Packaging · SEMI CONFIRMATION Advanced Packaging STRONG · Equipment LEADING · KEY GAP HBM
fundamentals > HBM price + 한 줄) → **FUNDAMENTAL × PRICE ALIGNMENT**(밸류체인마다 전파 단계 상태·점수 | 가격 상태·순위 | VIEW;
VIEW 는 펀더멘털 상태 × 가격 상태 조합 규칙 — CONFIRMED · DIVERGENCE · FUNDAMENTAL-LED · PRICE-LED · MIXED · WEAK, 영어 + 한글
sublabel, 기본 6행 + View all 10, CONFIRMED 행이 맨 위) → **AI FUNDAMENTAL TRANSMISSION**(9단계를 한 줄씩: 라벨 · 점수 · 상태,
subtitle 한 줄, 점수 뜻은 ⓘ tooltip, FUNDAMENTAL READ 한 줄, 기존 카드형은 View evidence) → **AI VALUE-CHAIN LEADERSHIP**
(LEADERS / LAGGARDS 3+3, 행마다 1주 상대 %p · Breadth · 가격 상태, LEADERSHIP READ 한 줄, 1D/1W/1M/EPS 전체 표는 View all 10) →
**SEMICONDUCTOR CONFIRMATION**(영역 6행: 상태 + 실제 column(PRICE · REL STRENGTH · BREADTH · NEWS / FUND · EPS)으로 만든 의미
한 줄, Memory / HBM 은 Key evidence HBM3E · HBM4 계약가 앵커 변화, 화살표 matrix 와 계약가 세부는 View evidence matrix /
View HBM details). 가격 상태는 세그먼트 role·순위·breadth 에서, 펀더멘털 상태는 전파 단계(없는 세그먼트는 expectation_gap
fundamental 문턱)에서 읽는다. 긴 문장(전파 문장 · 리더십 문장 · 반도체 문장)은 기본 화면에서 빼고 한 줄 read 로 대신한다.
9/29: Equipment · Packaging CONFIRMED, Foundry · HBM DIVERGENCE, Software MIXED, Networking · DC Infra · Power · GPU ·
Hyperscalers WEAK. 테스트 +3(백엔드) +1(프런트).

#### AI 센티2 · AI VS MARKET → WHAT IS DRIVING AI? (OBSERVATION → ATTRIBUTION) (2026-09-30)

두 카드만 바꿨고 점수 계산은 그대로다(표시 층: `config/ai_regime.yaml vs_market · driver_view · driver_verdict`,
`engines/ai_driver_view.py`, 프런트 `AiDriverSections.tsx`; AI 센티 기본 탭은 예전 카드 그대로). **AI VS MARKET** 은
"AI 가 절대적으로 약한가 → 시장보다도 약한가 → 그 차이가 평소 범위를 벗어났는가" 를 바로 답한다: 상단 ABSOLUTE TREND
(RISING / WEAK / FLAT) · RELATIVE TREND(OUTPERFORMING / IN LINE / UNDERPERFORMING) · RELATIVE Z(σ · 5D, 평소 대비 의미) 세
타일(영어 상태 + 한글 한 줄), 오른쪽 compact 1D / 1W / 1M 표(AI Basket · Nasdaq 100 · S&P 500 · **AI vs Nasdaq** 강조 ·
AI vs S&P), 아래 MARKET READ(라벨 = regime 짧은 이름 + AI RELATIVE WEAKNESS/STRENGTH, 2문장: 시장 상황 + AI-specific
deterioration 확인 여부) · RELATIVE PERFORMANCE READ(≤2문장) · 연결 문구 WHAT EXPLAINS THE GAP?. **WHAT IS DRIVING AI?** 는
EVIDENCE SCORE 범례(−100 강한 AI 하방 압력 · 0 방향성 근거 없음 · +100 강한 AI 상방 지지, "확률·수익률 전망이 아니라 내부
evidence 로 표준화한 값") → **DRIVER VERDICT**(AI UNDERPERFORMANCE −1.5%p vs Nasdaq · 1W 를 어떤 driver 가 설명하는가:
PRIMARY / SECONDARY PRESSURE · OFFSETTING SUPPORT · NOT YET CONFIRMED + 한글 결론; 순위 = |score| × 확인 가중(CONFIRMED
1.0 · UNCONFIRMED 0.6 · CONTRADICTED 0.3) × 데이터 확보율이라 점수만 커도 UNCONFIRMED 가 primary 가 되지 않는다) →
CONFIRMED / UNCONFIRMED / CONTRADICTED / PARTIAL 뜻 → driver 카드(점수 · 질적 라벨 STRONG NEGATIVE … STRONG POSITIVE ·
driver 별 한 줄 의미 · 0 중앙 NEGATIVE|POSITIVE 막대 · MARKET CONDITION evidence ≤3 · WHY IT MATTERS 1문장 · PRICE CHECK ·
상태 + 뜻; AI Narrative 는 NARRATIVE > PRICE 보조 라벨, AI-specific Fundamental Stress 는 Hyperscalers · AI Narrative ·
Semi Fundamentals 행) — 누르면 TRANSMISSION(시장 → AI 4단계) · 상태 뜻 · 전체 evidence · implication. 9/29: WEAK ·
UNDERPERFORMING · −0.7σ · MACRO-DRAGGED + AI RELATIVE WEAKNESS; VERDICT PRIMARY Macro / Rates −76 CONFIRMED · SECONDARY
Broad Risk-Off −56 CONFIRMED · OFFSETTING AI Narrative +22 · NOT YET CONFIRMED AI-specific Fundamental Stress −22 →
"현재 AI 약세는 AI 산업 자체의 펀더멘털 훼손보다는 Macro / Rates 와 Broad Risk-Off 의 설명력이 더 큽니다." 테스트 +4(백엔드) +1(프런트).

#### AI 센티2 · 상태값 의미 줄 · AI REGIME READ · AI SENTIMENT 시각 재구성 (2026-09-30)

판단 로직·점수 계산은 그대로이고 표현만 바꿨다. **AI TRADE REGIME** 상태 띠의 각 카드는 ENGLISH CATEGORY / ENGLISH STATUS /
한 줄 한국어 의미로 통일했다 — 번역이 아니라 "지금 이 상태가 뜻하는 것"(`config/ai_regime.yaml status_meaning`, 예: PRICE WEAK
→ "실제 가격은 AI 기대를 충분히 확인하지 못함", BREADTH NARROWING → "상승에 참여하는 종목 수가 감소", SEMI PARTIAL 은 확인
영역 이름을 채운다). FUNDAMENTAL CONFIRMATION 장문 · SUMMARY · Global market regime 설명은 **AI REGIME READ**(2~3문장,
`regime_read` 템플릿: 펀더멘털 수준 + 가격·breadth 확인 + 리더 세그먼트 + 매크로) 하나로 합치고 그 아래 **KEY TENSION**
(sentiment 의 보조 상태 재사용) 한 줄을 둔다; 원문 장문은 Details / Data Quality 안으로 내렸다(삭제 아님). **AI SENTIMENT** 는
읽는 순서를 게이지 → 5 factor bar(FUNDAMENTALS · NARRATIVE · PRICE · BREADTH · MACRO, 가로 막대 + 점수 + 상태 + 한 줄
sublabel) → KEY TENSION + 한 문장(`gap_read`) → SENTIMENT DRIVERS(SUPPORT ↑ / PRESSURE ↓ 2열 + NET EFFECT 한 줄) →
1M SENTIMENT(밴드 배경을 연하게 깐 스파크라인, 현재 점 강조, NOW / 1W / 1M RANGE, 변화의 뜻 한 줄 `history.read`, 작은
FEAR ← 0 — 50 — 100 → GREED 눈금) → AI SENTIMENT READ(입력 단위 최대 2문장) 로 바꿨다. 숫자 나열(44 → 56 → …)과 5개 큰 legend
는 없앴다. 데스크톱은 게이지 40% : factor 60%, 아래 full width 3열; 모바일은 single column. 9/29: 상태 띠 NEUTRAL+ · SOFT ·
WEAK · PARTIAL(Advanced Packaging · Equipment) · WEAK · NEUTRAL · NARROWING · HEADWIND · PARTIAL; AI REGIME READ "AI 펀더멘털은
유지되고 있지만 가격 confirmation 과 시장 breadth 는 약합니다. Semiconductor Equipment · Advanced Packaging 은 상대적으로
견조하지만 금리·Credit Stress 가 AI 전반의 확산을 제한하고 있습니다."; NET EFFECT "가격 · 확산도 · 매크로 압력이 내러티브 ·
펀더멘털 지지보다 우세"; 1M "1주 전 EXTREME GREED 영역에서 현재 FEAR 로 빠르게 냉각".

#### AI 센티2 · AI SENTIMENT · GREED & FEAR (2026-09-30)

`AI 센티2` 탭의 AI TRADE REGIME 바로 아래, AI vs MARKET 위에 붙는 영역이다(AI 센티 기본 화면과 기존 AI 센티2 의 구조·판정
로직은 그대로). 일반 시장 Fear & Greed 가 아니라 **AI 투자 테마 내부의 투자심리와 실제 시장 확인 강도**를 0~100 하나로
잰 현재 상태 지표이고, 상승·매수 확률이나 수익률 전망이 아니다. `config/ai_regime.yaml sentiment` 가 전부를 정한다:
구성요소 5개(NARRATIVE 0.20 · PRICE 0.25 · BREADTH 0.20 · FUNDAMENTALS 0.15 · MACRO 0.20)와 각 입력(AI 뉴스 톤 · Capex /
GPU / Hyperscaler driver 톤 · 바스켓 z · Nasdaq 대비 상대 z · 1M 수익 · 5/20일선·상승 비율 · HBM / 범용 메모리 / EPS 전파 단계 ·
반도체 펀더멘털 확인 · 금리 / 실질금리 / 달러 / VIX / 신용 / S&P z × 기대 부호), 밴드(0–20 EXTREME FEAR · 20–40 FEAR ·
40–60 NEUTRAL · 60–80 GREED · 80–100 EXTREME GREED), 보조 상태 규칙, SUPPORT / PRESSURE 문턱, READ 템플릿, 1M 이력 창.
엔진 `engines/ai_sentiment.py` 는 새 판정을 만들지 않는다 — 이미 계산된 AiRegime 값을 clip(값/ref) 로 0~100 에 옮기고
(50 = 중립) 가중 평균한다. **결측은 0 이 아니라 분모에서 뺀다**(EPS 컨센서스 없음, 범용 메모리 계열 없음은 DATA MISSING 으로
남고 구성요소 확보율에 적힌다). 보조 상태는 긴장이 가장 큰 규칙 하나(FUNDAMENTALS > PRICE · NARRATIVE AHEAD OF PRICE ·
PRICE AHEAD OF NARRATIVE · FRAGILE · MACRO-CAPPED · MACRO-SUPPORTED, 없으면 BALANCED). SENTIMENT STRUCTURE 는 입력 단위로
SUPPORT(≥60) / PRESSURE(≤40) 각 ≤3. 1M 이력은 같은 공식을 바스켓·벤치마크 종가 · 시장 계열 · 기사 시각으로 하루씩 되돌려
만들고, 날짜별 계열이 없는 구성요소(메모리 데이터·EPS)와 창 안에서 충분히 잴 수 없는 구성요소(뉴스는 기사가 있는 날만)는
basis 에서 빼고 그렇게 적는다 — 1D/1W 변화도 그 basis 위의 값이며 화면에 † 로 표시한다. 프런트 `AiSentimentSection.tsx`:
SVG 반원 게이지(viewBox, 밴드 5, 눈금 0·20·40·60·80·100, FEAR / NEUTRAL / GREED 라벨, 바늘 각도 −90° + s/100 × 180°,
load 때 한 번만 움직임), 중앙 점수 · 상태 · 한글 · 1D/1W, 아래 보조 상태; 오른쪽(데스크톱 0.8fr : 1.2fr) 구성요소 분해
(점수 · 상태 · 한글 해석 · 입력 확보), 그 아래 AI SENTIMENT READ(2~3문장) · SENTIMENT STRUCTURE(SUPPORT / PRESSURE) ·
1M 스파크라인(Range); 900px 이하는 게이지 `min(100%, 360px)` 가운데 정렬 single column. 색은 탈색 청 → 청회 → 웜 그레이 →
앰버 → 적갈의 muted 팔레트(`--gf-*`)로 심리 상태만 구분하고 좋고 나쁨(적/청)을 뜻하지 않는다. 9/29: **40 NEUTRAL** —
NARRATIVE 62 GREED(Capex +18 · 뉴스 톤 +6) · PRICE 32 FEAR(바스켓 −1.2σ · 상대 −0.7σ) · BREADTH 36 FEAR(5일선 위 12%) ·
FUNDAMENTALS 66 GREED(HBM +39 · 반도체 확인 PARTIAL; 범용 메모리·EPS 결측) · MACRO 13 EXTREME FEAR(HY OAS +3.9σ ·
실질금리 +1.5σ) → 보조 상태 FUNDAMENTALS > PRICE; SUPPORT AI Capex · HBM · Semi Confirmation, PRESSURE Credit Stress ·
Real Yield · Breadth >5DMA; 1M 이력은 PRICE · BREADTH · MACRO 기준(Range 21–82). 테스트 +4(백엔드) +1(프런트).

#### 실시간 2 · MARKET LEADERSHIP → Full-width Leadership Detail Panel (2026-09-30)

레이아웃·상호작용만 바꾼 수정이다(판단 로직 · 엔진 · 데이터 계약은 그대로). 좁은 카드 column 안에서 상세를 펼치던 구조를
버리고 **목록(compact) 과 상세(full-width) 를 분리**했다. MARKET LEADERSHIP 카드는 LEADERS / LAGGARDS 목록만 보이고,
테마를 누르면 그리드의 `leaddet` 행(`grid-column: 1 / -1`, 부모 그리드 전체 폭)에 `{테마} · LEADERSHIP DETAIL` 패널이 열린다.
한 번에 한 테마만 열리고(다른 테마를 누르면 교체, 다시 누르거나 닫기로 닫힘), 열린 행에는 작은 ACTIVE 표시가 붙는다.
패널 맨 위는 Summary(LEADERSHIP QUALITY · PRIMARY DRIVER · KEY RISK · SYSTEM READ)이고 그 아래가 상세다: 왼쪽 WHY LEADING →
SYSTEM VIEW(INTERNAL: DRIVER / QUALITY / RISK) → MARKET CONFIRMATION(Metric | Value | Status 세 칸, 좁으면 세로 스택),
오른쪽 STREET VIEW(EXTERNAL: 기관 · 애널리스트 · 날짜 · 한글 요약 · 핵심 변수 · View source; 긴 영어 원문은 2줄까지 접힘, 눌러야
펼침) → KEY STOCKS(표가 아니라 종목마다 이름 · σ · 역할 · 상태 줄을 가진 독립 row) → WHAT TO WATCH(별도 block). 2열은
viewport 1280px 이상이면서 패널 자체 폭이 충분할 때만(`@container ldp`), 그 아래(iPad landscape 1024~1200px 포함)는 한 열,
768px 이하는 완전한 single column. 그리드 자식은 `min-width: 0`, 열은 `repeat(2, minmax(0, 1fr))`, 긴 문장·URL 은
`overflow-wrap: anywhere` 로 page-level 가로 스크롤을 만들지 않는다. Playwright 로 1440 / 1366 / 1280 / 1180 / 1024 / 768 /
390px 에서 가로 스크롤 없음 · 패널이 부모 그리드 밖으로 나가지 않음 · 섹션/행 겹침 없음 · 열고 닫은 뒤 layout shift 없음을 확인.

#### 실시간 2 · MARKET → STOCK TRANSMISSION read 와 WATCHLIST 체크포인트 (2026-09-30)

**MARKET → STOCK TRANSMISSION**: DRIVER → INDUSTRY / THEME → STOCK 과 종목별 CONFIRMED / UNCONFIRMED / CONTRADICTED
판정은 그대로다. 체인마다 `n / m confirmed`(NO DATA 제외) 옆에 TRANSMISSION STRENGTH — STRONG(전파 강함) · PARTIAL(일부
전파) · LIMITED(전파 제한적) · UNCONFIRMED(아직 미확인) — 를 붙인다. 비율만이 아니라 driver 강도를 함께 본다
(`config/cockpit.yaml transmission.strength`). 그 아래 **TRANSMISSION READ** 1~2문장: 어느 산업까지 실제 가격에서
확인됐는지, 어디로의 확산은 추가 확인이 필요한지, 어떤 종목이 예상과 다르게 움직이는지(원인을 단정하지 않고
"종목·테마 고유 driver 가능성을 점검할 필요") 를 지금 데이터로만 만든다. 주어는 `transmission.subject_ko`(driver ×
방향), 산업 이름은 `industry_labels`.

**WATCHLIST**: '관심종목 5개' 가 아니라 '오늘 다시 확인해야 할 종목과 기다리는 trigger' 다. 제목 아래 목적 설명과
Stock Radar 와의 역할 차이("왜 오늘 움직였는가" vs "다음에 무엇이 나타나면 다시 봐야 하는가"). 종목마다 이름 / 수익률
→ Theme / Industry → **WHY WATCH**(1~2줄, 지금 데이터: 펀더멘털·테마 leadership 상태 + 가격 confirmation + 매크로 노출
/ 뉴스 / 대체데이터) → **KEY DRIVER**(≤3) → **TRIGGER**(무엇이 나타나면 다시 판단하는가; 시스템 임계가 없으므로 숫자
없음) → WATCH REASON 태그(NEWS · THEME · MACRO · FUNDAMENTAL · DIVERGENCE · ALT DATA · TRANSMISSION ≤3) → **TRANSMISSION
●**(누르면 해당 전파 카드로) · **RELATED ISSUE**(누르면 WHAT MATTERS NEXT 항목이 열림). 누르면 해설 발췌 · EPS revision ·
ANALYST VIEW 가 펼쳐진다. 선정은 수익률 순이 아니라 뉴스 · 상대강도 · 매크로 노출 · 테마 leadership · 전파 관련성 ·
이슈 관련성 · 대체데이터의 합(`watchlist.weights`)이고, 점수는 보이지 않고 HIGH 만 표식한다. driver 라벨과 종목별
driver/trigger 힌트는 `watchlist.driver_labels` / `watchlist.hints`, 없으면 종목 메타의 driver 로 만든다.

### 유가 탭 — 시장 원인 판별 (2026-09-29)

유가 탭은 룰 판정("Geopolitical Risk 아님")을 앞세우지 않는다. `engines/oil_regime.py`
가 `config/oil_regime.yaml` 의 증거표로 거시·유동성 / 수요 / 공급 / 지정학 프리미엄
네 driver 의 점수(−100~+100, 부호 = 유가에 주는 방향)를 내고, 유가 관측(브렌트·WTI)에
비춰 CONFIRMED / UNCONFIRMED / CONTRADICTED 를 붙인다. 두 유가가 갈리면 확인을
보류한다. 화면은 REGIME → DRIVER → MARKET CONFIRMATION → NARRATIVE vs PRICE →
WHAT TO WATCH NEXT(판단이 바뀌는 조건 3~5개) → Diagnostics(룰 판정·서명 대조,
접이식) 순이다. 엔드포인트 `GET /api/v1/oil-regime`. 판정 룰 엔진은 그대로 돈다.

### AI 탭 — AI Trade Intelligence (2026-09-29)

AI 탭은 시장 온도(공포·탐욕)를 보여주지 않는다. 위험선호·변동성·신용 같은 broad-market
값으로는 'AI 트레이드 자체가 약해지는가, 시장 risk-off 에 같이 눌리는가' 를 구분할 수 없기
때문이다. `engines/ai_regime.py` 가 `config/ai_regime.yaml` 의 바스켓(6개 그룹 32종목 —
Semiconductors/Compute · Memory · Hyperscalers · Networking/Infrastructure · Power/Data Center ·
Software/Application, 여기에 비교용 국내 AI 밸류체인 8종목)을 Yahoo 에서 받아 Nasdaq 100 달력
위의 동일가중 지수를 만들고, **Nasdaq 100 / S&P 500 대비 상대 수익과 상대 z** 를 판정의 축으로
쓴다. AI 절대 가격이 빠져도 Nasdaq 보다 약하지 않으면 AI-specific selloff 로 부르지 않는다.

화면은 AI TRADE REGIME(Confirmed AI Risk-On · Macro-Dragged AI Weakness · Leadership Narrowing ·
Narrative Ahead of Price · AI-Specific De-risking · Confirmed AI Risk-Off · Price Resilience ·
Mixed) → AI vs MARKET(1D/1W/1M 절대·상대·상대 z) → WHAT IS DRIVING AI?(Macro/Rates · Broad
Risk-Off · Semiconductor Cycle · AI Narrative · AI-specific Fundamental Stress 의 증거 점수) →
AI LEADERSHIP(그룹별 1D/1W/1M 상대 모멘텀·순위·회전 자동 판정) → AI BREADTH(5DMA/20DMA 상회,
상승 비율, 1주 변화 — 지수가 올라도 breadth 가 빠지면 Leadership Narrowing) → NARRATIVE × PRICE
(2×2: Confirmed / Narrative Ahead·Distribution Risk / Price Resilience / Confirmed Risk-Off, AI 기사를
Capex·GPU Demand·Hyperscaler Spending·Monetization·Competition·Regulation·Valuation driver 로
룰 분류) → MACRO CONFIRMATION(금리·실질금리·달러·VIX·HY OAS·S&P 가 AI 방향을 설명하는지 —
Macro-driven vs AI-specific weakness) → AI-SPECIFIC STRESS(LOW/MODERATE/HIGH) → WHAT CHANGES THE
VIEW(AI-specific Risk-Off 전환 조건 5개 + 해제 조건) → Diagnostics(판정 규칙 검사, Global market
regime 맥락, 구성원 표, 서명 대조, 접이식) 순이다. 엔드포인트 `GET /api/v1/ai-regime`. 판정
규칙 순서는 ai_specific_derisking → narrative_ahead → macro_dragged → leadership_narrowing →
confirmed_risk_on → confirmed_risk_off → price_resilience → mixed 이고 임계는 전부 설정에 있다.
확률 표현은 쓰지 않는다. 시장 판정·온도계는 맥락 한 줄로만 붙는다.

#### AI 센티2 탭 — Fundamental Confirmation Layer · 밸류체인 · 종목 영향도 (2026-09-29)

`AI 센티` 탭은 위 AI Trade Intelligence 화면 그대로이고, `AI 센티2` 탭(`scenario_checks.yaml` 의
`ai_sentiment2`, 기준 시나리오 `ai_sentiment`, focus `ai_regime_full`)이 같은 응답 위에 아래 블록을 더 편
확장 화면이다. 기존 AI TRADE REGIME 구조는 그대로 두고, 반도체·메모리·HBM 데이터를 **업사이클 판정이 아니라 AI 투자
사이클을 검증하는 확인 데이터**로 흡수했다(업사이클 %, 신호 n/4, 서명 일치도, require/support 는 쓰지
않는다). `engines/ai_value_chain.py` 가 같은 입력 위에 다음을 더한다 — REGIME 카드의 상태 띠(Narrative ·
AI Relative Strength · Price · Semiconductor Confirm. · AI Infra · Software · Breadth · Macro · Fundamental
Confirmation)와 부제(`… / FUNDAMENTALS RESILIENT`)·SUMMARY → AI FUNDAMENTAL TRANSMISSION(AI Narrative →
Hyperscaler Capex → GPU → HBM → Commodity Memory → Foundry/Packaging → Equipment → DC Infra → EPS, 단계마다
ACCELERATING/POSITIVE/STRONG/IMPROVING/STABLE/MIXED/DETERIORATING/UNCONFIRMED) → AI/SEMI/INFRA/SOFTWARE
LEADERSHIP(밸류체인 10 세그먼트의 1D/1W/1M·Nasdaq 대비·breadth·EPS, CURRENT LEADERSHIP / LAGGING) →
SEMICONDUCTOR FUNDAMENTAL CONFIRMATION(Compute/Accelerator · Memory/HBM · Commodity Memory · Foundry ·
Advanced Packaging · Equipment 의 가격·상대·breadth·뉴스·EPS 화살표와 status, MEMORY/HBM FUNDAMENTALS 표 —
현재·1W·1M·z·신선도, 이력이 없으면 N/A, HBM 계약가는 구조적 증거) → AI STOCK IMPACT MAP(52종목 universe,
THEME/FUNDAMENTAL/MARKET/MACRO 네 축 화살표 + overall + 해석 문장, 단일 점수·추천 없음) → STOCK RADAR
(Strongest confirmation · Improving · Narrative > Fundamentals · Fundamentals > Price · Macro pressure, 이유
포함) → NEWS → VALUE CHAIN → STOCK(기사 → driver → 1차/2차/인프라 세그먼트 → 종목, NEWS POSITIVE / MARKET
UNCONFIRMED 식 확인 라벨) → EXPECTATIONS vs FUNDAMENTALS(세그먼트별 Market Pricing vs Fundamental 0~100, gap)
→ WHAT MATTERS NOW(최대 5, CONFIRMING/WATCH/DETERIORATING) → DETAILS / DATA QUALITY. 종목·세그먼트·민감도·
키워드·임계는 전부 `config/ai_regime.yaml`. EPS revision 은 컨센서스 CSV 가 없어 N/A 로 남는다.

### 물가 탭 — Inflation & Rates Intelligence (2026-09-29)

물가 탭은 룰 판정("Inflation Shock 아님")을 앞세우지 않는다. `engines/rates_regime.py`
가 `config/rates_regime.yaml` 의 증거표로 물가 리프라이싱 / 연준 정책 경로 / 성장 /
기간 프리미엄·공급 / 위험·유동성 다섯 driver 의 점수(−100~+100, 부호 = 장기 명목금리에
주는 방향)를 내고, 10년 금리 관측에 비춰 CONFIRMED / UNCONFIRMED / CONTRADICTED 를
붙인다. 지배 driver 는 금리 방향과 맞는 것 중 |점수| 최대다 — 금리와 반대로 가는
driver 는 아무리 커도 '금리를 움직인 원인' 이 될 수 없다. 레짐 라벨은
`<지배 driver 헤드라인> — Inflation Repricing Confirmed / Not Confirmed / Contradicted`
(예: `LONG-END RATE / TERM PREMIUM SHOCK — Inflation Repricing Not Confirmed`).
화면은 REGIME → WHAT IS DRIVING RATES? → INFLATION PRESSURE(실현 물가·시장 기대·
에너지·임금/서비스·환율 전가, 계열 없는 것은 0 이 아니라 결측) → TREASURY CURVE
(2Y/5Y/10Y/30Y, 스티프닝/플래트닝과 주도 구간 자동 판별) → NOMINAL YIELD DECOMPOSITION
(명목 − 기대인플레 = 실질, TIPS 실측 대조) → MARKET CONFIRMATION(CONFIRMED / MIXED /
NOT CONFIRMED / MISSING) → KEY DIVERGENCE(설정의 괴리 짝 자동 탐지 + 한 문장) →
MARKET IMPLICATION(전이 방향, 추천 아님) → WHAT CHANGES THE VIEW(3~5 조건 + 지배
driver 해제 조건) → Diagnostics(룰 판정·팩터 원점수·서명 대조, 접이식) 순이다.
엔드포인트 `GET /api/v1/rates-regime`. 확률 표현은 쓰지 않는다 — 증거 크기다.
계열은 US5Y·BE5Y·TIPS10Y·TIPS5Y(FRED DGS5·T5YIE·DFII10·DFII5)를 더했고 금리 이름은
"US 10Y Yield" 처럼 명확하게 바꿨다. 실현 물가(CPI·PCE)와 임금·서비스 계열은 아직 없다.

### 메모리 가격 — DRAM·NAND 현물과 HBM 계약가 추정 (2026-09-29)

`python -m marketpulse.scripts.collect_memory_prices` 가 두 공개 출처를 읽어
`data/replay/alternative/*.csv` 에 쓴다. DRAMeXchange 홈페이지의 DRAM·NAND 현물
세션 평균과 DXI 는 공개 이력이 없어 **하루 한 줄씩 쌓고**, HBM3E·HBM4 계약가는
Silicon Analysts 무료 API 의 앵커(분기·비정기, 출처·신뢰도 포함)를 그대로 적는다.
HBM 은 현물 시장이 없으므로 추정치이며 화면에 '분기 추정' 표식이 붙고 z·방향
계산에서 빠진다. 현물 네 항목은 `min_points: 1` 로 값·변화부터 보이고 z 는
20봉이 차면 나온다("봉 n/20" 표식). 키·비밀 없음. 클라우드 환경에서 돌리려면
`dramexchange.com`(www 없이)과 `siliconanalysts.com` 이 허용 목록에 있어야 한다.

### 시나리오 점검 — 모의 탭을 실데이터로 (2026-09-29)

화면의 물가 충격·유가 급등·AI 센티2·평시 탭(2026-10-07 까지는 AI 센티·메모리 업사이클도)은
더는 모의 데이터를 보여주지 않는다. 헤더의 **시나리오 점검 탭**을 누르면 같은 실데이터 위에 패널이
하나 붙고, 그 시나리오의 **충격 서명**(`data/mock/scenario_*.json` 의 `shocks`,
마지막 봉 목표 z)을 지금 실데이터의 하루·5일 z 에 대어 본다. 일치도는
|기대 z| 를 가중치로 한 비율의 평균(0~100)이고 결측은 분모에서 뺀다. 그 시나리오가
가정하는 판정 라벨의 require 룰이 실제로 걸렸는지, 가설 점수, 관련 테마의
가격/뉴스 점수를 같이 적는다. 규칙은 전부 `config/scenario_checks.yaml` 에 있다.
예측이 아니라 "지금 시장이 그 그림과 얼마나 닮았나" 이며, 판정은 여전히
`state_rules.yaml` 이 정한다. 엔드포인트 `GET /api/v1/scenario-check`. 모의 데이터
자체는 MOCK 모드와 테스트의 골든 케이스로 그대로 남아 있다.

### 데이터 신선도는 거래일로 센다 (2026-09-29)

헤더 배지의 "N일 전" 은 가장 오래된 재료의 나이다. 금요일 봉을 월요일 아침에
보면 초로는 3일이라 화면 전체가 오래된 것처럼 보였다. 이제 `DataHealth` 에
`max_freshness_trading_days`(주말 제외 평일 수) · `oldest_instruments` ·
`freshness_note` 가 붙고, 배지는 하루 이상이면 "2거래일 전", 같은 거래일
안이면 시간·분으로 쓴다. 툴팁에 초 기준 나이와 해당 계열이 그대로 남는다.
각 시장의 휴장일은 알 수 없어 반영하지 않으므로 이 값은 **상한**이다 — note 에
그렇게 적혀 있다.

### 실시간 2 · MARKET TONE SNAPSHOT (2026-10-07)

MARKET REGIME HISTORY · 1M 과 TODAY'S MARKET DRIVERS 사이에 붙은 카드. HISTORY 가 "한 달 동안 regime 이 어떻게 변했는가" 라면 이 카드는
"현재 시장이 왜 이 regime 에 있는지, 가격·뉴스·주요 risk factor 가 어떤 방향인지" 다 — HISTORY → CURRENT CONDITION → TODAY'S DRIVERS.
내용은 **실시간 탭의 시장 온도 화면(`SentimentGauge`) 그대로**다: 같은 컴포넌트에 같은 `snapshot.thermometer` 를 넣으므로 점수·밴드·눈금(가격·뉴스
마커, 결빙~과열)·"△ 가격 / ▽ 뉴스 / 1주 전"·재료 스트립(1주 전 ◇ · 현재 ●)·템플릿 문장이 두 탭에서 같다. 전체 폭 카드에서 SVG 가 거대해지지
않게 폭만 실시간 탭 패널 수준(560px)으로 제한했다. 백엔드는 같은 온도계를 regime 과 대조한 `Cockpit.tone`(`engines/market_tone.py`,
`config/cockpit.yaml tone`: 상태 taxonomy · 재료별 의미 · 1W 변화 읽기 · PRICE vs NEWS · REGIME CONFIRMATION · 2문장 READ)도 API 로 준다 —
화면은 온도계 그대로를 쓰고 이 값은 API 소비자용이다. 실시간 탭의 온도계 UI·계산은 그대로다.

### 실시간 2 · CURRENT REGIME 단일 출처 — OFFICIAL vs RAW (2026-10-07)

MARKET REGIME HISTORY 의 CURRENT 와 MARKET NOW 의 판정이 서로 달랐던 문제(History: Risk-On · Now: NO REGIME)를 고쳤다.
이제 **공식(confirmed) regime 하나**만 현재 판정이고, 두 카드와 drivers · cross-asset · tone · what-matters 의 regime 참조가 모두
그 값을 쓴다. 공식 regime 은 `engines/regime_history.py` `stabilize()` 가 **인과적(causal)** 으로 만든다: 날짜 D 의 공식 regime 은 D 까지의
raw 만 보고(미래를 보지 않으므로 과거 값은 뒤에 날이 붙어도 바뀌지 않는다), 새 regime 으로 바뀌는 조건은 `config/cockpit.yaml`
`history.display` 의 두 가지 — 오늘까지 연속 `min_dwell_days`(2) 거래일 같은 raw, 또는 오늘 확신 ≥ `strong_evidence`(80). 그 외의 날은
직전 공식 regime 이 이어진다. 오늘 룰이 가리키는 판정(`market_state.primary_label`)은 **RAW SIGNAL** 로 따로 보인다 — MARKET NOW 의
RAW SIGNAL 상자(raw 판정 · RAW PERSISTENCE nD · STATUS)와 HISTORY 컨텍스트의 Raw signal 줄. STATUS 는 `history.transition` 템플릿의
CONFIRMED(raw = 공식) · UNCONFIRMED TRANSITION(raw ≠ 공식, 아직 1D 미만의 확인) · TRANSITION WATCH(한 거래일만 더 이어지면 전환) · CHANGED(오늘
공식 전환) · NO HISTORY(저장된 sequence 없음 → raw 를 그대로 공식으로). **NO REGIME 은 더 이상 "오늘 아무 룰도 안 걸렸다 = 현재 판정" 이 아니라**
raw 후보일 뿐이고, 2거래일 이어져 확정될 때까지 직전 공식 regime 이 유지된다. "Change" 줄은 공식 전환이 일어난 날(`changed_today`)에만 쓰고
그 외에는 "Transition watch / Potential change RISK-ON → NO REGIME" 으로 쓴다. 이름도 갈랐다: **REGIME DURATION** = 공식 regime 이 이어진
거래일(`duration_days`), **RAW SIGNAL PERSISTENCE** = 오늘까지 같은 raw 가 이어진 거래일(`raw_run()`). Conviction 은 regime 이 아니라 그 안의
증거 강도라 "41% · MEDIUM · WEAKENING"(직전 거래일 대비 `conviction_trend.delta`=10 이상 하락) 처럼 공식 Risk-On 과 같이 보일 수 있다.
MARKET READ 문장은 `now_read` 템플릿(확률·전망 어휘 없음)으로 "RISK-ON은 유지되고 있지만 raw signal 이 NO REGIME 쪽으로 1거래일째 이어지고
있습니다. 다음 거래일에도 같으면 공식 regime 이 전환됩니다." 처럼 쓴다. History 띠의 오늘 셀은 LIVE 로 공식 regime 을 따라가고(raw 는 툴팁·상세),
장중에는 RECORDED/LOCK 하지 않는다 — Daily Finalization(16:10 KST) 뒤에만 고정된다. 과거 날짜는 저장된 snapshot 그대로다. API: `market_now.raw_label
· raw_text · raw_persistence_days · transition_status(_ko) · potential_change_text · required_days · conviction_trend · read`,
`history.official_state_label · raw_regime · raw_label · raw_persistence_days · required_days · transition_status(_ko) · pending_regime · changed_today`.
회귀 테스트(`tests/test_cockpit.py TestCanonicalRegime`): 직전 확정 Risk-On · 오늘 raw Neutral 1D → HISTORY CURRENT = MARKET NOW = Risk-On,
raw 는 보조, 다음 날도 Neutral 이면 CHANGED; 저장 sequence 없음 → NO_HISTORY; 장중 오늘 = LIVE·unlocked.

### 신뢰도 기반 macro fallback data layer (2026-10-13)

INFLATION PRESSURE MAP 에서 DATA MISSING 이던 실제 물가 · 임금·서비스를, 빈 칸을 억지로 추정하지 않고 급(tier)이 붙은 경로로 보완한다.
`adapters/macro_fred.py`(수집) → `engines/macro_fallback.py`(급 판정 · 점수) → `models/macro_data.py`(정규화 스키마), 설정 `config/macro_sources.yaml`.

| 급 | 경로 | 기본 신뢰도 |
|---|---|---|
| PRIMARY | FRED API(`FRED_API_KEY`) — 원 발표기관(BLS · BEA)을 그대로 표기, 발표일은 FRED vintage 일자 | 0.95 |
| MIRROR | FRED 그래프 CSV(키 불필요) — 같은 원자료, 경로만 다름 | 0.85 |
| SECONDARY VERIFIED | `data/policy_events/*.json` 의 보도 확인 공식 발표값(CNBC 등 출처 표기, 발표일 ≤ as_of 의 actual 만) | 0.70 |
| PROXY | 원 series 가 없을 때 경제적으로 비슷한 지표 조합 — 늘 PROXY 배지 + "실제 원데이터 미연결 · 대체 지표로 추정" + 대체 구성 | 0.45 |
| NEWS | 테마 뉴스 톤 — 수치를 대체하지 않는 INFLATION NEWS PULSE, 신호 점수에 넣지 않음 | 0.20 |
| DATA UNAVAILABLE | 어느 경로도 없음 — 숫자를 만들지 않는다 | 0 |

- **series**: CPI · Core CPI(BLS) · PCE · Core PCE(BEA) · AHE · ECI(분기) · Services CPI(서비스, 에너지 제외) · Core Services PCE(에너지·주거 제외 서비스) · PPI Final Demand · Import Prices.
  각 값은 `series · value · previous · consensus · period · release_date · source · source_tier · is_original_data · proxy_components · fallback_reason ·
  last_updated · freshness_days · frequency · stale · confidence` 를 들고 다닌다(캡처 `macro_data.json`).
- **점수**: 수준이 아니라 모멘텀 — (최근 3개월 연율 − 12개월 상승률)을 과거 5년 같은 값의 표준편차로 나눈 z, ±2σ 에서 ±100. 화면에 YoY 와 3M 연율을 함께 보인다
  (CPI 3.35% YoY 인데 3M 연율 0.2% → 둔화 쪽 힘). YoY 는 FRED 계절조정 지수로 계산해 공식 발표(비계절조정)와 0.1%p 안팎 다를 수 있어 둘째 자리까지 보인다.
- **실제 물가**: CPI · Core CPI · PCE · Core PCE 가 하나라도 있으면 원자료 구성요소(점수는 STALE 이 아닌 것만). 하나도 없을 때만 PPI · 수입물가로
  **REALIZED INFLATION PROXY**(이름부터 바뀜, "실제 CPI/PCE 데이터 미연결 · 대체 지표 기반 추정"). 원자료가 있으면 PPI · 수입물가는 참고값으로만 남고 점수에 넣지 않는다.
- **임금·서비스**: 단일 원데이터가 없어 AHE · ECI · Services CPI · Core Services PCE 를 각각 표준화한 합성 점수 — 구성 series 가 공식 원자료여도 **늘 PROXY**.
  상태는 ACCELERATING · STICKY · STABLE · EASING · COOLING, 실제 물가 점수와 비교한 한 줄("임금·서비스 인플레이션 둔화 속도가 전체 물가보다 느림").
- **STALE**: 예상 갱신 주기(월 31일 · 분기 92일 · 회의 49일) × 1.5 를 넘으면 STALE — 보여주되 점수·신호에서 빼고 신뢰도를 절반으로.
- **확인 정도**: 개수와 품질을 나눈다 — `Official data 4/5 · Proxy 1 · News 1`. FULL 은 모든 구성요소가 공식/시장 원자료이고 STALE 이 아닐 때만,
  강한 신호 라벨(COOLING · REACCELERATING)은 FULL 이고 실제 물가가 원자료일 때만. 신호는 신뢰도 가중 평균(NEWS · STALE · 결측 제외).
- **LLM 해석**: 구성요소의 출처 급 · 원자료 여부 · STALE 을 함께 넘기고, 공식과 PROXY 가 같은 방향일 때만 확신을 싣게 한다(PROXY 만 강하면 "공식 확인은 부족",
  뉴스만 한쪽이면 "서사는 늘었지만 공식 확인은 부족"). PROXY 를 확정 사실처럼 쓰지 않는다.
- **API**: `MacroLayerService` 가 하루 한 번 받는다(실패는 30분 기억). MOCK 시나리오에는 실데이터 macro 를 붙이지 않는다. 이 환경에서는 FRED 그래프 CSV 가 egress 정책으로
  막혀 MIRROR 경로는 시도만 하고 넘어간다.

### 금리 탭 아래 세 패널 — INFLATION PRESSURE MAP → TREASURY CURVE → YIELD MOVE BREAKDOWN (2026-10-13)

데이터를 더하지 않고, 기존 계산값(물가 구성요소 점수 · 테너 수준과 변화 · 명목 분해)을 "물가 압력 → 금리곡선 → 금리 변화 원인" 순서로,
각 칸은 **상태 → 방향 → 원인 → 의미** 순으로 다시 읽는다(`engines/rates_panels.py` + `config/rates_panels.yaml`, 화면 `RatesLowerPanels.tsx`).
데스크톱은 세 패널이 한 줄, 좁은 화면은 위에서 아래로 이어지고, 각 패널 맨 아래 한 줄이 다음 패널로 잇는다. 그 밖의 금리 탭 섹션은 내용 그대로다
(Key Divergence 는 빈 칸이 생기지 않게 Market Confirmation 옆으로 자리만 옮겼다).

- **INFLATION PRESSURE MAP**(옛 Inflation Pressure): 맨 위에 INFLATION SIGNAL(COOLING BIAS · MIXED · UPSIDE BIAS, 다섯 칸이 다 있고 실제 물가가 있을 때만
  COOLING · REACCELERATING)과 CONFIRMATION(FULL · PARTIAL · INSUFFICIENT, 구성요소 n/5) + 한 줄. 구성요소는 영어명 + 한글 설명(실제 물가 · 시장 기대인플레이션 ·
  에너지·원자재 · 임금·서비스 · 환율 전가), 그리고 STATE(COOLING · EASING · MILD PRESSURE …) → SCORE → EVIDENCE(10Y BE −1.2σ · 5Y BE −1.1σ). 점수 눈금
  (−100 강한 물가 하락 압력 · 0 중립 · +100 강한 물가 상승 압력)을 칸 위에 적었다. 결측은 DATA MISSING + "CPI / PCE 실제 물가 데이터 미연결" — 0 으로 세지 않는다.
  하단 READ(최대 2문장, 숫자 없음)는 LLM 이 구성요소를 보고 쓴다(`ai/inflation_read.py`, MARKET READ 와 같은 호출 · 검증 · 폴백에 '숫자 없음' 추가).
- **TREASURY CURVE**: 오늘과 5D 전 수익률 곡선(2Y · 5Y · 10Y · 30Y)을 작게 그리고, **CURVE MOVE(5D bp)** 와 **MOVE INTENSITY(5D σ)** 를 칸으로 나눴다 —
  모양은 실제 2s10s(보조 5s30s) bp 변화로, 이례성은 같은 창의 z 로. 판정: 금리 하락 + 스프레드 확대 = Bull Steepening, 하락 + 축소 = Bull Flattening,
  상승 + 확대 = Bear Steepening, 상승 + 축소 = Bear Flattening(|Δ| < 1bp 는 평행, < 3bp 는 MILD). 같은 날의 1D 모양도 한 줄로 보인다 —
  상단 REGIME · Current Rates Analysis 의 "Bull Flattening" 은 하루(10/8: 2Y −2 · 10Y −6 · 30Y −7bp) 기준이라 5D(2Y −3 · 10Y −2 · 30Y −1bp, 2s10s +1bp)와 다르다.
  예전 패널이 5D bp 막대 옆에 하루 z 로 정한 모양을 붙여 둘이 섞여 보였던 것이다(계산 오류가 아니라 창이 달랐다).
- **YIELD MOVE BREAKDOWN**(옛 Nominal Yield Decomposition): "명목금리 변화 = 실질금리 변화 + 기대인플레이션 변화", 5Y · 10Y 기본(나머지는 View all).
  만기마다 Real Yield(MODEL = 명목 − 기대인플레) + Inflation Expectation = Nominal, **PRIMARY DRIVER**(한쪽이 1.5배 이상이면 그쪽, 아니면 둘 다)와
  한 줄("금리 하락은 기대인플레이션이 아니라 실질금리 하락이 주도."), OBSERVED TIPS 를 따로 — 모델과 2bp 이상 다르거나 방향이 반대면 MODEL / MARKET DIVERGENCE.
  READ 는 성격 한 문장(Discount-rate easing · Disinflation repricing · Growth / Risk-off 가능성 · 할인율 상승 · Inflation repricing · 혼재), 움직임이 3bp 미만이면 약한 신호라고 붙인다.
- **분해 날짜 맞춤(버그 수정)**: FRED 기대인플레(T10YIE · T5YIE)가 명목·TIPS 보다 하루 먼저 나오는 날, 각자의 마지막 5봉 변화를 빼서 서로 다른 구간을 섞고 있었다
  (10/13 화면의 "실질 +1bp vs TIPS 실측 −1bp"). 이제 `build_rates_regime(series=…)` 가 세 계열이 모두 값을 가진 공통 날짜로 5일 변화를 잰다 —
  10Y 명목 −2 = 실질 −1 + 기대인플레 −1(TIPS −1 과 일치), 5Y −2 = −3 + +1. 계열을 못 받으면 예전처럼 재되 `aligned=false` 로 표시하고 대조하지 않는다.

### 금리 탭 MARKET READ — LLM Macro + Rates Investment Interpretation (2026-10-13)

금리 탭 맨 위 MARKET READ 를 "지배 driver 를 문장으로 다시 읽는 템플릿" 에서 PM/매크로 전략가 관점의 짧은 투자 해석(한국어 2~4문장)으로 바꿨다.
판정·점수·숫자는 정량 엔진 그대로이고, LLM 은 그것을 바꾸지 않고 "이 금리 움직임의 성격이 무엇이고 위험자산에 어떤 환경인가" 만 쓴다.

- **컨텍스트**(`ai/rates_read.py::build_context`, 설정 `config/rates_read.yaml`): 미국채 2Y·5Y·10Y·30Y 수준과 1D·5D·20D 변화(bp)·z, 2s10s·5s30s,
  TIPS 실질금리, BE 기대인플레, 기간 프리미엄 proxy(엔진 driver 점수 — 직접 추정치가 아니라고 적어 넘긴다), 5일 분해, regime 판정·driver·확인/괴리,
  출처 확인된 매크로 발표(실제치만)·발표일 금리 반응·중앙은행 결정과 톤·예정 이벤트, cross-asset(S&P · Nasdaq 100 · SOXX · XLF · 경기민감/방어 · Russell ·
  DXY · USD/KRW · USD/JPY · 금 · 브렌트 · WTI · 구리 · VIX · MOVE · HY OAS, 성장 대 시장은 NDX − SPX 로 대신), 금리·매크로 관련 헤드라인(48시간, 금리·물가·정책
  테마 우선). 계열마다 OK · STALE · MISSING 과 마지막 관측일을 붙이고, 미국채와 미국 주식의 마지막 관측일이 다르면 "같은 날 반응으로 묶지 않는다" 를 적는다.
  화면 상단에 이미 보이는 숫자(10Y 수준 · 5D · driver 점수 · 격차)는 `displayed_elsewhere` 로 넘겨 반복하지 않게 한다.
- **프롬프트**: 내부 판단 순서(금리 움직임 → 이유 → 시장 반응(DATA → MARKET REACTION) → 움직임의 성격 → 위험자산 환경 → 필요할 때만 다음 확인 지점)는
  화면에 쓰지 않는다. 주제는 기간 프리미엄 · Fed · 물가 · 성장 · 재정/공급 · 유동성 · 위험회피 · 유가 · 달러/환율 · 크레딧 중 1~3개만. regime 판정을 반복하지 말고
  cross-asset 과 대조, 정책은 관련 있을 때만, 인과는 단정하지 않고("~에 더 부합한다"), 직접 추천·확률·전망 표현과 상투 문구는 금지, 결측·지연 데이터는 상상하지 않는다.
- **호출**(`LLMClient.interpret`): 구조화 출력(read · move_quality · themes · regime_fit · data_caveat) + 적응형 사고, effort high. 안전 분류기가 거절하면
  서버가 권장 대체 모델로 같은 요청을 다시 돌린다(`fallbacks: "default"`); 그래도 거절이면 규칙 기반으로 돌아간다. 키는 환경변수로만, 모델은
  `MARKETPULSE_RATES_READ_MODEL`(없으면 `MARKETPULSE_LLM_MODEL`)로 바꾼다.
- **검증**(`validate_read` · `check_output`): 문장 2~4개 · 460자 이내 · 숫자 3개 이내(날짜·만기 이름·지수 이름 제외) · 모든 숫자가 컨텍스트 값과 일치(반올림 허용) ·
  화면 숫자 반복 금지 · 금지어(매수 · 매도 · 비중 확대/축소 · 확률 · 전망 …) · 상투 문구("주된 원인은" · "아직 확인되지 않았습니다" · "모니터링해야" …) ·
  인과 단정("때문입니다" …). 걸리면 문제를 알려주고 한 번 더, 그래도 안 되면 규칙 기반 문장.
- **폴백**: LLM 이 꺼져 있거나(키 없음) · 실패하거나 · 검증을 못 넘으면 규칙 기반 문장(`rates_regime.yaml top.read`, 상투 문구를 뺀 새 문장)과 그 이유가
  보인다. `RatesTop.market_read_meta`(source llm/rule · status ok/fallback/pending/skipped · generator api/session · reason · themes · data_caveat · rule_read)에 남고,
  화면은 `AI INTERPRETATION · 10/13 10:30 KST` + 테마 태그 + 데이터 주의, 또는 `RULE-BASED · AI 해석 없음` + 이유. 모델 이름은 어디에도 남기지 않는다.
- **API**: `/rates-regime` 은 LLM 응답을 기다리지 않는다 — 스냅샷 as_of 별로 백그라운드 생성을 한 번 걸고 그동안 `RULE-BASED · AI 해석 생성 중` 을 돌려준다.
  MOCK 시나리오는 실데이터가 아니라 해석을 만들지 않는다(`skipped`). 정량 화면은 LLM 상태와 무관하게 그대로 돈다.
- **캡처**: `capture_rates_regime.py` 가 같은 경로를 돌리고 컨텍스트를 `rates_read_context.json` 으로 남긴다. API 호출이 실패한 날 같은 컨텍스트 · 같은 프롬프트로
  세션에서 만든 출력(`rates_read_session.json`)은 같은 검증을 통과해야만 쓰고, 화면에 `세션 생성` 과 API 실패 사유가 함께 보인다.

### 금리 탭 상단 정리 — REGIME · CURRENT RATES ANALYSIS · HISTORY · POLICY & MACRO EVENTS (2026-10-12)

금리 탭의 위쪽 세 영역만 다시 짰다. Inflation Pressure 이하(Treasury Curve · Nominal Yield Decomposition · Market Confirmation · Key Divergence ·
Market Implication · What Changes the View · Diagnostics)는 이름·계산·내용 그대로다(Key Divergence 는 빈 칸이 생기지 않게 폭만 한 줄로).

- **RATES REGIME**: 큰 판정(`LONG-END RATE / TERM PREMIUM SHOCK`)은 그대로, 바로 아래 **YIELD DIRECTION ↓ FALLING** · `LONG-END YIELD ↓` ·
  `TERM PREMIUM / SUPPLY DRIVEN`. 오른쪽 네 칸은 10Y(수준 · 5D bp · σ) · CONFIDENCE(Evidence Strength) · PRIMARY DRIVER · INFLATION REPRICING.
  MARKET READ 는 최대 2문장이고 숫자를 다시 읽지 않는다. DRIVER READ 는 PRIMARY(지배 driver) · COUNTER(반박된 driver, 없으면 반대 부호 중 가장 큰 것,
  |점수| ≥ 25) · NOT CONFIRMED(물가 · Fed 중 미확인). 기존 driver chip · TRANSMISSION 은 그대로 두고, 긴 판정 근거 문장은 접어 둔다.
- **CURRENT RATES ANALYSIS**: Driver(DOMINANT · LEADING · CONTESTED — 2위와 격차 30 / 10) · Curve(Bull Flattening · Long-end led) · Real Yield(TIPS 10Y) ·
  Breakeven(BE 10Y) 네 칸 + 한 줄, 그 아래 compact **WHAT IS DRIVING RATES?** — 순위 · 점수 · 상태 · 결론 한 줄만 보이고 행을 누르면 근거 계열(σ · 기여)이 펼쳐진다.
- **INFLATION & RATES STATE HISTORY · 1M**: 계산·저장 원칙은 그대로(과거 Recorded 고정 · 없는 날은 1회 Backfill · 오늘 LIVE · 마감 뒤 LOCK).
  머리 숫자만 CURRENT · DURATION · PREVIOUS · 1M SHARE · TRANSITIONS · DRIVER SCORE(1W) 칸으로 나누고 범례를 색 띠 바로 아래에 둔다(`DailyHistoryStrip layout="grid"`,
  금리 탭에서만).
- **POLICY & MACRO EVENTS**(신규): 금리 방향을 바꿀 수 있는 최근 정책 결정과 주요 지표. 값은 출처가 확인된 수기 파일
  `data/policy_events/YYYY-MM-DD.json`(as_of 이하 가장 최근 파일)에서만 오고, 확인 못 한 값(9월 평균시간당임금 · ECB 표결 등)은 비워 둔다.
  `engines/policy_events.py` + `config/policy_events.yaml` 이 ① 놀람(실제 − 컨센서스, HOT/COOL/INLINE/MIXED · STRONG/WEAK) ② 금리 반응(발표일 미국채
  2Y·10Y 일간 종가 − 직전 거래일 종가, FRED) ③ 경로(EVENT → SURPRISE → 기대 경로 → 2Y · 10Y bp) ④ 현재 regime 영향(기대 방향이 지금 10Y 방향과 반대면
  CHALLENGED, 같고 경로 driver 가 지배 driver 면 SUPPORTED, 나머지 NEUTRAL; ECB·BOJ·BOK 는 미국 regime 판정 대상이 아니라 CONTEXT)을 만든다.
  화면은 regime 연결(최근 CPI·PCE 중 최근 것) → RECENT(기본 4, 영향도 → 최근 순) · CENTRAL BANKS(FED · ECB · BOJ · BOK: LAST · RATE · TONE · NEXT, 누르면
  Decision · Previous / Current Rate · Vote · Statement · Chair tone · Projections · Market path · Next meeting · implication · 출처) · UPCOMING(기본 5, 날짜순).
  MOCK 시나리오에는 실제 이벤트를 붙이지 않는다. 오늘 이후 날짜의 결과는 쓰지 않고, 일정은 as_of 기준으로 자동으로 RECENT/UPCOMING 이 갈린다.

### 탭 정리 — 실시간 · AI 센티 · 메모리 업사이클 탭 제거 (2026-10-07)

헤더 탭은 **실시간 · AI 센티 · 금리 · 유가 · 평시** 다섯 개, 이 순서다. 같은 날 이름을 바꿨다: 남은 cockpit 탭 `실시간 2` → `실시간`,
`AI 센티2` → `AI 센티`, `물가 충격` → `금리`, `유가 급등` → `유가`(`config/scenario_checks.yaml` 의 `title` 이 탭 이름이고 키 순서가 탭 순서다 —
시나리오 파일 제목·이 문서의 옛 절 이름 `실시간 2`·`AI 센티2` 는 그대로 둔다). 지운 것은 세 탭이고 **코드·엔진·저장은 지우지 않았다**.
`실시간`(기존 대시보드 그리드)은 `App.tsx` 에서 버튼만 뺐다 — 그리드는 cockpit 의 Details 안에, 그리고 cockpit 집계를 못 받을 때의 대체 화면으로
그대로 있다. `AI 센티`(기본 AI 화면)·`메모리 업사이클`(반도체 합의)은 `config/scenario_checks.yaml` 의 해당 점검에 `tab: false` 를 달아
`check_scenarios()` 가 목록에서 건너뛴다 — 설정·서명·엔진(`ai_regime`, `semiconductor` 합의, MEMORY CYCLE HISTORY 저장)은 남는다. 다시 보이게
하려면 그 줄을 지우면 된다. API `/scenario-check` 와 캡처 `scenario_check.json` 도 네 점검만 돌려준다.

### Daily snapshot history — 모든 History 는 저장 후 고정 (2026-10-07)

대시보드의 모든 History(실시간 Market State 띠, 실시간 2 MARKET REGIME HISTORY · 1M 과 MARKET NOW
sparkline, AI 센티2 의 1M SENTIMENT 와 새 AI TRADE REGIME HISTORY, 물가·유가 탭의 STATE HISTORY,
메모리 업사이클 탭의 MEMORY CYCLE HISTORY, 평시 탭의 띠)가 한 원칙을 따른다:

> History 는 오늘의 모델이 과거를 계속 다시 평가하는 화면이 아니라, **각 날짜의 시스템 판단을 한 번
> 저장한 뒤 고정해서 보여주는 기록**이다.

| 상황 | 처리 | source |
|---|---|---|
| 과거 + snapshot 있음 | 그대로 읽는다. 재계산 없음 | RECORDED / BACKFILLED · locked |
| 과거 + snapshot 없음 | 그 날짜 **이하**의 데이터와 현재 모델로 1회 계산 → 저장 → 즉시 고정 | BACKFILLED · locked |
| 오늘 | LIVE (장중 재계산·교체 가능) → Daily Finalization(`config/history.yaml finalize_time`, 16:10 KST) 이후 RECORDED → 고정 | LIVE → RECORDED |
| 날이 바뀜 | 어제가 아직 LIVE 면 그날 마지막 관측을 RECORDED(last_observation) 로 승격·고정 | RECORDED |

모델·룰이 바뀌어도(model_version · logic_version 이 snapshot 마다 남는다), 데이터가 수정돼도 과거 snapshot 은
바뀌지 않는다. 자동 갱신이 잠긴 snapshot 을 건드리면 `LockedSnapshotError` 로 거부된다. 예외적 수정은
`DailySnapshotManager.correct()` 만 — original / corrected / reason / when / who 의 audit trail 을 남긴다.

구현: `marketpulse/history/` — `store.py`(`JsonDirStore` = `data/history/{tab}.json` 커밋되는 append-only 파일,
`SqliteDailyStore` = `daily_snapshots` 테이블), `manager.py`(`DailySnapshotManager`: get/save/record/finalize/
promote_stale_live/backfill_missing/correct), `calculators.py`(탭별 live→snapshot 변환과 D 이하 데이터만 쓰는
backfill 계산기), `assemble.py`(저장 sequence → `MarketStateHistory` / `SentimentHistory` / `DailyHistory`;
Duration · Previous · Transitions · Share · 1W 변화 전부 sequence 에서), `integrate.py`(탭별 `sync_*`),
`migrate.py`(기존 `data/captures/*/` 의 판정을 RECORDED 로 — 당시 재계산했던 state_history.json 은 옮기지 않는다).
탭 id 는 `market_regime · ai_sentiment · ai_regime · rates_regime · oil_regime · memory_cycle`; 상태 taxonomy·색·
점수 라벨은 `config/history.yaml`. 모든 snapshot 은 snapshot_date · tab_id · state · score · confidence ·
component_scores · key_drivers · data_coverage · data_asof · missing_components · history_source · calculated_at ·
model_version · logic_version · is_final · is_locked · is_backfilled 를 가진다 — label 만 저장하지 않으므로 과거
화면의 색·점수·driver·구성요소는 같은 snapshot 에서 나온다. 결측 입력은 0 이 아니라 결측으로 남고 coverage 에
적힌다; 핵심 데이터가 없는 날은 `INSUFFICIENT_DATA` 로 저장한다(값을 지어내지 않는다).

API: `GET /api/v1/history/{tab}`(`DailyHistory`), `GET /api/v1/history`, 기존 `/market-state/history` 는 stored
sequence 를 돌려주고 `?mode=recomputed` 가 현재 모델로 다시 계산한 별도 뷰다. `/cockpit` 의 history 와 `/ai-regime` 의
`sentiment.history` 도 stored 다(`history_mode`, `recorded_days`, `backfilled_days`, `footnote`). MOCK 시나리오는
프로세스 메모리 저장소에 `mock-{scenario}-` 접두로 분리돼 실데이터 기록과 섞이지 않는다. 저장소 위치는
`MARKETPULSE_HISTORY_DIR`(JSON) 또는 `MARKETPULSE_HISTORY_DB`(SQLite). 주기 실행기(`scheduler.runner`)는 틱마다
시장 판정을 기록한다(LIVE → finalize 뒤 RECORDED). CLI: `python -m marketpulse.history show|migrate|finalize|correct|tabs`.

화면: 각 History 아래 짧은 각주 "각 거래일 최종 snapshot 기준 · 저장 후 고정" 과 Recorded / Backfilled 일수.
BACKFILLED 는 기본 화면에서 크게 표시하지 않고 날짜 툴팁·클릭 상세에서 `Backfilled · calculated 10/07 ·
market_regime_v0.1.0 · rules_f647efd0 · locked` 로 보인다(RECORDED 는 `Recorded`). 공통 컴포넌트
`DailyHistoryStrip`(띠 · score 선 · 범례 · 상세) 이 AI 판정·물가·유가·메모리 탭에 붙는다.
10/7 첫 적용: 캡처 10일치가 RECORDED, 창 안의 나머지 거래일은 BACKFILLED 로 채웠다(시장 7+14, AI 센티 2+18,
AI 판정 2+19, 금리·유가 2+19, 메모리 6+15). 테스트 `tests/test_daily_history.py`(요구서의 Regression Test 1~7).

### Market State 한 달 히스토리 (2026-09-23)

Market State 패널 안, 주도 변수 아래에 최근 22거래일 차트가 붙었다. 한 달을
나누는 **1차 분류는 뷰마다 다르다**: 실데이터·물가 충격 등은 판정 라벨(Risk-On/Off ·
Inflation Shock · Geopolitical Risk …), **AI 센티멘트 뷰만 시장 공포·탐욕 = 온도계
밴드**(결빙=극단적 공포 · 냉각=공포 · 중립 · 온기=탐욕 · 과열=극단적 탐욕,
`scoring.yaml thermometer.bands`). 범례, 위의 얇은 띠, "지금 … n일째 · 직전 … ·
전환 n회" 한 줄, 구간 목록이 그 기준을 따르고 다른 쪽은 보조 줄과 툴팁에 남는다.
서버는 두 기준을 모두 준다(`summary` / `band_summary`, `segments` /
`band_segments`); 어느 쪽을 앞세울지는 `historyPrimaryFor(scenario)` 한 곳에서 정한다.
① 온도계의 세 바늘(종합·가격·뉴스)을 날마다 찍고, 그 뒤에 그날 판정의 확신(%)을
옅은 기둥으로 깔아 보조지표로 읽는다. ② 온도계 재료 스트립 항목을 날짜별
히트맵으로(기간 내내 결측인 항목은 뺐다고 적는다).

**2026-10-07 부터 이 띠는 저장된 daily snapshot 의 sequence 다**(아래 "Daily snapshot history" 절).
과거 날짜는 다시 계산하지 않는다. `engines/state_history.py` 의 재생(같은 시계열을 날짜별로 잘라
같은 엔진을 다시 돌리는 것)은 `?mode=recomputed` 의 별도 RECOMPUTED HISTORY 로만 남아 있고,
backfill(기록이 없는 날짜를 그 날짜까지의 데이터로 1회 계산)에도 같은 `replay_point` 를 쓴다.

엔드포인트는 `GET /api/v1/market-state/history?days=22[&mode=stored|recomputed]`. 기본 일수는
`MARKETPULSE_STATE_HISTORY_DAYS`.

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
