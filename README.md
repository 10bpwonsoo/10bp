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

### 현재 상태 — P2 완료

| 단계 | 범위 | 상태 |
|---|---|---|
| **P0** | 데이터 계약, MOCK 파이프라인, FeatureEngine, API, CLI, 대시보드 골격 | ✅ 완료 |
| **P1** | Market State Engine, Theme Score, Sentiment, 룰 추출, Theme Heatmap | ✅ 완료 |
| **P2** | Confirmation, Divergence, Alert, 저장소, 스케줄러 | ✅ 완료 |
| P3 | Impact Map, LLM 이벤트 추출, AI 요약 | 예정 |
| P4 | 실데이터 어댑터, 히스토리, 백테스트 | 예정 |

대시보드에서 아직 만들지 않은 패널은 해당 단계(P1/P2/P3)를 명시한 자리
표시자로 남는다. **그럴듯한 가짜 숫자로 채우지 않는다.**

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
| `lexicon.yaml` | 감성 사전. 맥락 의존 표현은 일부러 제외했다 |

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
| `MARKETPULSE_LLM_ENABLED` | `false` | false 면 정량 파이프라인만 동작 |
| `ANTHROPIC_API_KEY` | – | P3 에서 사용 |

`LIVE` / `DELAYED` 어댑터는 P4 에서 추가한다. 그 전에 해당 모드로 실행하면
**조용히 MOCK 으로 떨어지지 않고 명확히 실패한다.** 모의 데이터를 실시간이라
표시하는 것은 이 시스템이 피하려는 바로 그 부정직함이다.

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
| `ai_divergence` | 요구 7 의 예시. AI 뉴스·가격은 강한데 외국인 수급이 빠진다 → PRICE_VS_FLOW / NEWS_VS_FLOW 괴리 |

> **괴리와 알림은 두 틱이 필요하다.** 한 틱짜리 격차는 노이즈와 구분되지
> 않아 표시하지 않고, 알림은 직전 틱과 비교해야 "변화" 를 말할 수 있다.
> CLI 는 `--warmup` 으로 미리 돌리고(기본 1), 화면은 폴링하면서 자연히
> 채워진다. 데모 전에 스케줄러를 몇 분 돌려 두면 첫 순간부터 채워진다.

```bash
# 히스토리를 쌓아 두는 주기 실행기
.venv/bin/python -m marketpulse.scheduler.runner \
    --scenario ai_divergence --interval 60 --db data/snapshots.db
```

### 테스트

```bash
.venv/bin/python -m pytest
```

네트워크 없이 돈다. 엔진이 순수 함수이기 때문이다.

> ⚠️ 루트 `conftest.py` 가 `upbit_trading/` 수집을 막는다. 그 안의
> `test_sql_load.py` 는 이름만 테스트일 뿐 **import 되는 순간 SQL Server 에
> 접속해 데이터베이스를 만들고 라이브 Upbit API 를 호출하는** 스크립트다.
> 이 가드를 제거하지 마라.

### 구조

```
marketpulse/
├── models/      데이터 계약 7종 + 공통 타입 (pydantic v2)
├── config/      instruments · themes · factors · state_rules · scoring · lexicon
├── adapters/    MarketAdapter / NewsAdapter + MOCK 구현
├── engines/     features · normalize · scoring · factors · market_state
│                confirmation · sentiment · theme · divergence · alert
│                korean · orchestrator
├── ai/          rule_extractor (LLM 없이 동작하는 기준선)
├── storage/     SnapshotRepository + SQLite 구현
├── scheduler/   주기 실행기
├── vendor/      technical_indicators.py 이식본
├── api/         FastAPI 라우트
├── data/mock/   시나리오 파일
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
