# Market Pulse AI — 사전 분석 및 아키텍처 설계서

> 상태: **설계 검토 단계 (구현 착수 전)**
> 대상 리포지토리: `10bpwonsoo/10bp`
> 브랜치: `claude/market-pulse-ai-design-r7pmsm`
> 작성 기준일: 2026-09-11

이 문서는 구현 승인을 받기 위한 사전 분석 결과다. 코드는 아직 작성하지 않았다.

---

## STEP 1. 현재 구조 분석

### 1.1 Repository Tree

단일 커밋(`32b7b36`), Python 파일 24개, 7,908 라인.

```
/
├── .env.example              # TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 2개만
├── .gitignore
├── README.md
├── upbit_cursor.py           # 1,093 라인 — 리포트 생성 단일 스크립트
└── upbit_trading/            # 23 파일 / 6,815 라인
    ├── config.py             (199)  설정 dataclass
    ├── data_collector.py     (679)  Upbit/Binance 수집기
    ├── db_manager.py         (451)  MS SQL Server 접근
    ├── backtester.py         (521)  백테스트 엔진
    ├── telegram_commands.py  (557)  텔레그램 명령
    ├── trader.py             (413)  주문 실행
    ├── test_sql_load.py      (404)  ※ 테스트 아님 (아래 참조)
    ├── trading_engine.py     (386)  매매 오케스트레이션
    ├── run_analysis.py       (375)
    ├── strategy_historical_low.py (358)
    ├── strategy_box_range.py (356)
    ├── notification_manager.py (327)
    ├── risk_manager.py       (300)
    ├── scalp_engine.py       (282)
    ├── test_data_quality.py  (262)  ※ 테스트 아님
    ├── technical_indicators.py (250)
    ├── price_momentum.py     (233)
    ├── config.py / telegram_bot.py (159) / position_tracker.py (158)
    ├── strategies.py         (58)
    ├── rate_limiter.py       (51)
    └── __init__.py           (36)
```

### 1.2 기존 기술 스택

| 구분 | 사용 기술 | 비고 |
|---|---|---|
| 언어 | Python 3.11 | |
| 데이터 | pandas (10개 파일), numpy (4개) | |
| DB | **MS SQL Server + SQLAlchemy + pyodbc** | `mssql+pyodbc`, T-SQL `MERGE` 사용 |
| 마켓 데이터 | pyupbit, requests, yfinance, FinanceDataReader | |
| 알림 | python-telegram-bot | |
| 인증 | PyJWT | Upbit 주문 서명용 |
| 설정 | python-dotenv (optional import) | |
| 프론트엔드 | **없음** | |
| 테스트 | **없음** | |
| CI | **없음** | |

의존성 선언 파일이 존재하지 않는다. `requirements.txt`, `pyproject.toml`, `setup.py`, `conftest.py`, `pytest.ini` 모두 없다. 의존성은 `README.md:54`에 산문으로만 적혀 있고, 그마저도 실제 사용 패키지 11개 중 5개만 나열되어 있다. `sqlalchemy`, `pyodbc`, `PyJWT`, `yfinance`, `FinanceDataReader`, `python-dotenv`가 누락되어 있다.

### 1.3 실행 방법과 현재 환경에서의 실행 가능성

README 기준 실행 절차는 `.env` 작성 후 `python upbit_cursor.py`다. 실제로는 다음 문제로 **현재 개발 컨테이너에서 실행 불가능하다.**

| 항목 | 실측 결과 |
|---|---|
| Python | 3.11.15 사용 가능 |
| Node / npm | 22.22.2 / 10.9.7 사용 가능 |
| 설치된 서드파티 패키지 | requests, PyYAML, cryptography 정도. **pandas / numpy / sqlalchemy / yfinance 전부 미설치** |
| PyPI 접근 | 가능 (실측 확인) |
| npm 레지스트리 접근 | 가능 (실측 확인) |
| 외부 마켓데이터 API | **전면 차단** |

외부 엔드포인트 접근을 직접 측정한 결과는 다음과 같다.

| 엔드포인트 | 결과 |
|---|---|
| query1.finance.yahoo.com | CONNECT rejected (organization policy) |
| api.stlouisfed.org (FRED) | CONNECT rejected |
| api.upbit.com | CONNECT rejected |
| stooq.com | CONNECT rejected |
| api.anthropic.com | 도달 가능 (HTTP 401, 키 미설정) |

이것이 이번 설계에서 가장 중요한 환경 제약이다. 요구사항 12의 MOCK 모드는 선택 사항이 아니라 이 환경에서 개발을 진행하기 위한 **필수 전제**다.

추가로 DB 접속 기본값이 작성자 개인 PC에 묶여 있다. `CH-PC1\SQLEXPRESS`가 `config.py:68`, `price_momentum.py:17`, `test_sql_load.py:15`, `backtester.py:91` 네 곳에 하드코딩되어 있다.

### 1.4 재사용 가능한 코드

**A등급 — 거의 그대로 사용 가능**

| 파일 | 근거 |
|---|---|
| `upbit_trading/technical_indicators.py` | `sma:14`, `ema:19`, `rsi:27`(Wilder), `macd:46`, `bollinger_bands:72`, `stochastic:101`, `atr:126`, `volume_profile:148`, `vwap:180`, `add_all_indicators:196`. pandas/numpy만 의존하고 리포지토리 내 다른 모듈을 하나도 import 하지 않는다. 거래소 비종속. 단 `vwap:188-190`이 세션 리셋 없이 무한 `cumsum`이라 다일자 데이터에서 조용히 틀린다. 이식 시 수정 필요. 현재 이 모듈은 아무도 import 하지 않는 사문화 코드다. |
| `upbit_trading/rate_limiter.py` | 51라인 슬라이딩 윈도우 리미터. 이름과 달리 Upbit 종속 코드가 0이다. 단 `:36`에서 락을 쥔 채 sleep 하므로 동시 요청이 직렬화된다. 이식 시 락 밖에서 대기하도록 고치고 asyncio 변형을 추가한다. |
| `upbit_trading/strategies.py`의 `TradeSignal` | `signal / strategy_name / confidence / reason / metadata` 구조(`:30-36`). 이번 프로젝트가 요구하는 설명가능성 계약과 정확히 같은 모양이다. Score 스키마의 선례로 채택한다. |
| `backtester.py::_normalize_ohlcv` (`:130-159`) | 컬럼명 별칭 20여 개를 표준 `datetime/open/high/low/close/volume`로 정규화. 어떤 데이터 소스든 어댑터 출력 정규화에 그대로 쓴다. |
| `backtester.py::_calculate_metrics` (`:237-286`) | CAGR, MDD, 승률, Sharpe. 자산 무관하게 동작. P4 히스토리컬 분석에서 사용. |
| `telegram_bot.py::_split_message` (`:138-159`) | 라인 단위 메시지 분할. 범용. |

**B등급 — 패턴만 차용, 코드는 신규 작성**

| 대상 | 차용할 것 |
|---|---|
| `upbit_cursor.py:66-104` `MarketDataCollector` ABC + Crypto/Global/Korean 구현 | Data Adapter Interface의 선례. 단 `async def`만 붙어 있고 내부는 동기 blocking 호출이라 구조 자체는 재작성한다. |
| `upbit_cursor.py:203-218` `SectorReport.sectors` | XLK~XLU 11개 GICS 섹터 ETF 매핑. Theme→Asset 매핑 시드로 즉시 활용. |
| `upbit_trading/config.py` | dataclass + `__post_init__`에서 `os.getenv` fallback. **시크릿 하드코딩이 전혀 없다** (아래 1.5 참조). 이 패턴을 유지한다. |
| `data_collector.py:42-90` `_request` / `_check_rate_limit` | 429는 `retry_delay * attempt * 2`, 5xx는 `retry_delay * attempt`, 그 외 4xx는 즉시 re-raise. 응답 헤더의 잔여 쿼터를 파싱해 선제 sleep. 어댑터 공통 재시도 정책으로 채택. |
| `db_manager.py:153-170` | 엔진 풀링(`pool_pre_ping`, `pool_recycle`) + `@contextmanager connection()`. Repository 구현 패턴으로 차용. T-SQL DDL과 MERGE는 이식 불가. |
| `notification_manager.py:53` `notify_signal`, `:262` `notify_error` | `indicators` dict를 임의 key/value로 렌더하는 방식(`:91-95`)이 Alert 포맷터로 적합. |
| `test_data_quality.py:98-166` | OHLC 무결성 검증(high<low, high<open, low>close 등) + NULL/0 체크. 진짜 함수 `validate_ohlcv(df) -> list[Issue]`로 승격해 데이터 품질 패널에 쓴다. |
| `price_momentum.py:217-228` | 상승/하락/보합 종목 수, 평균 변동률, 총 거래대금. Breadth 엔진의 씨앗. |
| `trading_engine.py:76-148` | start/stop/pause/resume + `_main_loop`/`_execute_cycle`. Pipeline Orchestrator 구조 참고. |

**C등급 — 재사용 불가**

`price_momentum.py`, `test_sql_load.py`, `db_manager.py`의 DDL/MERGE는 MS SQL Server에 직결되어 있다. `trader.py`, `trading_engine.py`, `scalp_engine.py`, `strategy_*.py`, `position_tracker.py`, `risk_manager.py`, `telegram_commands.py`는 주문 실행·포지션 관리 계열로 이번 범위 밖이다.

### 1.5 보안 점검 결과

리포지토리 전체를 크리덴셜 형태 리터럴 기준으로 훑었다. **하드코딩된 API 키나 시크릿은 발견되지 않았다.**

| 설정 클래스 | 시크릿 필드 | 환경변수 | 하드코딩 |
|---|---|---|---|
| `UpbitConfig:29` | access_key, secret_key | `UPBIT_ACCESS_KEY` / `UPBIT_SECRET_KEY` | 없음 (`""` 기본값) |
| `BinanceConfig:43` | api_key, secret_key | `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` | 없음 |
| `DBConfig:56` | username, password | `DB_USERNAME` / `DB_PASSWORD` | 없음 |
| `TelegramConfig:103` | token, chat_id | `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | 없음 |

`.env.example`의 값은 플레이스홀더다. `.gitignore:2-4`가 `.env`와 `*.env`를 올바르게 제외한다.

다만 **`README.md:43`이 "`upbit_trading/config.py`에서 업비트 API 키를 설정하라"고 안내한다.** 이대로 따르면 추적 대상 파일에 시크릿이 들어간다. 신규 문서에서는 이 문장을 쓰지 않고, 기존 README도 수정을 권한다.

### 1.6 문제점

1. **의존성 선언 부재.** 매니페스트가 없어 재현 불가. 신규 패키지에서는 `pyproject.toml`을 먼저 만든다.
2. **환경 하드 바인딩.** MSSQL + ODBC Driver 17 + 개인 PC 호스트명. 리눅스 컨테이너와 해커톤 환경에서 동작하지 않는다.
3. **레이어 혼재.** 수집·계산·문자열 포맷·텔레그램 전송이 한 함수 안에 있다. `upbit_cursor.py` 1,093라인이 대표적이다. 요구사항 15-3, 15-4와 정면으로 충돌한다.
4. **테스트 체계 없음.** `def test_*` 0개, `import pytest` 0개, `assert` 0개다. 더 심각한 것은 `test_sql_load.py`가 **함수조차 아닌 최상위 스크립트**라는 점이다. import 되는 순간 master DB에 접속하고(`:38`) `CREATE DATABASE [CryptoDB]`를 실행하며(`:51`) 테이블을 만들고(`:72-186`) 라이브 Upbit API를 호출한다(`:189-244`). 접속 실패 시 `exit(1)`까지 부른다(`:67`). **pytest를 도입하는 순간 이 파일이 수집되어 DB를 생성하고 외부 API를 두드린다.** pytest 설정에서 명시적으로 제외하거나 파일명을 바꿔야 한다.
5. **깨진 코드.** `backtester.py:495-501`이 `BollingerBandStrategy`, `CombinedStrategy`, `GoldenCrossStrategy`, `MACDStrategy`, `RSIStrategy` 5개를 import 하는데 **전부 존재하지 않는다.** `strategies.py`는 `Signal`, `TradeSignal`, 추상 `Strategy` 3개만 정의한다. `quick_backtest()`는 호출할 때마다 `ImportError`를 낸다.
6. **중복.** 지표 계산이 3중 중복(`technical_indicators.py`, `run_analysis.py:47-83`, `strategy_box_range.py` 인라인), DB 접속 문자열이 4중 중복, DDL이 2중 중복이다.
7. **import 시점 부작용.** `config.py:199`가 전역 설정 인스턴스를 만들고, `db_manager.py:154`가 이를 import 시점에 읽는다.
8. **SQL 식별자 주입 표면.** `db_manager.py:206-240`이 테이블명·컬럼명을 f-string으로 보간한다. 현재는 리터럴만 넘겨 악용 불가하지만, 대시보드 사용자 입력이 닿는 곳에는 절대 노출하면 안 된다.
9. **비동기 위장.** 수집기는 전부 동기 `requests` + `time.sleep`인데 알림 계층만 `async`다. 백엔드는 이 둘을 스레드풀이나 httpx로 이어야 한다.
10. **도메인 불일치.** 기존 코드는 "암호화폐 자동매매 실행"이고 신규 요구는 "멀티에셋 시장 인텔리전스 관측"이다. 읽기 전용 분석 시스템에 주문 실행 계열 코드는 필요 없다.
11. **z-score가 리포지토리 전체에 존재하지 않는다.** `zscore|percentile|rank(` 검색 결과 0건이다. `.std()`는 Sharpe(`backtester.py:270`)와 볼린저(`technical_indicators.py:82`)에만 쓰인다. 이번 프로젝트 정량 레이어의 핵심인 **횡단면 표준화는 전부 신규 구현**이다.

### 1.7 STEP 1 결론

기존 코드를 재작성하지 않는다. `upbit_trading/`은 손대지 않고 그대로 둔다. 신규 `marketpulse/` 패키지를 병렬로 추가하고, A등급 모듈 4개만 복사·수정해 가져온다. 두 시스템은 같은 리포지토리에 공존하되 서로 import 하지 않는다.

---

## STEP 2. 요구사항 분류

분류 기준은 **"이것이 없으면 End-to-End 데모가 성립하는가"**다. 요구사항 13이 기능 수보다 동작하는 데모가 중요하다고 명시했으므로, 이 축으로 정렬한다.

### MUST — 없으면 데모 자체가 성립하지 않음

| ID | 항목 | 근거 |
|---|---|---|
| M1 | 7개 핵심 Data Contract (MarketData / NewsEvent / ThemeState / MarketState / Divergence / Alert / Relationship) | 요구 15-12. 모든 레이어가 이 계약 위에 선다 |
| M2 | Data Adapter Interface + LIVE/DELAYED/MOCK 3모드 | 요구 3, 12. 현 환경에서 외부 API가 전면 차단이라 MOCK 없이는 개발 자체가 불가 |
| M3 | Mock Data Pipeline (재현 가능한 시나리오) | 요구 12. z-score 계산에 필요한 **롤링 히스토리를 포함**해야 함 |
| M4 | Market State Engine (deterministic rule) | 요구 2, 6. 프로젝트의 핵심 원칙 |
| M5 | Theme Engine + Theme Score (가중치 외부화) | 요구 5. "단순 평균 금지" 명시 |
| M6 | Divergence Engine | 요구 7이 "핵심 차별화 기능"으로 명시 |
| M7 | Dashboard: Market State / Theme Heatmap / Divergence / Alert 4개 패널 | 요구 10 |
| M8 | 모든 score의 계산 근거 추적 (contribution breakdown) | 요구 2, 15-6 |
| M9 | 엔진 단위 테스트 (입력→출력 재현) | 요구 14 |
| M10 | LLM 장애 시에도 정량 대시보드 정상 동작 | 요구 15-7 |

### SHOULD — 있어야 제품이지만 없어도 데모는 돈다

| ID | 항목 | 근거 |
|---|---|---|
| S1 | Sentiment Engine (사전 기반 baseline + LLM 보강) | 요구 5. baseline이 M10의 fallback 경로를 만든다 |
| S2 | Flow / Price / Volatility Confirmation 4신호 비교 뷰 | 요구 10 |
| S3 | Alert Engine (레벨이 아닌 "변화" 기반) | 요구 9 |
| S4 | LLM Event Extractor + structured output validation | 요구 4, 14 |
| S5 | AI Market Summary | 요구 6. LLM은 설명만 담당 |
| S6 | Relationship / Impact Map (사전 정의 그래프) | 요구 8 |
| S7 | What's Moving / Why 패널 | 요구 10 |
| S8 | freshness / mode 메타데이터 UI 노출 | 요구 12 |
| S9 | FastAPI API 레이어 | 요구 11 |

### COULD — 시간이 남으면

| ID | 항목 |
|---|---|
| C1 | LLM이 제안한 신규 관계 (사전 정의와 분리 저장, 요구 8) |
| C2 | Real Data Adapter (yfinance / FDR / FRED / ECOS) |
| C3 | Historical analysis / Backtest / validation |
| C4 | Portfolio linkage |
| C5 | Implied volatility, 선물 수급 |
| C6 | WebSocket 실시간 push |
| C7 | Novelty score (뉴스 중복 제거) — 계산 방법이 요구사항에 미정의, STEP 7 참조 |

### WON'T — 이번 범위 밖임을 명시

주문 실행, 포지션 관리, 리스크 관리(기존 `upbit_trading` 영역). 사용자 인증, 멀티테넌시.

---

## STEP 3. Architecture 제안

### 3.1 기술 스택 선정과 근거

| 레이어 | 선택 | 근거 |
|---|---|---|
| Backend | Python 3.11 + FastAPI + Uvicorn | 기존 자산이 Python/pandas다. 정량 계산을 Python에 두어야 `technical_indicators.py`를 재사용할 수 있다 |
| Data Contract | **Pydantic v2** | 데이터 계약 정의와 LLM structured output 검증을 **같은 도구 하나로** 해결한다. 요구 14의 "LLM 출력은 반드시 structured output validation을 거친다"가 스키마 정의의 부산물로 공짜로 따라온다 |
| Quant | pandas + numpy | 설치 검증 완료 (pandas 3.0.5 / numpy 2.4.6) |
| Frontend | React 19 + TypeScript + Vite + TailwindCSS + Recharts | Node 22 확인. 고밀도 그리드 레이아웃을 빠르게 만들려면 Tailwind가 유리 |
| Storage (정의) | YAML | 테마·관계·가중치는 git diff로 변경 이력이 보여야 한다 |
| Storage (시계열) | SQLite + Parquet | MSSQL은 이 환경에서 뜨지 않는다. SQLite는 zero-config. Repository 인터페이스로 감싸 Postgres/Timescale 교체를 흡수 |
| AI | Anthropic Claude | 키는 환경변수. 모델 선택과 비용은 STEP 7 참조 |
| Cache | in-process TTL cache | P0~P3. Redis는 P4 옵션 |

스택 선정에서 실제로 고민한 지점은 프론트엔드다. **Streamlit을 검토했고 기각했다.** 30분이면 뜨지만 요구 10의 "10~20초 안에 시장 상태 파악", "정보 밀도와 즉시성"을 만족하는 레이아웃 제어가 불가능하다. 다만 데모 리스크 대비책으로 **CLI 텍스트 출력을 P0에 함께 만든다** (STEP 7-7 참조). 프론트가 무너져도 데모는 돈다.

설치 가능성을 사전 검증했다. `fastapi 0.141.1 / uvicorn 0.52.4 / pydantic 2.13.5 / pandas 3.0.5 / numpy 2.4.6 / pytest 9.1.1 / httpx 0.28.1` 포함 20개 패키지가 충돌 없이 해석된다.

### 3.2 데이터 흐름

```
[Scheduler / Orchestrator]                         tick = 60s
        │
        ├─(1)─▶ MarketAdapterRegistry ──▶ mode: LIVE | DELAYED | MOCK
        │         Equity / Rates / FX / Commodity /
        │         Volatility / Flow / Breadth Adapter
        │            └─▶ List[MarketDataPoint] + DataMeta
        │
        └─(2)─▶ NewsAdapterRegistry
                  RSS / File / Mock
                     └─▶ List[RawNewsItem]
                             │
                             ▼
                  [Normalization Layer]
                   MarketSnapshot(as_of, points{}, meta{})
                             │
        ┌────────────────────┴────────────────────┐
        ▼                                         ▼
┌────────────────────────┐          ┌──────────────────────────┐
│ QUANT LAYER            │          │ AI LAYER (optional)      │
│ (deterministic)        │          │                          │
│                        │          │ EventExtractor (LLM)     │
│ FeatureEngine          │          │   → NewsEvent (validated)│
│  · 수익률 1d/5d/20d     │          │   ✗ 실패 ⇒ RuleExtractor │
│  · rolling z-score     │          │ Classifier (theme 태깅)  │
│  · realized vol, RSI   │          │                          │
│  · breadth, MA 이격     │          │  ※ 이 레이어가 통째로     │
│ FactorEngine           │          │    죽어도 아래는 동작한다  │
│  · 11개 factor score   │          └──────────┬───────────────┘
│ MarketStateEngine      │                     │
│  · rule → label + conf │                     │
└───────────┬────────────┘                     │
            └──────────────┬────────────────────┘
                           ▼
                 [FUSION LAYER]
                   ThemeEngine          뉴스側 + 시장側 결합
                   ConfirmationEngine   cross-asset 확인
                   DivergenceEngine     내러티브 vs 실제 괴리
                   RelationshipEngine   Event→Theme→Macro→Asset→Sector
                   AlertEngine          직전 스냅샷 대비 Δ
                           │
                           ▼
                 [NarrativeEngine] (LLM, optional)
                   deterministic 결과만 입력.
                   숫자를 새로 만들지 못하게 입력을 고정한다.
                           │
                           ▼
                 [SnapshotStore]  SQLite + Parquet
                           │
                           ▼
                 [FastAPI]
                   GET /api/v1/snapshot        ← 대시보드는 이것 하나만 호출
                   GET /api/v1/market-state
                   GET /api/v1/themes
                   GET /api/v1/divergences
                   GET /api/v1/alerts
                   GET /api/v1/impact-map
                   GET /api/v1/news
                   GET /api/v1/health          ← mode, freshness, coverage
                           │
                           ▼
                 [React Dashboard]  5s polling (P4: WebSocket)
```

### 3.3 핵심 설계 결정 3가지

**① Snapshot-first — 엔진은 순수 함수다.**

모든 엔진의 시그니처를 `f(MarketSnapshot, List[NewsEvent], Optional[PreviousSnapshot]) -> Result` 형태로 고정한다. 전역 상태도, I/O도, 시계도 엔진 안에 없다. 이 결정 하나가 요구 14의 재현성을 구조적으로 보장한다. 같은 입력을 넣으면 언제나 같은 출력이 나오고, 과거 스냅샷을 그대로 재생할 수 있고, 테스트에 네트워크가 필요 없다.

**② LLM은 파이프라인 바깥의 enrichment다.**

LLM이 닿는 지점은 단 두 곳이다. 뉴스에서 `NewsEvent`를 추출하는 곳과, 확정된 결과를 자연어로 설명하는 곳. 두 지점 모두 실패해도 `IntelligenceSnapshot`은 생성된다. 추출은 키워드 기반 `RuleExtractor`가 항상 fallback으로 대기하고, 설명은 템플릿 문장으로 대체된다. 요구 15-7이 이 구조의 직접적 근거다.

**③ 모든 합성 점수는 값이 아니라 `ScoreBreakdown`을 반환한다.**

`(value, method, contributions[], inputs_hash)` 4-tuple이다. UI에서 숫자에 hover 하면 "Oil z=+2.1에 가중치 0.35를 곱한 0.735, Rates z=+1.5에 0.30을 곱한 0.45 ..."가 그대로 나온다. 요구 2와 15-6을 데이터 구조 차원에서 강제한다.

---

## STEP 4. 핵심 Data Schema 정의

### 4.0 공통 타입

```python
DataMode = Literal["LIVE", "DELAYED", "MOCK"]

class DataMeta:
    source: str                  # "yfinance" | "mock:scenario_baseline" | "fdr"
    mode: DataMode
    retrieved_at: datetime       # UTC
    as_of: datetime              # 데이터 기준 시각 (UTC)
    freshness_sec: int           # retrieved_at - as_of
    is_stale: bool               # freshness_sec > threshold
    quality: Literal["OK", "PARTIAL", "STALE", "MISSING"]

class ScoreContribution:
    key: str                     # "BRENT"
    raw_value: float             # 2.34 (%)
    normalized: float            # 2.1 (z) 또는 0~1
    weight: float                # 0.35
    contribution: float          # normalized * weight
    note: str                    # "60일 롤링 대비"

class ScoreBreakdown:
    value: float
    method: str                  # "weighted_z_tanh_v1"
    contributions: List[ScoreContribution]
    missing_inputs: List[str]    # 재정규화된 항목
    inputs_hash: str             # sha256 — 재현성 검증용
    computed_at: datetime
```

`inputs_hash`는 정렬된 `key=value` 문자열의 SHA-256이다. 테스트에서 "같은 입력 → 같은 해시 → 같은 값"을 단언한다. 요구 14의 재현성을 기계적으로 검증하는 장치다.

### 4.1 MarketData

```python
AssetClass = Literal["equity","rate","fx","commodity","volatility",
                     "flow","breadth","credit"]

class Instrument:                # 레지스트리 (config/instruments.yaml)
    id: str                      # "KOSPI","US10Y","USDKRW","BRENT","VIX"
    name: str
    asset_class: AssetClass
    region: Optional[str]        # "KR" | "US" | "CN" | "GLOBAL"
    unit: Literal["price","percent","index","bp","krw_bn","count","ratio"]
    currency: Optional[str]
    higher_is_risk_on: Optional[bool]   # VIX는 False — 방향성 해석에 필수
    calendar: str                # "KRX" | "NYSE" | "24H" — 휴장 처리용
    tags: List[str]

class MarketDataPoint:
    instrument_id: str
    as_of: datetime
    value: float
    prev_close: Optional[float]
    change: Optional[float]
    change_pct: Optional[float]
    change_bp: Optional[float]   # rates 전용 (금리는 %가 아니라 bp로 말한다)
    volume: Optional[float]
    meta: DataMeta

class MarketFeature:             # FeatureEngine 산출
    instrument_id: str
    as_of: datetime
    ret_1d, ret_5d, ret_20d: Optional[float]
    z_1d, z_5d, z_20d: Optional[float]
    zscore_window: int           # 기본 60
    realized_vol_20d: Optional[float]
    rsi_14: Optional[float]
    ma_dist_20, ma_dist_60: Optional[float]
    percentile_1y: Optional[float]
    meta: DataMeta

class MarketSnapshot:
    as_of: datetime
    mode: DataMode
    points: Dict[str, MarketDataPoint]
    features: Dict[str, MarketFeature]
    coverage: float              # 요구 instrument 중 확보 비율
    missing: List[str]
```

`unit`과 `change_bp`를 분리한 이유는 금리 때문이다. US10Y가 4.2%에서 4.35%로 갔을 때 "3.6% 상승"이라고 표시하면 현업에서 쓸 수 없다. "15bp 상승"이어야 한다. `higher_is_risk_on`은 factor 계산에서 부호를 자동 결정한다.

### 4.2 NewsEvent

```python
TimeHorizon = Literal["intraday","short","medium","long"]
Direction   = Literal["up","down","neutral"]

class Entity:
    name: str
    type: Literal["company","country","person","organization",
                  "commodity","currency","index"]
    ticker: Optional[str]

class AssetImpact:
    instrument_id: Optional[str] # Instrument 레지스트리와 연결되면 채움
    label: str                   # "Brent","Airlines" — 미연결이어도 표시는 가능
    direction: Direction
    magnitude: Literal["low","medium","high"]
    confidence: float            # 0~1
    rationale: str

class RawNewsItem:
    id, title, body, url, publisher: str
    published_at: datetime
    language: str
    meta: DataMeta

class NewsEvent:
    id: str
    source_item_ids: List[str]   # 여러 기사가 한 이벤트로 병합될 수 있다
    event: str
    event_type: Literal["geopolitical","macro","policy","earnings",
                        "supply","regulation","flow","other"]
    themes: List[str]            # Theme 레지스트리 FK
    entities: List[Entity]
    sentiment: int               # -100 ~ +100
    impact_score: int            # 0 ~ 100
    novelty_score: int           # 0 ~ 100
    time_horizon: TimeHorizon
    affected_assets: List[AssetImpact]
    direction: Dict[str, Direction]        # 요구 4 원문 스키마 유지
    second_order: List[RelationshipEdge]   # Oil↑ → Inflation↑ → Rates↑
    reason: str
    source: str
    timestamp: datetime

    # --- 출처 추적 (요구 15-11) ---
    extractor: Literal["llm","rule","manual"]
    extractor_model: Optional[str]
    validation: ValidationReport  # {schema_ok, errors[], clamped_fields[]}
    confidence: float             # 0~1
```

`extractor` 필드가 중요하다. LLM이 만든 것인지 룰이 만든 것인지 사람이 넣은 것인지가 데이터에 남는다. `clamped_fields`는 LLM이 sentiment를 150으로 뱉었을 때 100으로 자른 사실을 기록한다. 조용히 고치지 않고 기록한다.

`second_order`가 요구 4의 "Oil↑ → Inflation Expectation↑ → Rates↑ → Growth Equity Valuation↓" 연쇄를 표현하는 자리다.

### 4.3 ThemeState

```python
class Theme:                     # 레지스트리 (config/themes.yaml)
    id: str                      # "ai","semiconductor","oil","geopolitical_risk"
    name: str
    aliases: List[str]
    keywords: List[str]          # RuleExtractor가 쓴다
    parent: Optional[str]
    instruments: List[ThemeInstrument]   # {instrument_id, weight, direction}
    macro_factors: List[str]

class ThemeState:
    theme_id: str
    as_of: datetime

    theme_score: float           # -100 ~ +100
    breakdown: ScoreBreakdown

    news_sentiment: float        # -100 ~ +100
    news_volume: float           # z-score
    news_momentum: float
    price_momentum: float
    flow_momentum: float
    volatility: float

    cross_asset_confirmation: Literal["HIGH","MEDIUM","LOW","CONFLICT"]
    confirmation_score: float    # -100 ~ +100
    confidence: float            # 0 ~ 100
    confidence_breakdown: ScoreBreakdown

    last_change: float           # 직전 스냅샷 대비 Δ
    last_change_window: str      # "1h"

    supporting_events: List[str]      # NewsEvent.id
    supporting_instruments: List[str]
    data_quality: Literal["OK","PARTIAL","INSUFFICIENT"]
```

요구 5의 예시(`AI: Sentiment +78 / News Momentum +65 / Price +52 / Flow +71 / Confirmation HIGH / Confidence 82%`)가 이 스키마에 1:1로 대응한다.

### 4.4 MarketState

```python
StateLabel = Literal["RISK_ON","RISK_OFF","GROWTH_SHOCK","INFLATION_SHOCK",
                     "LIQUIDITY_STRESS","POLICY_DRIVEN","GEOPOLITICAL_RISK",
                     "NEUTRAL"]

class FactorScore:
    factor: str    # Growth|Inflation|Rates|USD|Liquidity|RiskAppetite|
                   # Credit|Volatility|China|KoreaFlow|KoreaBreadth
    score: float                 # z 단위, 대략 -3 ~ +3
    breakdown: ScoreBreakdown
    data_quality: Literal["OK","PARTIAL","INSUFFICIENT"]

class RuleMatch:
    rule_id: str
    expression: str              # "Inflation >= 1.0"
    passed: bool
    observed: float              # 2.05

class StateHypothesis:
    label: StateLabel
    score: float                 # 0 ~ 1
    matched_rules: List[RuleMatch]

class DriverItem:
    instrument_id: str
    label: str                   # "Oil"
    z: float                     # +2.1
    direction: Literal["up","down","flat"]
    arrow: str                   # "↑↑" | "↑" | "→" | "↓"

class MarketState:
    as_of: datetime
    primary_label: StateLabel
    secondary_label: Optional[StateLabel]
    confidence: float            # 0 ~ 100
    confidence_breakdown: ScoreBreakdown
    factors: Dict[str, FactorScore]        # 11개 전부
    hypotheses: List[StateHypothesis]      # 전체 순위
    main_drivers: List[DriverItem]
    cross_asset_confirmation: ConfirmationResult
    narrative: Optional[str]
    narrative_source: Literal["llm","template","none"]

class ConfirmationResult:
    confirmed: List[str]
    unconfirmed: List[str]
    conflicting: List[str]
    score: float                 # -1 ~ +1
    verdict: Literal["HIGH","MEDIUM","LOW"]
    note: str
```

요구 6이 "하나의 Label만 보여주기보다"라고 했으므로 `hypotheses` 전체 순위와 `factors` 11개를 **항상 함께** 반환한다. 단일 라벨은 편의 필드일 뿐이다.

`narrative`가 `None`이어도 UI는 완전히 동작해야 한다. `narrative_source`가 `"none"`이면 프론트가 해당 영역을 접는다.

### 4.5 Divergence

```python
DivergenceType = Literal[
    "NEWS_VS_PRICE","NEWS_VS_FLOW","PRICE_VS_FLOW","THEME_VS_ASSET",
    "RISK_VS_VOL","OIL_VS_INFLATION_EXP","BREADTH_VS_INDEX"]

class DivergenceLeg:
    name: str                    # "News Sentiment"
    value: float                 # +82
    z: Optional[float]
    direction: Literal["up","down","flat"]

class Divergence:
    id: str
    type: DivergenceType
    as_of: datetime

    severity: float              # 0 ~ 100
    severity_band: Literal["LOW","MEDIUM","HIGH","CRITICAL"]
    duration_periods: int        # 연속 감지 횟수
    first_detected_at: datetime

    related_theme: Optional[str]
    related_assets: List[str]

    legs: List[DivergenceLeg]    # 재현용 원자료
    gap: float                   # 표준화된 격차
    rule_id: str

    explanation: str             # 템플릿 — LLM 없이 생성된다
    llm_commentary: Optional[str]
```

요구 7의 예시(`AI Divergence: News +82 / Price +61 / Flow -34`)는 `legs` 3개로 표현되고, `explanation`은 템플릿으로 "AI 관련 뉴스와 가격은 긍정적이나 외국인 수급이 동반되지 않고 있음"을 생성한다. LLM은 여기서 필요 없다.

### 4.6 Alert

```python
AlertType = Literal[
    "THEME_SENTIMENT_SPIKE","NEWS_VOLUME_SPIKE","PRICE_ZSCORE_SPIKE",
    "FLOW_REVERSAL","VOL_SPIKE","DIVERGENCE_OPENED","STATE_CHANGE",
    "DATA_QUALITY"]

class AlertTrigger:
    rule_id: str
    metric: str                  # "news_volume_3h"
    current: float               # 38
    baseline: float              # 10
    delta: float                 # 28
    delta_pct: float             # 280.0
    threshold: float             # 150.0
    window: str                  # "3h"

class Alert:
    id: str
    as_of: datetime
    type: AlertType
    severity: float              # 0 ~ 100
    severity_band: Literal["INFO","WARN","HIGH","CRITICAL"]
    title: str
    message: str
    trigger: AlertTrigger
    related_theme: Optional[str]
    related_assets: List[str]
    related_events: List[str]
    dedupe_key: str
    first_fired_at: datetime
    last_fired_at: datetime
    fire_count: int
    state: Literal["NEW","ONGOING","RESOLVED"]
```

요구 9가 "단순 수준보다 변화를 중요하게 본다"고 했으므로 `baseline`과 `delta`를 **필수 필드**로 둔다. 값만 있고 기준선이 없는 알림은 만들 수 없게 스키마가 막는다. `dedupe_key`와 `fire_count`가 같은 알림의 반복 발화를 억제한다. 기존 코드에는 중복 제거 장치가 전혀 없었다.

### 4.7 Relationship

```python
NodeType = Literal["EVENT","THEME","MACRO_FACTOR","ASSET","SECTOR"]

class RelationshipNode:
    id: str
    type: NodeType
    label: str
    ref_id: Optional[str]        # NewsEvent.id / Theme.id / Instrument.id

class RelationshipEdge:
    id: str
    source_id: str
    target_id: str
    direction: Literal["positive","negative","ambiguous"]
    strength: float              # 0 ~ 1
    confidence: float            # 0 ~ 1
    lag: Literal["immediate","hours","days","weeks"]
    reason: str

    # --- 요구 8, 15-11의 핵심 ---
    origin: Literal["predefined","llm_proposed","statistical"]
    status: Literal["active","candidate","rejected"]
    evidence: List[str]
    created_at: datetime
    verified_by: Optional[str]

class ImpactMap:
    as_of: datetime
    root_event_id: Optional[str]
    nodes: List[RelationshipNode]
    edges: List[RelationshipEdge]
    max_depth: int
```

`origin`과 `status`가 LLM 추론 관계를 사전 정의 관계와 분리한다. UI에서 `predefined`는 실선, `llm_proposed`는 점선과 다른 색으로 그린다. 불확실한 시장 관계를 확정 사실처럼 제시하지 않는다는 요구 15-11이 데이터 구조에 박혀 있다.

### 4.8 IntelligenceSnapshot (API 최상위 응답)

```python
class IntelligenceSnapshot:
    as_of: datetime
    mode: DataMode
    market_state: MarketState
    themes: List[ThemeState]
    divergences: List[Divergence]
    alerts: List[Alert]
    impact_maps: List[ImpactMap]
    events: List[NewsEvent]
    whats_moving: List[MovingItem]    # {label, z, change, kind}
    data_health: DataHealth           # {coverage, stale[], llm_status,
                                      #  engine_timings_ms{}}
    engine_versions: Dict[str, str]
```

대시보드는 `GET /api/v1/snapshot` 한 번으로 화면 전체를 그린다. 패널마다 호출을 나누면 패널 간 시점이 어긋나 "Market State는 10:00 기준인데 Theme은 10:01 기준"인 상태가 생긴다. 시장 분석 도구에서 이것은 치명적이다.

---

## STEP 5. Scoring Methodology

### 5.0 4가지 원칙

1. **모든 원자료는 롤링 z-score로 표준화한다.** 유가는 %, 금리는 bp, VIX는 포인트다. 단위가 다른 것을 그대로 더하면 의미가 없다.
2. **가중치는 코드가 아니라 `config/scoring.yaml`에 둔다.** 요구 5, 15-9.
3. **결측은 0으로 채우지 않는다.** 가중치를 재정규화하고 confidence를 깎는다. 0으로 채우면 "데이터가 없음"이 "중립임"이라는 거짓 정보로 둔갑한다. 이것이 정량 시스템에서 가장 흔한 조용한 오류다.
4. **모든 합성 점수는 contributions 배열을 동봉한다.** 요구 15-6.

### 5.1 표준화 함수

```
z(x) = (x_t - mean(x, W)) / std(x, W)
    W = 60 (일봉) / 120 (인트라데이)
    clamp(z, -4, +4)

squash(z) = 100 * tanh(z / 2)      →  -100 ~ +100
```

**왜 tanh인가.** 선형 스케일링은 극단치에서 포화되지 않는다. 한 자산이 +6σ로 튀면 그 자산 하나가 전체 점수를 지배한다. tanh는 ±2σ 부근에서 ±76 정도로 부드럽게 포화되어 outlier에 견고하다. 동시에 단조 증가하고 미분 가능해서 해석이 직관적이다. clamp는 z 계산 단계에서 한 번 더 안전장치를 둔 것이다.

`squash(2) ≈ 76`, `squash(3) ≈ 91`, `squash(1) ≈ 46`. 요구사항 예시의 "+78" 같은 값이 대략 2σ 수준에 대응하도록 스케일을 맞췄다.

### 5.2 Factor Score

각 factor는 사전 정의된 instrument 묶음의 **부호 가중 z 평균**이다.

```
F_j = Σ_i (s_ij · w_ij · z_i) / Σ_i w_ij        (available i만, 재정규화)
    s_ij ∈ {+1, -1}   방향 부호
```

`config/factors.yaml` 초기값:

| Factor | 구성 |
|---|---|
| Inflation | +0.35·z(Brent) +0.25·z(WTI) +0.20·z(Copper) +0.20·z(BE10Y) |
| Rates | +0.40·z(US10Y_bp) +0.30·z(US2Y_bp) +0.30·z(KR10Y_bp) |
| Growth | +0.30·z(Copper/Gold) +0.30·z(Russell) +0.25·z(YieldCurve) +0.15·z(KOSPI) |
| RiskAppetite | +0.30·z(SPX) +0.25·z(NDX) −0.25·z(VIX) −0.20·z(CreditSpread) |
| USD | +0.60·z(DXY) +0.40·z(USDKRW) |
| Volatility | +0.60·z(VIX) +0.40·z(RealizedVol20d) |
| Credit | +1.00·z(HY_OAS) |
| Liquidity | −0.50·z(CreditSpread) −0.30·z(MOVE) +0.20·z(거래대금) |
| China | +0.50·z(HSCEI) +0.30·z(Copper) +0.20·z(CNH) |
| KoreaFlow | +0.60·z(외국인순매수) +0.40·z(기관순매수) |
| KoreaBreadth | +0.60·z(상승종목비율) +0.40·z(신고가−신저가) |

**왜 통계 추정이 아니라 사전 정의 부호 가중인가.** 해커톤 기간에 PCA나 회귀로 factor를 추정하면 표본이 부족해 결과가 불안정하고, 무엇보다 **설명이 안 된다.** "PC1이 0.7이라 Risk-Off입니다"는 운용자에게 아무 정보가 아니다. 사전 정의 부호는 매크로 상식과 일치하고, YAML에서 즉시 조정할 수 있으며, 모든 기여도가 그대로 보인다. 통계적 추정은 P4의 validation 단계에서 이 초기값을 검증하는 용도로 쓴다.

### 5.3 Market State Score

**require + support 2단 구조의 룰 기반 스코어링.**

```yaml
# config/state_rules.yaml
INFLATION_SHOCK:
  require:
    - Inflation >= 1.0
  support:
    - {expr: "Rates >= 0.8",         weight: 0.30}
    - {expr: "Volatility >= 0.5",    weight: 0.20}
    - {expr: "RiskAppetite <= -0.5", weight: 0.30}
    - {expr: "Growth <= 0.0",        weight: 0.20}
```

```
score(label) = 0                              if require 미충족
             = 0.5 + 0.5 · Σ(w_k · passed_k)  otherwise
```

**왜 require gate가 필요한가.** 순수 가중합만 쓰면 핵심 조건 없이도 라벨이 켜진다. 인플레이션 지표가 전혀 안 움직였는데 금리와 변동성만으로 "Inflation Shock"이 뜨면 그 시스템은 신뢰를 잃는다. require가 오탐을 막고, support가 강도를 준다. 그리고 어떤 룰이 통과·실패했는지 `matched_rules`에 `{expr, passed, observed}`로 그대로 남아 "왜 Inflation Shock인가"에 즉답할 수 있다.

`primary = argmax(score)`, `secondary = 2등` (단 score ≥ 0.5일 때만).

**요구 14의 검증 케이스가 이 룰로 어떻게 재현되는지:**

입력 `Oil +2σ, Rates +1.5σ, VIX +1.5σ, Equity −1.2σ` →
Inflation factor ≈ +1.2 (Brent·WTI 기여), Rates ≈ +1.5, Volatility ≈ +0.9, RiskAppetite ≈ −1.1 →
`INFLATION_SHOCK`: require(Inflation ≥ 1.0) 통과, support 4개 전부 통과 → score 1.0
`RISK_OFF`: require(RiskAppetite ≤ −0.8) 통과, support 일부 → score ≈ 0.85
결과: primary = INFLATION_SHOCK, secondary = RISK_OFF. 이것을 `tests/test_market_state.py`에 골든 케이스로 고정한다.

### 5.4 Confidence Score

```
Conf = 100 · (0.40·Separation + 0.25·Confirmation
            + 0.20·Coverage   + 0.15·Persistence)

Separation   = clamp((s₁ − s₂) / 0.5, 0, 1)     1등과 2등의 격차
Confirmation = cross-asset 확인 비율 (5.5 참조)
Coverage     = 확보 instrument 비중
Persistence  = 직전 N틱 중 같은 라벨이 나온 비율
```

**설계 근거.** 신뢰도는 "얼마나 강한가"가 아니라 "얼마나 확실한가"다. 강도는 factor z가 이미 표현하고 있으므로 confidence에 다시 넣으면 같은 정보를 두 번 세는 것이다. 대신 서로 **독립적인 불확실성의 원천 4가지**를 넣었다.

- 1등과 2등이 붙어 있으면(Risk-Off 0.82 vs Growth Shock 0.79) 어느 쪽인지 확신할 수 없다 → Separation
- 유가는 올랐는데 USD와 금이 반응하지 않으면 확신할 수 없다 → Confirmation
- 데이터의 40%가 비어 있으면 확신할 수 없다 → Coverage
- 한 틱 나타났다 사라지면 확신할 수 없다 → Persistence

Separation에 가장 큰 가중치를 준 것은, 라벨 자체가 틀릴 가능성이 가장 직접적인 불확실성이기 때문이다.

### 5.5 Confirmation Score

사전 정의된 **기대 반응표**를 사용한다. 예를 들어 Inflation Shock의 기대 반응은 `Oil↑, BE↑, Rates↑, Gold↑, GrowthEquity↓, USD↑`다.

```
confirmed_i   ⟺ sign(z_i) == expected_i  and  |z_i| >= 0.5
conflicting_i ⟺ sign(z_i) != expected_i  and  |z_i| >= 1.0
unconfirmed_i ⟺ |z_i| < 0.5

Confirmation = (#confirmed − #conflicting) / #expected
verdict: ≥0.6 HIGH / ≥0.3 MEDIUM / else LOW
```

이 구조가 요구 6의 문장을 **자동으로** 만들어낸다. USD의 |z|가 0.4라면 `unconfirmed` 목록에 들어가고, 그 사실이 Confirmation을 떨어뜨리고, Confirmation이 Confidence를 떨어뜨린다. 그리고 템플릿이 `unconfirmed` 목록을 읽어 "유가는 강하게 상승했으나 USD 반응은 제한적이므로 글로벌 Risk-Off 전이는 아직 제한적"을 생성한다. **LLM 없이 이 문장이 나온다.** LLM은 이것을 더 매끄럽게 다듬을 뿐이다.

conflicting의 임계(1.0)를 confirmed(0.5)보다 높게 둔 이유는 비대칭이다. "기대와 반대로 강하게 움직였다"는 주장은 "기대대로 조금 움직였다"보다 강한 주장이므로 더 높은 증거를 요구한다.

### 5.6 Sentiment Score

**2단 구조 — baseline은 항상 동작한다.**

```
Baseline (LLM 불필요): 극성 사전 + 부정어 처리 → -100 ~ +100
LLM (가용 시):         NewsEvent.sentiment

S_item = α · S_llm + (1−α) · S_lex,    α = 0.7  (LLM 검증 통과 시)
                                       α = 0    (그 외)
```

Theme 단위 집계에서 **단순 평균을 쓰지 않는다** (요구 5 명시). 시간 감쇠 · 영향도 · 출처 3중 가중이다.

```
w_k = exp(−ln2 · age_hours_k / H) · (impact_k / 100) · src_weight_k
    H = 6h (intraday) / 24h (daily)

ThemeSentiment = Σ(w_k · S_k) / Σ(w_k)
```

**왜 지수 감쇠인가.** 뉴스의 시장 관련성은 지수적으로 줄어든다. 단순 평균은 3일 전 기사와 10분 전 기사를 같은 무게로 취급해 급변을 완전히 놓친다. 반감기 6시간은 장중 이슈의 수명에 대한 실무적 감각을 반영한 초기값이며 YAML에서 조정한다. 영향도 가중은 사소한 기사 20건이 헤드라인 1건을 희석하는 것을 막는다.

**News Volume / Momentum:**

```
NewsVolume_z = z(최근 3h 건수  vs  직전 7일 "같은 시간대" 건수)
NewsMomentum = squash( z(Σ S·w, 3h) − z(Σ S·w, 직전 24h) )
```

Volume의 기준선을 "같은 시간대"로 잡은 것이 중요하다. 장중과 새벽의 뉴스량 차이가 몇 배에 달하므로, 단순 이동평균을 기준선으로 쓰면 **매일 개장 때마다 가짜 스파이크**가 뜬다. 알림 엔진이 매일 아침 오탐을 내는 시스템은 쓰이지 않는다.

### 5.7 Theme Score

```
ThemeScore = 100 · tanh( Σ(w_c · n_c) / Σ|w_c| )
    n_c = (각 component의 z) / 2
```

| Component | 기본 weight |
|---|---|
| price_momentum | **0.30** |
| news_sentiment | 0.25 |
| flow_momentum | 0.20 |
| news_momentum | 0.15 |
| volatility | **−0.10** |

**가중치 설계 근거.** price_momentum이 가장 크다. 가격은 유일하게 조작할 수 없는 실제 체결 정보이고, 뉴스는 후행하거나 과장될 수 있다. news_sentiment를 가격보다 낮게 둔 것은 이 시스템의 입장 때문이다. **"뉴스가 시장을 움직인다"가 아니라 "시장이 뉴스를 검증한다."** 요구 1의 "뉴스의 내러티브와 실제 가격·수급이 일치하는가"라는 질문 자체가 시장 쪽에 무게를 두고 있다.

volatility에 음수 가중치를 준 것은 의도적이다. 테마 변동성 급등은 일반적으로 테마의 건전성이 아니라 불안정성을 뜻한다. 급등 자체를 긍정으로 읽으면 붕괴 직전 테마가 최고점을 받는다.

테마의 price/flow momentum은 theme→instrument 매핑의 가중 평균이다.

```
price_momentum_theme = Σ(w_i · d_i · z_i) / Σ(w_i)      d_i = ±1 방향
```

**Theme Confirmation:**

```
signals = [news_sentiment, price_momentum, flow_momentum]
|signal| >= 20 인 것만 유효 신호로 카운트
Confirmation = 100 · (agree − disagree) / valid_count
HIGH ≥ 60 / MEDIUM ≥ 25 / LOW ≥ −25 / CONFLICT < −25
```

**Theme Confidence:**

```
Conf = 100 · (0.35·Confirmation_norm + 0.25·Coverage
            + 0.20·NewsSufficiency   + 0.20·Stability)

NewsSufficiency = min(1, n_events / 5)
Stability       = 1 − min(1, stdev(theme_score, 최근 6틱) / 40)
```

**NewsSufficiency가 왜 필요한가.** 기사 1건으로 만든 +78과 기사 20건으로 만든 +78은 같은 확신도가 아니다. 전자는 한 기자의 의견이고 후자는 시장의 관심이다. 포화점 5건은 해커톤 mock 데이터 규모에 맞춘 실용적 선택이며 YAML에서 조정한다.

### 5.8 Divergence Severity

```
gap = |n_A − n_B|                      두 신호 모두 -100~+100 표준화
severity = 100 · tanh(gap / 80) · persistence_mult · materiality

persistence_mult = min(1.5, 1 + 0.1·(duration_periods − 1))
materiality      = clamp( max(|n_A|, |n_B|) / 50, 0, 1 )

트리거: gap ≥ 40  AND  max(|n_A|,|n_B|) ≥ 30  AND  duration ≥ 2틱
```

**materiality가 왜 필요한가.** `n_A = +3, n_B = −3`이면 gap은 6이고 부호도 반대다. 통계적으로는 divergence지만 실무적으로는 아무 의미가 없다. 둘 다 사실상 0이기 때문이다. 두 신호 중 **적어도 하나는 충분히 커야** 괴리가 의미를 갖는다.

**persistence가 왜 필요한가.** 한 틱짜리 노이즈와 며칠 지속되는 구조적 괴리는 전혀 다른 것이다. 요구 7이 `duration`을 필드로 요구한 이유가 이것이다. 2틱 이상 지속을 트리거 조건으로 둬서 노이즈를 걸러낸다.

### 5.9 Alert Severity

레벨이 아니라 **변화**를 본다 (요구 9).

```
severity = 100 · tanh(|delta_z| / 2.5) · type_weight
delta_z  = z(metric_now − metric_prev)  또는  (current − baseline)/baseline

dedupe_key = (type, subject, severity_band)
cooldown   = 30분 — 같은 키 재발화 시 fire_count만 증가
```

요구 9의 예시(`News Volume: 3H 평균 대비 +280%`)는 `AlertTrigger{metric:"news_volume_3h", current:38, baseline:10, delta_pct:280, threshold:150, window:"3h"}`로 저장된다. 화면에 표시되는 모든 숫자가 구조화되어 남는다.

### 5.10 재현성 보장

모든 `ScoreBreakdown`이 `inputs_hash = sha256(정렬된 k=v)`를 갖는다. 테스트는 다음을 단언한다.

```python
def test_market_state_reproducible():
    result1 = MarketStateEngine(rules).compute(snapshot_fixture)
    result2 = MarketStateEngine(rules).compute(snapshot_fixture)
    assert result1.confidence_breakdown.inputs_hash == result2....inputs_hash
    assert result1.primary_label == "INFLATION_SHOCK"
    assert [r.rule_id for r in ... if r.passed] == [...]   # 발동 룰까지 고정
```

요구 14가 요구한 "어떤 rule에 의해 발생했는지 확인할 수 있어야 한다"를 테스트가 직접 검증한다.

---

## STEP 6. 구현 계획 (파일 단위)

### 6.0 디렉터리 구조

기존 `upbit_trading/`은 손대지 않는다. 신규 패키지를 병렬로 추가한다.

```
marketpulse/
├── config/
│   ├── settings.py              pydantic-settings, 시크릿은 env만
│   ├── instruments.yaml         Instrument 레지스트리
│   ├── themes.yaml              Theme + theme→instrument 매핑
│   ├── factors.yaml             11개 factor 구성과 부호 가중
│   ├── scoring.yaml             모든 weight / threshold
│   ├── state_rules.yaml         MarketState require+support 룰셋
│   ├── divergence_rules.yaml
│   ├── alert_rules.yaml
│   └── relationships.yaml       사전 정의 관계 그래프
├── models/
│   ├── common.py                DataMode, DataMeta, ScoreBreakdown
│   ├── market.py                Instrument, MarketDataPoint, MarketFeature,
│   │                            MarketSnapshot
│   ├── news.py                  RawNewsItem, NewsEvent, AssetImpact, Entity
│   ├── theme.py, state.py, divergence.py, alert.py, relationship.py
│   └── snapshot.py              IntelligenceSnapshot
├── adapters/
│   ├── base.py                  MarketAdapter / NewsAdapter ABC
│   ├── registry.py              mode에 따른 어댑터 선택
│   ├── market/
│   │   ├── mock.py, csv_replay.py
│   │   └── yfinance_adapter.py, fdr_adapter.py, fred_adapter.py   (P4)
│   └── news/
│       ├── mock.py, file.py
│       └── rss.py                                                  (P4)
├── data/mock/
│   ├── scenario_baseline.json
│   ├── scenario_inflation_shock.json
│   ├── scenario_ai_divergence.json
│   └── history/*.parquet        ← z-score용 롤링 히스토리 (중요)
├── engines/
│   ├── features.py              z-score, 수익률, 변동성, RSI, breadth
│   ├── factors.py, market_state.py, sentiment.py, theme.py
│   ├── confirmation.py, divergence.py, relationship.py, alert.py
│   └── orchestrator.py          순수 함수: snapshot → IntelligenceSnapshot
├── ai/
│   ├── client.py                Anthropic client, timeout/retry/서킷브레이커
│   ├── event_extractor.py       LLM structured output
│   ├── rule_extractor.py        키워드 fallback, 항상 동작
│   ├── summarizer.py            narrative (deterministic 입력만)
│   └── validation.py            pydantic 검증 + clamp + 기록
├── storage/
│   ├── repository.py            ABC
│   ├── sqlite_repo.py
│   └── schema.sql
├── api/
│   ├── main.py, deps.py
│   └── routes/snapshot.py, market_state.py, themes.py,
│              divergences.py, alerts.py, impact_map.py, news.py, health.py
├── scheduler/runner.py
├── vendor/
│   ├── indicators.py            technical_indicators.py 이식 (vwap 수정)
│   └── rate_limiter.py          락 밖 대기로 수정 + async 변형
└── cli.py                       python -m marketpulse.cli snapshot --scenario=...

frontend/
├── src/
│   ├── api/client.ts, types.ts  백엔드 스키마와 1:1 (수기 동기화)
│   ├── components/
│   │   ├── MarketStateHeader.tsx    [TOP]
│   │   ├── ThemeHeatmap.tsx         [THEME HEATMAP]
│   │   ├── WhatsMoving.tsx          [WHAT'S MOVING]
│   │   ├── WhyPanel.tsx             [WHY]
│   │   ├── ConfirmationMatrix.tsx   [FLOW & PRICE CONFIRMATION]
│   │   ├── DivergencePanel.tsx      [DIVERGENCE]
│   │   ├── ImpactMap.tsx            [IMPACT MAP]
│   │   ├── AlertTimeline.tsx        [ALERT / TIMELINE]
│   │   ├── ScoreTooltip.tsx         ScoreBreakdown 렌더 — 설명가능성 UI
│   │   └── DataModeBadge.tsx        LIVE/DELAYED/MOCK + freshness
│   ├── layout/DashboardGrid.tsx
│   └── theme/tokens.ts
├── vite.config.ts, tailwind.config.ts
tests/
docs/
pyproject.toml
requirements.txt
```

컴포넌트 배치는 요구 10의 화면 순서를 그대로 따른다.

### 6.1 P0 — Dashboard skeleton / Schema / Mock pipeline

**목표:** `GET /api/v1/snapshot`이 mock 데이터로 완전한 페이로드를 반환하고, 대시보드가 그것을 그린다.

| 파일 | 내용 |
|---|---|
| `pyproject.toml`, `requirements.txt` | 의존성 선언. **기존 리포지토리에 없던 것을 처음 만든다** |
| `pytest.ini` | `--ignore=upbit_trading/test_sql_load.py` **필수** (STEP 1-6 4번 참조) |
| `models/*.py` 전부 | STEP 4의 7개 스키마 + 공통 타입 |
| `config/settings.py` | pydantic-settings. `MARKETPULSE_DATA_MODE`, `ANTHROPIC_API_KEY` 등 |
| `config/instruments.yaml` | 요구 3의 6개 카테고리 초기 30여 종목 |
| `config/themes.yaml` | 요구 5의 12개 테마 + instrument 매핑 |
| `adapters/base.py`, `registry.py` | ABC + mode 기반 선택 |
| `adapters/market/mock.py`, `news/mock.py` | |
| `data/mock/scenario_baseline.json` + `history/` | **롤링 히스토리 60틱 포함** |
| `engines/features.py` | z-score, 수익률, 변동성 |
| `engines/orchestrator.py` | 스텁 (이후 P마다 채운다) |
| `vendor/indicators.py` | `technical_indicators.py` 이식, `vwap` 세션 리셋 수정 |
| `api/main.py`, `routes/snapshot.py`, `routes/health.py` | |
| `cli.py` | **텍스트 출력 데모 경로 — 프론트 장애 대비책** |
| frontend 부트스트랩 + `DashboardGrid` + `MarketStateHeader` + `ThemeHeatmap`(더미) + `DataModeBadge` | |
| `tests/test_schemas.py`, `test_mock_adapter.py`, `test_features.py` | |

**완료 기준:** `pytest` 통과 / `uvicorn` 기동 / 대시보드에 mock 데이터 표시 / 모드 배지에 "MOCK" 노출 / `python -m marketpulse.cli snapshot`이 텍스트 요약 출력.

**주의 사항:** `data/mock/history/`를 P0에서 빼먹으면 P1에서 z-score를 계산할 수 없어 전부 막힌다. 60틱 히스토리는 P0의 필수 산출물이다.

### 6.2 P1 — Market State / Theme Score / Sentiment / Heatmap

| 파일 | 내용 |
|---|---|
| `config/factors.yaml`, `state_rules.yaml`, `scoring.yaml` | STEP 5의 모든 수치 |
| `engines/factors.py` | 11개 factor |
| `engines/market_state.py` | require+support 룰 평가, hypotheses 순위 |
| `engines/sentiment.py` | 극성 사전 baseline + 시간감쇠 집계 |
| `engines/theme.py` | ThemeScore + Confidence |
| `ai/rule_extractor.py` | 키워드 기반 — **LLM 없이 파이프라인 완주** |
| `data/mock/scenario_inflation_shock.json` | 요구 14 검증 케이스 |
| frontend: `ThemeHeatmap` 실데이터, `ScoreTooltip` | |
| `tests/test_factors.py`, `test_market_state.py`, `test_theme_score.py`, `test_sentiment.py` | |

**완료 기준:** 요구 14의 `Oil +2σ / Rates +1.5σ / VIX +1.5σ / Equity −1.2σ → Inflation Shock` 케이스가 테스트로 통과하고, 응답에 발동 룰 목록이 포함된다.

### 6.3 P2 — Confirmation / Divergence / Alert

| 파일 | 내용 |
|---|---|
| `engines/confirmation.py` | 기대 반응표 대조 |
| `engines/divergence.py` | 7개 divergence 타입 |
| `engines/alert.py` | 변화 기반 + dedupe + cooldown |
| `config/divergence_rules.yaml`, `alert_rules.yaml` | |
| `storage/repository.py`, `sqlite_repo.py`, `schema.sql` | **직전 스냅샷 비교에 필요 — 여기서 처음 필요해진다** |
| `scheduler/runner.py` | 주기 실행 |
| `api/routes/divergences.py`, `alerts.py` | |
| frontend: `ConfirmationMatrix`, `DivergencePanel`, `AlertTimeline`, `WhatsMoving` | |
| `data/mock/scenario_ai_divergence.json` | 요구 7 예시 재현 |
| `tests/test_confirmation.py`, `test_divergence.py`, `test_alert.py` | |

**완료 기준:** AI 테마 divergence 시나리오가 자동 탐지되어 패널에 뜨고, 같은 알림이 cooldown 내에 중복 발화하지 않는다.

### 6.4 P3 — Impact Map / LLM Extraction / AI Summary

| 파일 | 내용 |
|---|---|
| `config/relationships.yaml` | 사전 정의 그래프 (요구 8의 중동→유가→인플레→금리→성장주 포함) |
| `engines/relationship.py` | 그래프 순회, depth 제한 |
| `ai/client.py` | timeout 8s, retry, 서킷브레이커 (연속 3회 실패 → 5분 차단) |
| `ai/event_extractor.py` | LLM structured output |
| `ai/validation.py` | pydantic 검증 + clamp + `clamped_fields` 기록 |
| `ai/summarizer.py` | deterministic 결과만 입력, 숫자 검증 후처리 |
| `api/routes/impact_map.py`, `news.py` | |
| frontend: `ImpactMap`(predefined 실선 / llm_proposed 점선), `WhyPanel` | |
| `tests/test_relationship.py`, `test_llm_validation.py`(고정 fixture, 네트워크 없음), `test_llm_fallback.py` | |

**완료 기준:** `ANTHROPIC_API_KEY`를 지워도 대시보드 전체가 정상 동작하고 narrative만 템플릿으로 대체된다. 이것을 테스트로 고정한다.

### 6.5 P4 — Real Adapter / History / Backtest

| 파일 | 내용 |
|---|---|
| `adapters/market/yfinance_adapter.py`, `fdr_adapter.py`, `fred_adapter.py` | |
| `adapters/market/csv_replay.py` | **로컬 CSV 리플레이 — 현 환경 네트워크 차단 대응** |
| `adapters/news/rss.py` | |
| `analysis/backtest.py` | `backtester.py::_calculate_metrics` 이식 |
| API WebSocket | |

**완료 기준:** `MARKETPULSE_DATA_MODE=LIVE` 환경변수 하나로 전환된다. 엔진 코드는 한 줄도 바뀌지 않는다.

### 6.6 커밋 단위

P당 3~5커밋을 권한다. 스키마 → 엔진 → API → 프론트 → 테스트 순. 각 P 완료 시점에 `pytest`가 통과하는 상태를 유지한다.

---

## STEP 7. Risk / Gap 분석

### 7.1 데이터 확보 — 최상위 리스크

**현 컨테이너에서 마켓데이터 API가 전면 차단되어 있다.** 추정이 아니라 실측 결과다(STEP 1.3). Yahoo Finance, stooq, FRED, Upbit 모두 조직 네트워크 정책으로 CONNECT가 거부된다.

대응:
- MOCK을 1급 시민으로 설계한다. 기본 모드를 MOCK으로 두고 LIVE는 명시적 opt-in이다.
- `csv_replay` 어댑터를 만든다. 사용자가 로컬 PC에서 받은 CSV를 `data/replay/`에 넣으면 LIVE에 준하는 데모가 가능하다. 이것이 네트워크 제약을 우회하는 가장 현실적인 경로다.
- LIVE 어댑터는 작성하되 이 환경에서 통합 테스트가 불가하므로, 고정 응답 fixture 기반 **계약 테스트**로 검증한다.

**Gap — Flow 데이터.** 외국인/기관 순매수는 무료 API가 사실상 없다. KRX 일별 CSV 수동 적재 또는 mock 고정 중 하나를 택해야 한다. 요구 5의 Theme Flow Momentum과 요구 7의 "Price↑ / Flow↓" divergence가 여기에 의존하므로, **이 항목만큼은 mock이어도 시나리오가 설득력 있게 구성되어야 한다.**

### 7.2 실시간성

무료 소스는 대체로 15~20분 지연이다.

대응: DELAYED를 **명시적 상태**로 두고 `freshness_sec`를 UI에 항상 표시한다. "실시간"이라고 주장하지 않는다. 데이터의 나이를 정직하게 드러내는 것이 자산운용 현업에서는 오히려 신뢰 요소다.

### 7.3 LLM Hallucination

가장 위험한 시나리오는 LLM이 없는 숫자를 만들거나 존재하지 않는 시장 관계를 사실처럼 반환하는 것이다.

4중 방어:
1. **LLM은 점수를 산출하지 않는다.** 모든 숫자는 정량 레이어에서 나온다. 이것이 요구 2의 핵심 원칙이자 가장 강력한 방어다.
2. **summarizer 입력 고정.** 프롬프트에 deterministic 결과만 주입하고 "주어진 수치 외 인용 금지"를 제약으로 건다. 출력 후 숫자 토큰이 입력에 실제로 존재하는지 후검증한다.
3. **extractor 출력 검증.** pydantic 스키마 검증 + 범위 clamp. 실패 시 `rule_extractor`로 폴백하고 `validation.errors`에 기록한다.
4. **LLM 제안 관계 격리.** `origin="llm_proposed"`, `status="candidate"`로 저장하고 UI에서 점선·다른 색으로 그린다. 사전 정의 관계와 섞이지 않는다.

### 7.4 Latency

LLM 호출이 파이프라인을 블로킹하면 대시보드가 멈춘다.

대응: LLM을 파이프라인 밖의 비동기 enrichment로 둔다. 스냅샷은 LLM 없이 **먼저 생성·반환**되고, narrative는 준비되면 다음 폴링에 채워진다. 타임아웃 8초, 서킷브레이커는 연속 3회 실패 시 5분 차단. 뉴스는 배치 처리하고 동일 기사는 본문 해시로 캐싱한다.

### 7.5 비용

기사당 LLM 호출은 건수에 선형 비례한다.

대응:
- 본문 해시 캐시로 중복 기사 제거
- 추출은 저비용 모델, 요약만 상위 모델
- 배치 처리 (10건/요청)
- prompt caching으로 스키마·지침 부분 재사용
- `MARKETPULSE_LLM_ENABLED=false`로 전면 차단 가능

구체적인 모델 선택과 단가는 구현 착수 시점의 공개 가격표를 확인해 확정한다. 기억에 의존해 숫자를 적지 않는다.

### 7.6 Scoring Reliability

가중치와 임계값이 자의적이라는 것이 이 설계의 가장 정직한 약점이다.

대응:
- 전부 YAML로 외부화해 코드 수정 없이 조정 가능하게 한다
- 모든 점수에 contributions를 동봉해 즉시 검증 가능하게 한다
- `inputs_hash`로 재현성을 테스트로 고정한다
- 골든 시나리오 테스트로 회귀를 막는다
- **문서와 UI에 "이 가중치는 매크로 상식에 기반한 초기값이며 통계적으로 추정된 값이 아니다"를 명시한다.** 요구 15-11이 요구하는 태도다. 불확실한 관계를 확정 사실처럼 제시하지 않는다.

**Gap — 히스토리 길이.** z-score의 60틱 롤링 윈도우를 채우려면 최소 60개 관측치가 필요하다. mock 시나리오에 히스토리를 포함시켜야 한다. **P0에서 이것을 놓치면 P1 전체가 막힌다.** 6.1에 명시했다.

### 7.7 Demo Risk

| 리스크 | 대응 |
|---|---|
| 데모 중 외부 API 실패 | 기본 모드 MOCK, LIVE는 명시적 opt-in |
| 프론트엔드 빌드 실패 | P0에서 `/api/v1/snapshot` JSON과 **CLI 텍스트 출력**을 먼저 완성. 최악의 경우 CLI로 데모 |
| LLM 키 만료 / 한도 초과 | 7.3, 7.4의 폴백. narrative만 템플릿으로 대체되고 나머지는 그대로 동작 |
| 시연 결과가 매번 달라짐 | `?scenario=inflation_shock` 쿼리로 결정론적 재생. 우연에 의존하지 않는다 |
| 시간 부족 | P0~P2가 이미 "뉴스+마켓데이터 결합 → divergence 탐지"라는 핵심 차별점을 담는다. P3는 있으면 좋은 것 |
| 기존 리포지토리의 `test_sql_load.py` | pytest 도입 시 **import만으로 DB 생성과 외부 API 호출이 발생한다.** `pytest.ini`에서 반드시 제외 |

### 7.8 요구사항 자체의 Gap

구현 전에 결정이 필요한 항목들이다.

1. **Novelty score 계산 방법이 요구사항에 정의되어 있지 않다.** 제안: 제목 토큰의 자카드 유사도 또는 임베딩으로 최근 24시간 기사와 비교해 최대 유사도의 역수를 쓴다. 임베딩은 비용이 붙으므로 P3 이후로 미루고, P1~P2는 자카드로 간다.
2. **타임존.** KRX·US·유럽 시장이 섞인다. 내부는 전부 UTC로 통일하고 표시만 KST로 한다. instrument별 `as_of` 정의를 명확히 해야 한다.
3. **시장 휴장.** 한국 휴장 중 미국 지표만 움직이면 KoreaFlow와 KoreaBreadth factor가 왜곡된다. `Instrument.calendar` 필드를 두고 휴장 시 해당 factor를 `data_quality="INSUFFICIENT"`로 표시하고 confidence에서 제외한다.
4. **Theme 목록의 고정성.** 요구 5의 12개 테마가 초기값인지 확장 가능해야 하는지 불명확하다. YAML로 두어 런타임 추가는 가능하게 하되, 자동 테마 발견은 범위 밖으로 둔다.

---

## 승인 요청 사항

구현 착수 전에 다음 4개 결정을 확인받고자 한다.

1. **기존 `upbit_trading/`을 건드리지 않고 신규 `marketpulse/` 패키지를 병렬 추가하는 방향**이 맞는지. 기존 코드는 암호화폐 자동매매 실행 도메인이라 이번 요구와 겹치는 부분이 지표 계산과 레이트리밋 정도다.
2. **프론트엔드를 React + Vite로 가는 것**이 맞는지. Streamlit이 더 빠르지만 요구 10의 정보 밀도·즉시성을 만족하기 어렵다고 판단했다.
3. **현 환경의 네트워크 제약**(외부 마켓데이터 API 전면 차단)을 감안할 때, P4의 LIVE 어댑터를 계약 테스트로만 검증하고 실제 연동은 로컬 환경에 맡기는 것이 맞는지. 대안으로 `csv_replay` 어댑터를 P2로 앞당길 수 있다.
4. **STEP 5의 초기 가중치**를 그대로 시작할지, 아니면 현업 감각에 맞춰 조정한 뒤 시작할지. YAML이라 언제든 바꿀 수 있지만 초기값이 데모 결과를 좌우한다.

승인 후 P0부터 순차적으로 구현한다.

---

## 구현 기록

### P0 — 완료 (커밋 d6aeaf3 외)

설계서 STEP 6.1 의 완료 기준을 모두 충족했다. `pytest` 통과, `uvicorn` 기동,
대시보드에 MOCK 데이터 표시, 모드 배지 노출, CLI 텍스트 요약 출력.

**설계 대비 변경점 두 가지**

1. **프론트엔드에서 TailwindCSS 를 쓰지 않았다.** 토큰 기반 CSS 로 갔다.
   이유는 두 가지다. 고밀도 금융 표에 필요한 것(등폭 숫자, 헤어라인 괘선,
   한국 관례의 상승 적색·하락 청색 체계)을 유틸리티 클래스로 쓰면 JSX 가
   읽을 수 없게 길어진다. 그리고 빌드 의존성이 하나 줄면 데모가 죽을 경로도
   하나 준다(STEP 7.7). Recharts 도 그릴 시계열이 생기는 P1/P2 로 미뤘다.
   React + TypeScript + Vite 는 설계대로다.

2. **시나리오에 `quiet_z` 를 추가했다.** 설계에 없던 항목이다. 47개 종목을
   난수로 생성하면 순전한 우연으로도 |z| 2.5 가 나와, 시나리오가 말하려는
   이야기를 노이즈가 덮는다. 충격을 선언하지 않은 종목의 마지막 변화를
   tanh 로 연성 압축해 선언한 충격이 서사를 이끌게 했다. 히스토리는 건드리지
   않고 마지막 한 점만 조정한다. 하드 컷이 아니라 연성 압축인 이유는, 하드
   컷을 쓰면 여러 종목이 정확히 같은 z 에 뭉쳐 한눈에 인공물로 보이기
   때문이다.

**설계서가 예측한 대로 확인된 것**

- z-score 의 rolling window 를 채우려면 히스토리가 필요하다는 STEP 7.6 의
  Gap 지적이 정확했다. 시나리오의 `bars: 180` 이 P0 의 필수 산출물이었다.
- `upbit_trading/test_sql_load.py` 는 실제로 위험하다. 루트 `conftest.py` 의
  `collect_ignore_glob` 으로 막았고, 그 가드가 제거되면 깨지는 회귀 테스트를
  함께 두었다.

**함께 처리한 것 (P0 범위 밖이지만 같은 파일을 만진 김에)**

- README 가 "`upbit_trading/config.py` 에서 업비트 API 키를 설정하라" 고
  안내하던 문장을 고쳤다. 그대로 따르면 실거래 가능한 시크릿이 git 추적
  대상 파일에 들어간다. 코드는 이미 환경변수에서 읽고 있으므로 그 안내는
  위험할 뿐 아니라 사실과도 달랐다.
- `.env.example` 에 `config.py` 가 실제로 읽는 변수 12개를 모두 채웠다.
  기존에는 2개만 있었다.

**P1 착수 전 확인 사항**

설계서 STEP 5.2 의 factor 구성 중 `US_HY_OAS`, `MOVE`, `BE10Y` 는
instruments.yaml 에 등록되어 있으나 실데이터 확보 난이도가 높다(STEP 7.1).
P1 에서 factor 를 계산할 때 이들이 빠져도 가중치 재정규화로 동작하는지
테스트로 고정한다.

### P1 — 완료

STEP 6.2 의 완료 기준을 충족했다. 요구 14 의 검증 케이스가 테스트로 통과하고,
응답에 발동 룰 목록이 포함된다.

**요구 14 검증 케이스 재현**

`scenario_inflation_shock` 이 Oil +2.1σ / Rates +1.6σ / VIX +1.5σ / Equity −1.2σ 를
선언하고, 엔진이 다음을 산출한다.

```
INFLATION_SHOCK   1.000   ✓ inf_core(Inflation>=1.0, 관측 +1.70)
                          ✓ inf_rates ✓ inf_risk ✓ inf_vol ✓ inf_growth
RISK_OFF          0.875   ✓ ro_core ✓ ro_vol ✓ ro_credit ✓ ro_usd
                          · ro_flow  (KoreaFlow -0.20, 조건 <= -0.3 미달)
GEOPOLITICAL_RISK 0.775
POLICY_DRIVEN     0.750

primary = INFLATION_SHOCK, secondary = RISK_OFF, confidence 65%
```

두 판정의 순위를 가른 것은 **국내 수급 조건 하나**다. `ro_flow` 가 실패하지
않았다면 두 라벨이 동점이 되고 separation 이 0 이 되어 confidence 가 더
낮아졌을 것이다. 이 한 줄이 테스트로 고정되어 있다.

**설계 대비 변경점**

1. **Confirmation 엔진을 P1 로 당겼다.** 설계서는 P2 에 두었으나 STEP 5.4 의
   Confidence 가 Confirmation 을 구성요소로 쓴다. 둘을 떼면 P1 의 confidence
   가 불완전해진다. P2 는 이것을 테마와 divergence 로 확장한다.

2. **`Theme.sentiment_polarity` 를 추가했다.** 설계에 없던 항목이다. 요구 5 의
   예시 히트맵에서 "Geopolitical Risk +88" 은 지정학 리스크가 **높다**는 뜻이다.
   그런데 사전은 "긴장 고조" 를 부정 극성으로 읽는다. 테마의 키워드 자체가
   부정 극성 단어인 경우(전쟁·분쟁·긴장·제재)에만 부호를 뒤집도록 했다.
   Inflation 의 키워드(물가, CPI)는 중립 명사라 뒤집으면 오히려 틀린다.

3. **`NewsEvent.theme_sentiment` 를 추가했다.** 기사 하나가 여러 테마를
   건드릴 때 기사 전체 감성을 모든 테마에 그대로 붙이면 틀린다.
   "정유주 강세, 항공주 약세" 는 Energy 에 +, Airlines 에 −여야 한다. 문장과
   한국어 대조 접속사(반면/한편), 그리고 헤드라인의 말줄임표를 경계로 잘라
   테마 키워드가 있는 절만 채점한다.

4. **`news_volume` 을 횡단면 z 로 계산한다.** 설계의 정의는 시계열 z(최근
   3시간 vs 직전 7일 같은 시간대)다. 뉴스 히스토리가 없는 현 단계에서는
   쓸 수 없어, "이 테마가 지금 다른 테마들보다 유별나게 많이 언급되는가" 로
   대체했다. 다른 지표이므로 method 문자열에 그 사실을 남겼고, 히스토리가
   붙는 P4 에서 교체한다.

5. **ThemeState 의 구성요소를 `float | None` 으로 바꿨다.** 처음에는 미측정을
   0.0 으로 채웠는데, 이는 설계서 STEP 5.0 의 원칙 3 을 스스로 어긴 것이었다.
   수급 자산을 매핑하지 않은 테마의 Flow 가 "+0" 으로 보이면 "측정했더니
   중립" 으로 읽힌다. 화면에서도 `–` 로 구분한다.

6. **데이터 품질 판정에서 구조적 부재와 실제 결손을 구분한다.** Defense
   테마에 수급 자산을 매핑하지 않은 것은 데이터 결손이 아니라 모델링
   선택이다. 그것까지 PARTIAL 로 표시하면 진짜 결손이 묻힌다.

**설계대로 유지된 것**

- LLM 을 한 번도 호출하지 않는다. `llm_status` 는 `disabled` 이고 narrative 는
  템플릿에서 나온다. 요구 6 의 "유가는 강하게 상승했으나 USD 반응은
  제한적" 같은 문장이 `ConfirmationResult.note` 에서 자동 생성된다.
- 표현식 평가에 `eval` 을 쓰지 않는다. 설정 파일이 임의 코드를 실행할 수
  있으면 그것은 설정이 아니라 코드다. 허용 문법만 정규식으로 파싱한다.
- 평가 불가를 통과로 처리하지 않는다. 그렇게 하면 데이터가 없을수록 라벨이
  잘 붙는 시스템이 된다.

**P2 착수 전 확인 사항**

`inflation_shock` 시나리오에서 Semiconductor 테마의 news_sentiment(−39)와
price_momentum(−65)은 같은 방향이지만, flow_momentum(−10)은 상대적으로
약하다. P2 의 Divergence Engine 이 이런 격차를 어느 임계에서 잡을지는
`divergence_rules.yaml` 에서 정한다. 설계서 STEP 5.8 의 materiality 항이
이 경우를 걸러내는지 테스트로 확인해야 한다.

### P2 — 완료

STEP 6.3 의 완료 기준을 충족했다. AI 테마 divergence 시나리오가 자동
탐지되어 패널에 뜨고, 같은 알림이 cooldown 내에 중복 발화하지 않는다.

**요구 7 예시 재현**

`scenario_ai_divergence` 에서 AI 테마의 뉴스 +37 / 가격 +61 / 수급 −34 가
나오고, DivergenceEngine 이 두 건을 잡는다.

```
CRITICAL 100  PRICE_VS_FLOW  ai   가격 +61 vs 수급 -34
HIGH      67  NEWS_VS_FLOW   ai   뉴스 +37 vs 수급 -34
```

요구 7 이 적은 "AI 관련 뉴스와 가격은 긍정적이나 외국인 수급이 동반되지
않고 있음" 이 템플릿으로 생성된다. LLM 을 쓰지 않는다.

**설계에 없던 판정 조건을 추가했다 — 가장 중요한 수정**

설계서 STEP 5.8 은 severity 를 gap 으로만 정의했다. 그대로 구현하니
**같은 방향으로 크기만 다른 것까지 괴리로 잡혔다.** 뉴스 톤 +6 과 가격 +66
은 격차가 60 이지만 둘 다 같은 방향인데, 여기에 "내러티브가 가격으로
확인되지 않는다" 는 문장이 붙었다. 틀린 말이다.

요구 7 이 든 예시를 다시 보면 전부 두 형태 중 하나다.

| 형태 | 예시 |
|---|---|
| **opposing** 두 신호가 반대 방향 | News ↑ / Price ↓, Price ↑ / Flow ↓ |
| **unresponsive** 한쪽이 무반응 | Risk Event ↑ / VIX 반응 없음 |

그래서 `qualifies()` 를 두어 이 둘 중 하나에 해당할 때만 괴리로 인정한다.
설명 템플릿도 두 형태로 나눴다. 무반응을 "방향이 엇갈린다" 고 쓰면 안 된다.

**그 밖의 설계 대비 변경점**

1. **알림에 보존 창(`retention_minutes`)을 두었다.** 괴리 발생 같은 사건은
   다음 틱에 조건이 재생성되지 않아, 그대로 두면 한 틱 만에 화면에서
   사라진다. 타임라인이 성립하지 않는다. 다만 재생성되지 않았다고 해서
   해소된 것도 아니다. 괴리가 4틱째 이어지는데 알림이 "해소" 로 찍히면
   화면이 거짓말을 한다. `live_subjects` 로 조건 지속 여부를 보고 ONGOING
   과 RESOLVED 를 가른다. 이를 위해 `Alert.subject` 를 추가했다.

2. **`engines/korean.py` 를 추가했다.** 설명 템플릿이 "은(는)" 같은 이중
   표기를 그대로 내보내면 현업 화면에서 조악하게 읽힌다. 받침 유무로 조사를
   고른다. 숫자도 처리한다 — "+66으로", "+65로" 가 각각 맞다.

3. **설명 템플릿에 `{active}` / `{quiet}` 치환자를 두었다.** 크기 기준이다.
   무반응 문장이 "가격은 -8로 움직였으나 수급은 +39에 그쳤다" 처럼 큰 쪽과
   작은 쪽을 뒤바꿔 말하는 것을 막는다.

4. **뉴스 기반 괴리에 `min_events` 를 두었다.** 기사 1건으로 "내러티브가
   가격과 어긋난다" 고 말하는 것은 한 기자의 문장과 시장을 비교하는 것이다.

5. **스케줄러를 라이브러리 없이 만들었다.** APScheduler 가 필요한 지점은
   '일정 간격으로 한 함수를 부르고 SIGINT 에 깨끗이 멈추는 것' 뿐이었다.

**구현 중 발견한 버그**

API 의 스냅샷 서비스가 **히스토리를 캐시에 종속시켜** 두어, 엔진이 보는
'직전 스냅샷' 이 한 틱 밀렸다. 그 결과 divergence 가 매 틱 나타났다
사라지기를 반복했다(`[0, 6, 0, 6, ...]`). 화면에서 먼저 발견했고, 회귀
테스트(`TestHistoryContinuity`)로 고정했다. 히스토리는 캐시와 독립이어야
한다 — 캐시는 TTL 최적화일 뿐이고 비워도 시계열이 끊기면 안 된다.

**P3 착수 전 확인 사항**

`baseline` 시나리오에서도 괴리가 2건 잡힌다(Shareholder Return, Consumer의
가격 ↔ 수급). 평시 시나리오에 괴리가 있는 것이 이상하지는 않지만, 임계값이
느슨한 것인지 시나리오의 수급 난수가 큰 것인지는 실데이터가 붙어야 판단할
수 있다. `scoring.yaml` 의 `divergence.trigger` 가 재검토 대상이다.

### P3 — 완료

STEP 6.4 의 완료 기준을 충족했다. **`ANTHROPIC_API_KEY` 를 지우고
`MARKETPULSE_LLM_ENABLED=true` 로 켜도 대시보드 전체가 정상 동작하고
narrative 만 템플릿으로 대체된다.** 이것을
`tests/test_llm.py::TestGracefulDegradation` 에 고정했다.

**요구 8 확산 경로 재현**

`relationships.yaml` 에 사전 정의 관계 46개를 넣었다. 요구 8 이 적은
"유가 급등 → 에너지/항공 → 인플레이션 → 금리 → 성장주" 가 그대로 이어진다.

```
사건          테마        매크로        업종        자산
event ──┬─ Oil ──┬── BRENT / WTI
        │        ├── 에너지 ─────────────────── XLE
        │        ├── 항공 (−) ────────────────── JETS
        │        └── 인플레이션 ── 금리 ─┬─ 성장주 (−) ── NDX
        ├─ Inflation ─────────────────────┼─ 금융 ───────── XLF
        └─ USD ── 달러                     └─ 유틸리티 (−) ─ XLU
```

`inflation_shock` 에서 깊이 5, 노드 28, 관계 28 로 렌더된다.

**설계 대비 변경점**

1. **`max_depth` 를 4 → 5 로 올렸다.** 요구 8 의 사슬은 사건까지 세면 6단계다.
   4 로 자르면 마지막 자산(NDX)이 잘려서, 요구가 말한 확산의 끝을 못 보여준다.

2. **테마 → 매크로 다리 간선을 추가했다.** 처음에는 테마와 매크로 factor 를
   별개 평면으로 두었는데, 그러면 `theme:oil` 에서 `macro:Inflation` 으로
   건너갈 방법이 없어 사슬이 테마에서 끊겼다. `theme:inflation→macro:Inflation`
   같은 다리를 명시했다.

3. **모든 간선에 `origin` 을 붙였다.** 지금은 전부 `predefined` 다. LLM 이
   제안한 관계가 섞이면 화면에서 **점선**으로 그린다. 개발 규칙 11 —
   불확실한 시장 관계를 deterministic fact 처럼 보여주지 않는다 — 을 UI
   차원에서 지킨다. 범례가 어느 쪽인지 항상 명시한다.

4. **사건이 없으면 테마를 뿌리로 삼는다.** 뉴스가 테마를 못 물면 지도가
   통째로 빈다. 빈 패널보다 "무엇에서 출발한 경로인지" 를 낮춰서라도 보여주는
   편이 낫다. 다만 뿌리가 테마임을 화면에 그대로 쓴다.

**LLM 계층 — 세 겹의 안전장치**

STEP 7.3 이 지목한 hallucination 리스크에 대해, 신뢰하지 않는 것을 전제로
설계했다.

| 장치 | 파일 | 동작 |
|---|---|---|
| 회로 차단기 | `ai/client.py` | 연속 3회 실패 시 5분 차단. **인증 실패는 영구 차단** — 키가 없는데 매 틱 재시도하는 것은 지연만 늘린다 |
| 스키마 검증 | `ai/validation.py` | 레지스트리에 없는 테마·종목 ID 는 버린다. 보정한 필드를 전부 `clamped_fields` 에 남긴다 |
| 숫자 검증 | `ai/summarizer.py` | 요약문의 모든 숫자 토큰이 결정론적 facts 에 실재해야 한다. 하나라도 지어내면 통째로 템플릿으로 되돌리고 경고를 남긴다 |

숫자 검증이 가장 중요하다. 운용자는 화면의 숫자를 믿고 판단한다. 덜 매끄러운
문장이 지어낸 숫자보다 낫다.

**구현 중 발견한 문제**

1. **자격증명이 없을 때 SDK 가 `AuthenticationError` 가 아니라 `TypeError` 를
   던진다.** 클라이언트 생성 시점에 터지기 때문이다. 그대로 두면 "알 수 없는
   오류" 로 분류되어 회로가 영구 차단되지 않고 매 틱 재시도했다. `TypeError`
   중 인증 관련 메시지를 영구 인증 실패로 분류하고, 사용자가 조치할 수 있는
   문구를 남긴다.

2. **회로 차단기가 틱을 넘겨 살아남지 못했다.** 매 호출마다 클라이언트를 새로
   만들고 있었으니 실패 카운터가 늘 0이었다. `build_client()` 를 메모이즈해
   차단 상태가 유지되게 했다. 실측으로 확인했다 — 1틱 0.81초(경고 1건),
   2·3틱 0.07초(무음), 정량 출력은 세 틱 모두 동일.

3. **실패 사유가 1틱 뒤 화면에서 사라졌다.** 차단된 뒤로는 호출 자체를 안 하니
   새 경고가 생기지 않는다. 화면은 "LLM 정상" 처럼 보인다. `llm_status` 가
   `failed` 인 동안 경고를 매 틱 다시 붙인다.

**P4 로 넘기는 것**

- 실데이터 어댑터 전체. 사용자가 네트워크 문제를 해결한 뒤 착수한다.
- `csv_replay` 어댑터의 시점 정렬.
- **승인 요청 ④ 스코어링 가중치 검토가 P0~P3 내내 미결로 누적됐다.**
  현재 값은 전부 매크로 상식 기반 초기 제안값이며 통계적 추정치가 아니다.
  실데이터가 붙는 시점에 `scoring.yaml` 전체가 재검토 대상이다.

### Impact Map 레이아웃 교체 — B(전파 단계) + G(점도표)

P3 의 지도는 노드를 **종류**별 열에 세웠다. 아홉 가지 레이아웃 후보를 실제
데이터로 그려 비교한 결과 그 배치가 네 가지를 못 보여준다는 것이 드러났다.

| | 현행의 문제 |
|---|---|
| 1 | 열 안 순서가 payload 등장 순서라 선이 서로를 가로지른다. 경로를 못 따라간다 |
| 2 | 열이 종류라 높이가 안 맞는다. 사건 1행 대 자산 13행 |
| 3 | 실제로 움직였는지가 없다. **가설만 그린다** |
| 4 | 관계 부호와 가격 방향이 같은 색 체계를 쓴다 |

**바꾼 것**

열을 종류에서 **사건으로부터의 전파 단계**로 바꿨다. 열 분포가 1·3·6·7·7·4
로 고르게 펴지고, `macro:USD → theme:china` 처럼 뒤로 가는 관계가 사라진다.
왼쪽에서 오른쪽이 곧 인과 순서다.

그리고 **노드 면색을 실측 z 로 칠했다.** 이것이 가장 큰 변화다. 관계
그래프만 그리면 지도는 가설만 보여주는데, 이 제품의 1번 질문은 "뉴스의
내러티브와 실제 가격·수급이 일치하는가" 다. 예상 부호 옆에 실측을 두어야
지도가 그 질문에 답한다.

색 체계는 세 채널로 분리했다. 섞으면 선의 적/청이 "역방향 관계" 인지
"가격 하락" 인지 구분되지 않는다.

| 채널 | 표현 |
|---|---|
| 가격 방향 | 노드 면색 (한국 관례: 상승 적, 하락 청) |
| 관계 부호 | 선 색이 아니라 ⊖ 표식 |
| 관계 출처 | 실선(사전 정의) / 점선(LLM 제안) |

**예상 부호를 어떻게 정하는가**

대표 경로 하나의 관계 부호 곱이다. 대표 경로는 한 단계 앞 노드에서
들어오는 관계 중 `strength` 가 가장 큰 것으로 고른다. 임의로 고르지 않는
이유는 결정론이 필요해서다 — 같은 시나리오는 같은 화면이어야 한다(요구 14).
`via_edge_id` 로 그 근거를 추적할 수 있다(요구 15-6).

**다른 경로가 반대 부호를 주면 판정하지 않는다.** `inflation_shock` 의
`macro:Inflation` 이 그렇다. 유가에서는 +, 물가 테마에서는 − 로 들어온다.
이때 `sign_conflict` 를 세우고 reaction 을 `unknown` 으로 둔다. 관계가
상충하는 것이지 시장이 틀린 것이 아니다(개발 규칙 11).

`|z| < 0.5` 는 `muted` 다. 0.3σ 짜리 움직임으로 내러티브의 옳고 그름을
말하면 잡음을 신호로 읽는 것이다. 임계값은 `scoring.yaml` 에 있다.

**실측을 어디까지 올리는가**

종목과 매크로 factor 만이다. 테마와 업종은 비운다. 테마 점수는 뉴스·가격·
수급을 섞은 합성값이라 그것을 '실측 가격 반응' 칸에 넣으면 내러티브를
내러티브로 검증하게 된다. 비워 두는 편이 정직하다 — 0 으로 채우지 않는다.

**같이 붙인 것**

- **단계별 실측 반응(점도표)** — 지도는 경로를, 점도표는 크기를 보여준다.
  단계가 깊어질수록 충격이 줄어드는지 오히려 커지는지가 한 그림에 보인다.
  넓은 화면에서는 지도 옆에, 좁으면 아래로 접힌다.
- **목록 보기** — 같은 데이터의 들여쓰기 트리. 좁은 폭에서 그래프는 접히지
  않지만 목록은 접힌다. 복사해서 메모에 붙여넣을 수도 있다.
- **경로 강조** — 노드에 마우스를 올리면 사건까지의 대표 경로만 남는다.
  교차가 남아 있어도 한 경로는 따라갈 수 있다.

**검토 중 발견한 별건 — 테마 방향과 감성 톤이 한 필드에 뭉개져 있다**

`build_impact_maps` 는 `event → theme` 관계의 방향을 테마 감성의 부호로
정한다. 기사 "원달러 환율 장중 1380원대… 수입 물가 부담 확대 우려" 에서
`부담`·`우려` 가 감성을 음수로 만들고, 그 값이 그대로 `물가가 내린다` 는
뜻으로 쓰인다. 그 기사는 **물가가 오른다**는 뜻이다.

그래서 이 지도에서 `US 10Y Breakeven`(예상 −, 실측 +1.8σ) 등 세 노드가
예상과 반대로 찍힌다. 부호 하나를 + 로 돌리면 셋이 그대로 해소되고,
남는 `구리`(예상 −, 실측 +0.5σ)와 `Financials`(예상 +, 실측 −0.7σ)는
버그가 아니라 진짜 괴리다. 후자는 관계 정의 자체가 `strength 0.45` 로
"조달비용과 신용위험이 상쇄한다" 고 적어 둔 자리다.

*테마 방향(물가 ↑)* 과 *감성 톤(부정적)* 은 다른 축이다. 한 필드로 합칠 수
없다. 이것은 룰 추출기의 문제이고 지도와는 별건이라 여기서 고치지 않았다.
**다만 실측을 지도에 올린 덕분에 화면에서 저절로 드러났다** — 레이아웃을
바꾼 이유가 그것이다.

### 테마 방향과 감성 톤의 분리

앞 절에서 별건으로 남겼던 것을 고쳤다.

**무엇이 문제였나**

`build_impact_maps` 는 `event → theme` 관계의 방향을 **테마 감성의 부호**로
정했다. 그래서 이렇게 읽혔다.

| 기사 | 감성 | 쓰인 방향 | 맞는 방향 |
|---|---|---|---|
| 수입 물가 부담 확대 우려 | − | 물가 하락 | **물가 상승** |
| 물가 둔화 흐름 확인 | + | 물가 상승 | **물가 하락** |

둘 다 정확히 반대다. 그리고 이 부호는 지도의 첫 가지라 아래 연쇄 전체가
같이 뒤집힌다. `inflation_shock` 에서 `US 10Y Breakeven` · `US 10Y Treasury`
· `Nasdaq 100` 이 "예상과 반대" 로 찍힌 것이 그 결과였다.

**왜 한 필드로 합칠 수 없나**

호재냐 악재냐와 오르냐 내리냐는 **독립된 두 축**이다. 네 조합이 모두
존재한다.

|  | 방향 ↑ | 방향 ↓ |
|---|---|---|
| **감성 +** | 수주 확대 | 물가 둔화 |
| **감성 −** | 물가 부담 확대 | 성장 둔화 |

증거는 기존 `lexicon.yaml` 안에 이미 있었다. 감성 사전은 `둔화` 와 `확대`
를 "맥락 의존" 이라며 일부러 제외해 두었는데, 그 두 표현은 **방향으로는
전혀 모호하지 않다.** 한 사전으로 두 축을 감당할 수 없다는 뜻이다.

**고친 것**

1. `lexicon.yaml` 에 `direction` 사전을 추가했다. 감성 사전과 별개의 목록이다.
2. `engines/direction.py` 를 새로 두었다. 감성 엔진과 같은 파일에 두면
   다시 섞인다.
3. `NewsEvent.theme_direction: dict[str, Direction]` 을 추가했다.
4. LLM 스키마와 프롬프트에도 `theme_direction` 을 넣었다. 기존 프롬프트는
   "sentiment 는 해당 테마가 강해지는 방향을 뜻한다" 고 적어 **같은 혼동을
   모델에게 지시하고 있었다.** 이제 두 축을 나눠 설명하고, 모델이 비우면
   룰 추출기의 사전 값으로 채운다.
5. `build_impact_maps` 가 `theme_direction` 으로 부호를 정한다. 방향을
   못 읽으면 `ambiguous` 다 — 감성으로 대신 채우지 않는다.

**절 단위로는 부족했다 — 거리로 재야 했다**

처음에는 감성 엔진처럼 "테마 키워드가 있는 절만 보고 등장 순서로 가중" 했다.
이 문장에서 틀렸다.

    연준 위원 "물가 둔화 흐름 확인"… 국채 금리 소폭 상승

`rates` 테마는 `연준`(1절)과 `금리`(2절) 양쪽에 걸린다. 등장 순서로는 1절의
`둔화` 가 이기는데, 그 둔화는 물가를 말한 것이다. **키워드와의 거리**로
재도록 바꿔 `금리↔상승`(2절, 거리 5)이 `연준↔둔화`(1절, 거리 10)를 이기게
했다. 쉼표도 절 경계로 넣었다 — 한국어 헤드라인은 쉼표로 대조를 만든다
("정유·에너지주 강세, 항공주는 약세").

**사전에서 뺀 것**

`인상` · `인하`. 정책 행위지 값의 움직임이 아니다. "금리 인하 시점이 늦춰질
가능성" 은 `인하` 라는 글자를 담고도 금리 상승을 뜻한다. 부분 문자열
매칭으로는 감당할 수 없어 뺐다. 감성 사전이 `둔화`·`확대` 를 뺀 것과 같은
판단이고, 그 자리가 LLM 레이어의 몫이다.

**가장 약한 고리 — 같이 넣은 판정 게이트**

고치고 나니 `Financials` 가 모든 지도에서 "예상과 반대" 로 남았다. 그런데
`relationships.yaml` 은 그 관계를 `strength 0.45` 로 적으면서 이유에
**"조달비용과 신용위험이 상쇄한다"** 고 써 두었다. 스스로 약하다고 적은
관계를 놓고 "예상과 반대로 움직였다" 고 말하는 것은 과장이다.

그래서 `RelationshipNode.path_strength` — 대표 경로의 **가장 약한 고리** —
를 두고, `scoring.yaml` 의 `reaction_min_link_strength` 에 못 미치면
판정하지 않는다. 곱이 아니라 최솟값을 쓴다. 곱은 깊이에 따라 급격히
작아져 요구 8 의 6단 연쇄를 통째로 침묵시킨다. 사슬은 가장 약한 고리만큼만
버틴다.

**결과**

| 시나리오 | 고치기 전 | 고친 뒤 |
|---|---|---|
| `inflation_shock` | 6개 | **1개** (구리) |
| `baseline` | 3개 | **2개** (Nasdaq 100, Utilities) |
| `ai_divergence` | 0개 | 0개 |

남은 것은 전부 진짜 괴리다. `구리` 는 달러 강세 → 중국 약세 → 구리 하락이
예상인데 +0.5σ 로 올랐다. `baseline` 은 금리가 올랐는데 성장주와 유틸리티가
같이 올랐다. 이런 것을 화면에 올리는 것이 이 패널의 목적이다.

**남겨 둔 한계**

방향을 못 읽어 `ambiguous` 로 남는 기사가 있다 ("AI 데이터센터 증설 수주
잇따라… 반도체 업황 호황 국면 진입"). 사전을 늘리면 잡히지만, 틀린 방향
하나가 연쇄 전체를 거짓으로 만드는 구조라 **보수적으로 두었다.** 비는 것의
비용은 빈칸이고, 틀리는 것의 비용은 거짓 연쇄다.

### P4 — 완료

STEP 6.5 의 완료 기준을 충족했다. `MARKETPULSE_DATA_MODE` 하나로 전환되고
**엔진 코드는 한 줄도 바뀌지 않았다.** 어댑터 계층만 늘었다.

**먼저 확인한 것 — 이 환경의 네트워크는 여전히 막혀 있다**

사용자는 풀렸을 것이라 했으나 실측 결과는 그대로다. 추정이 아니라
프록시 응답이다.

```
CONNECT query1.finance.yahoo.com:443 → HTTP/1.1 403 Forbidden
```

| 호스트 | 결과 |
|---|---|
| query1.finance.yahoo.com · stooq.com · api.stlouisfed.org | CONNECT 403 |
| data.krx.co.kr · finance.naver.com · api.upbit.com | CONNECT 403 |
| pypi.org · registry.npmjs.org · api.github.com | 200 |

패키지 레지스트리와 GitHub 만 열려 있는 정책이다. 컨테이너 안에서 바꿀 수
있는 것이 아니다 — 환경을 만들 때 고른 네트워크 정책이고, 프록시를 끄는
것은 답이 아니다. 그래서 **STEP 7.1 이 처음부터 적어 둔 대응을 그대로**
따랐다. 어댑터는 전부 작성하되 고정 응답 fixture 로 계약을 고정하고,
사용자가 자기 네트워크에서 한 번에 검증할 수 있는 도구를 같이 만든다.

**만든 것**

| 파일 | 내용 |
|---|---|
| `config/sources.yaml` | 종목별 공급자 우선순위. "무엇을 본다"(instruments)와 "어디서 가져온다"의 분리 |
| `adapters/http.py` | 호스트별 회로 차단기를 가진 HTTP 계층 |
| `adapters/market/providers.py` | yahoo · stooq · fred · krx · csv |
| `adapters/market/live.py` | 공급자 폴백 + 파생 계산 + 출처 추적 |
| `adapters/news/rss.py` + `config/feeds.yaml` | RSS 7개 |
| `analysis/backtest.py` | 신호 백테스트 |
| `api/routes/stream.py` | WebSocket |
| `cli.py probe` / `cli.py backtest` | 진단과 채점 |

**설계와 달라진 것**

1. **`yfinance` · `FinanceDataReader` 를 쓰지 않았다.** 설계서는 두 어댑터를
   적었지만 표준 라이브러리 `urllib` 로 직접 붙였다. 두 패키지 모두 pandas
   의존이 깊고 스크래핑 계층이 자주 깨진다. 엔진 어디에도 pandas 의존이
   없는데 어댑터 때문에 들이면 데모가 죽을 경로가 하나 는다(STEP 7.7).
   응답 파싱은 `parse()` 정적 메서드로 분리해 fixture 로 테스트한다.

2. **`csv_replay` 를 별도 어댑터가 아니라 공급자로 만들었다.** 설계서는
   `csv_replay.py` 를 독립 어댑터로 적었다. 그러면 모드를 또 하나 늘려야
   하고, "네트워크가 되는 종목은 네트워크로, 안 되는 종목만 CSV" 라는 가장
   쓸모 있는 조합이 불가능해진다. 공급자로 두니 `data/replay/<id>.csv` 를
   넣기만 하면 자동으로 마지막 후보가 된다.

3. **LIVE 모드를 없애지 않고 경고로 처리했다.** 무료 공급자는 일봉 종가만
   준다. LIVE 를 막아 버리면 사용자가 왜 안 되는지 모르고, 조용히 LIVE 라
   표시하면 거짓말이다. 요청은 받되 데이터는 DELAYED 로 표시하고 이유를
   경고로 남긴다.

4. **백테스트의 대상을 바꿨다.** 설계서는 `backtester.py::_calculate_metrics`
   이식이라고만 적었다. 그대로 옮기면 매매 전략 백테스트가 되는데 이
   시스템은 주문을 내지 않는다. 지표(MDD·Sharpe·승률)는 이식하되 대상을
   **신호**로 바꿨다 — 판정 뒤 벤치마크가 어떻게 됐는가.

   같이 넣은 세 가지 제약이 지표보다 중요하다.
   - 같은 판정이 20틱 이어져도 신호는 하나다. 매 틱을 독립 표본으로 세면
     표본이 부풀고 지표가 거짓말을 한다.
   - 괴리는 방향 없는 신호다. 어느 쪽으로 수렴할지 말하지 않으므로
     적중률을 계산하지 않는다.
   - 표본 10건 미만은 그렇게 적는다. 5건짜리 적중률 60% 는 숫자가 아니라
     인상이다.

   진입가는 판정 시각 **이하**의 마지막 봉이다. 그 이후 봉을 쓰면 판정
   시점에 없던 정보를 쓰는 것이다(look-ahead). 테스트로 고정했다.

5. **`probe` 명령을 추가했다.** 설계서에 없다. 막힌 네트워크에서 개발한
   결과물을 사용자가 자기 네트워크에서 검증해야 하는데, "안 된다" 와
   "왜 안 되는지" 는 다르다. 공급자별 가용성, 종목별 커버리지, 실패 이유,
   호스트별 회로 상태가 한 화면에 나온다.

**Flow 데이터 — STEP 7.1 이 지목한 Gap**

외국인·기관 순매수는 여전히 무료 API 가 없다. KRX 정보데이터시스템의
OTP 기반 CSV 가 유일한 무료 경로라 그것을 붙였지만 공개 계약이 아니다.
실패를 정상 경로로 취급한다 — 실패하면 CSV 로, 그것도 없으면 missing 이다.
**0 으로 채우지 않는 것이 여기서 특히 중요하다.** 요구 5 의 Theme Flow
Momentum 과 요구 7 의 가격↔수급 괴리가 이 값에 의존하므로, 0 이 되면
"수급이 중립이다" 라는 없는 주장이 만들어진다.

Breadth(상승종목 비율·신고가-신저가)는 종목 전체를 훑어야 나와서 무료
공급자가 아예 없다. `sources.yaml` 에 **빈 목록으로 명시**했다 — 설정에서
빠진 것과 "받을 곳이 없다" 는 다르다. 테스트로 고정했다.

**검증**

네트워크가 막혀 통합 테스트를 할 수 없으므로 계약 테스트로 고정했다
(테스트 445개 통과, P4 에서 51개 추가).

- 공급자별 파서: 정상 응답, API 오류, HTML 차단 페이지, FRED 의 `.` 휴일
- 폴백 사슬: 한 공급자 장애 → 다음, 전부 장애 → missing(0 아님)
- 최소 관측 수 미달 시 거부
- 출처가 데이터와 함께 이동(`csv:US10Y`)
- RSS: 미래 시각 기사 제거, 중복 헤드라인 축약, 죽은 피드 격리, id 안정성
- 회로 차단기 개방
- `sources.yaml` 의 모든 참조가 레지스트리에 존재, 파생 지표에는 공급자가
  없음(따로 받으면 기초 자산과 어긋난다)

실측으로 확인한 것 — `probe` 가 이 환경에서 커버리지 0/3 과 실패 이유를
정확히 출력한다. 백테스트는 30일치 히스토리를 만들어 돌렸고, 표본이 적은
신호에 "참고용" 을 붙이는 것까지 확인했다.

**남은 것**

- 승인 요청 ④ 스코어링 가중치 검토. P0~P4 내내 미결이다. 이제 실데이터를
  받을 수 있는 코드가 있으니, 사용자가 열린 네트워크에서 며칠치를 쌓으면
  `scoring.yaml` 을 통계로 재검토할 수 있다. **지금 값은 전부 매크로 상식
  기반 초기 제안값이다.**
- 장중 갱신. 유료 피드 없이는 불가능하다.
- KRX 공급자의 실환경 검증. 이 환경에서 한 번도 200 을 받아 보지 못했다.

### 베타 — 막힌 네트워크에서 실데이터로 돌리기

사용자 요청: "구할 수 있는 정보로만 전부 최대한 찾아서 베타버전 완성."

**무엇이 열려 있는지 다시 실측했다**

| 호스트 | 결과 |
|---|---|
| Yahoo · stooq · FRED · KRX · 네이버 · 업비트 | CONNECT 403 |
| frankfurter · exchangerate.host · coingecko · ECB · World Bank · Nasdaq Data Link | 전부 차단 |
| **raw.githubusercontent.com** | **200** |
| pypi · npm · api.github.com | 200 |

GitHub API 는 세션 레포로 제한되지만 **raw 는 제한이 없다.** 그리고
`datasets` 조직은 CBOE·EIA·연준 H.10 의 공개 자료를 매일 자동으로
미러링한다. 원본 기관에 닿을 수 없을 때 **같은 숫자에 닿는 유일한
경로**다.

**GithubCsvProvider 를 추가했다**

| 종목 | 저장소 | 원본 | 마지막 봉 |
|---|---|---|---|
| VIX | `finance-vix/vix-daily.csv` | CBOE | 2026-09-09 |
| WTI · BRENT | `oil-prices/{wti,brent}-daily.csv` | EIA | 2026-09-09 |
| NATGAS | `natural-gas/daily.csv` | EIA | 2026-09-09 |
| USDKRW · USDJPY · EURUSD · USDCNH | `exchange-rates/daily.csv` | 연준 H.10 | 2026-09-04 |

세 가지를 지원해야 했다.

1. **열 이름을 설정에서 받는다.** VIX 파일은 OHLC 라 `CLOSE` 를 명시해야
   한다. 자동 추론에 맡기면 미러의 열이 바뀐 날 조용히 `OPEN` 을 종가로
   읽는다 — 아무도 눈치채지 못하는 종류의 오류다.
2. **롱 포맷 필터.** 환율 파일 하나에 22개국이 들어 있다.
   `filter: {Country: South Korea}` 로 한 계열만 뽑는다.
3. **역수.** 연준 H.10 은 USD→EUR(0.86)로 준다. `invert: true` 가 없으면
   EURUSD 가 0.86 이 되어 z-score 가 통째로 뒤집힌다.

파일 하나를 네 종목이 나눠 쓰므로 15분 메모리 캐시를 뒀다. 없으면 같은
7.6MB 를 네 번 내려받는다.

**실측 결과 — 베타가 실제로 도는 상태**

```
모드 DELAYED · 커버리지 17% (8/47) · 최대 지연 7.7일 · 기사 0건
판정 없음 · Confidence 5%
WTI 원유 +0.96σ (+3.24%)   USD/KRW -0.95σ (-0.76%)   VIX +0.73σ (+4.71%)
```

시장 상태가 "판정 없음" 인 것은 고장이 아니라 **정답**이다. 8종목으로는
어떤 상태 룰의 require 조건도 충족할 수 없고, confidence 5% 가 그 사실을
말한다. 시스템은 모르는 것을 모른다고 말했다.

**이 과정에서 고친 것 — 전부 실데이터를 붙이고 나서야 드러났다**

1. **캐시 TTL 4초가 화면을 영영 비웠다.** 실데이터 수집은 콜드 9.7초가
   걸리는데 TTL 이 4초라, 폴링마다 새 수집이 시작되고 직전 요청은 취소됐다.
   **어떤 요청도 끝나지 않아 화면이 계속 비어 있었다.** 모드별 TTL 로
   바꿨다 — MOCK 4초, 실데이터 300초. 값 자체도 데이터의 성질을 따라야
   한다. 하루에 한 번 바뀌는 일봉을 4초마다 다시 받을 이유가 없다.

2. **실데이터 모드에서 MOCK 시나리오 전환기가 떴다.** 프론트가 모드를
   모른 채 시나리오를 붙여 요청했다. `/api/v1/info` 로 모드를 먼저 확인하고,
   MOCK 이 아니면 전환기를 숨기고 시나리오를 보내지 않는다.

3. **DELAYED 신선도 임계가 22분이었다.** 무료 공급자는 일봉을 주므로
   월요일 아침의 마지막 봉은 금요일 종가다 — 정상 상태에서도 3일이다.
   22분으로 두면 주말마다 거짓 경보가 뜨고, 경보가 일상이 되면 진짜 고장을
   놓친다. 4일로 바꿨다. 지금 환율 7.7일은 정확히 걸리고 유가 2일은
   안 걸린다.

4. **PARTIAL factor 의 coverage 기여가 0 이었다.** 데이터가 반쯤 빠진
   상황에서 confidence 가 정확히 0 이 되어 "조금 아는 것" 과 "전혀 모르는
   것" 이 같아졌다. 운용자가 신뢰도를 조정해야 할 때가 바로 그 구간이다.
   절반(0.5)을 인정한다. 분모는 계산된 factor 가 아니라 **정의된 factor**
   수로 뒀다 — 계산 못 한 것을 분모에서 빼면 둘만 살아남아도 100% 가 된다.

5. **신선도를 숫자로만 보여줬다.** `661701초` 는 사람이 못 읽는다. 단위를
   사람 단위로 바꾸고, 기준을 넘으면 **문장으로** 말하게 했다. 화면에
   숫자가 있어도 사람은 잘 안 본다.

6. **내려받은 CSV 가 그대로 안 들어갔다.** FRED 다운로드 헤더는
   `observation_date,DGS10` 인데 파서가 `date`/`close` 만 받았다. 열 이름을
   손으로 고치게 만들면 그 과정에서 `Open` 을 종가로 넣는 사고가 난다.

**베타의 한계 — 숨기지 않는다**

- **커버리지 17%.** 일별 주가지수·금리·수급을 이 경로로 구할 수 없다.
  Market State 는 사실상 판정 불가이고, 괴리 탐지는 테마당 두 신호가
  필요해 동작하지 않는다.
- **뉴스 0건.** RSS 호스트가 전부 막혀 있다. 테마의 news 성분이 비고,
  Impact Map 은 사건이 아니라 테마를 뿌리로 그린다.
- **단일 레그 테마 점수.** Defense 는 ITA 가 없어 VIX 만으로,
  China 는 USDCNH 만으로 점수가 난다. 가중치 재정규화의 정상 동작이고
  `데이터 부족` 으로 표시되지만, 히트맵이 점수로 정렬되므로 한 다리로 선
  테마가 두 다리로 선 테마보다 위에 올 수 있다. **승인 요청 ④ 스코어링
  검토와 함께 볼 항목이다.**
- 환율 미러가 최대 7.7일 늦다. 매크로 신호로는 쓸 만하지만 일간 변화를
  논할 수준은 아니다.

**네트워크가 열리면**

`sources.yaml` 에서 `github` 은 각 종목의 **마지막 네트워크 후보**다.
Yahoo·FRED 가 닿는 순간 자동으로 그쪽이 쓰이고 미러는 조용히 뒤로 물러난다.
설정을 고칠 필요가 없다.
