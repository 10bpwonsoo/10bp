-- Market Pulse AI 스냅샷 저장소 (SQLite)
--
-- 기존 upbit_trading 은 MS SQL Server 를 쓰지만 여기서는 SQLite 다.
-- 이유는 STEP 3.1 에 적었다. MSSQL 은 이 환경에서 뜨지 않고, 해커톤
-- 데모에서 zero-config 가 의존성 하나를 줄인다. Repository 인터페이스로
-- 감싸 두었으므로 Postgres/Timescale 교체는 구현체만 바꾸면 된다.

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stream_key      TEXT    NOT NULL,   -- "{mode}:{scenario}"
    as_of           TEXT    NOT NULL,   -- ISO8601 UTC
    created_at      TEXT    NOT NULL,
    payload         TEXT    NOT NULL,   -- IntelligenceSnapshot JSON
    -- 아직 min_duration 을 채우지 못한 divergence 후보.
    -- 스냅샷에는 싣지 않지만 다음 틱에서 지속 기간을 이으려면 필요하다.
    pending         TEXT    NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS ix_snapshots_stream_as_of
    ON snapshots (stream_key, as_of DESC);

-- 같은 스트림의 같은 시각은 한 번만 남긴다. 재실행이 중복을 만들지 않는다.
CREATE UNIQUE INDEX IF NOT EXISTS ux_snapshots_stream_as_of
    ON snapshots (stream_key, as_of);


-- ── Investment Intelligence (2026-09-16 신설) ─────────────────────
-- 기존 snapshots 테이블은 손대지 않는다. 아래는 전부 추가다.

-- 종목·대체데이터 일별 시계열. 화면 refresh 마다 다시 받지 않고 여기서 읽는다.
CREATE TABLE IF NOT EXISTS alt_daily (
    series_id   TEXT NOT NULL,
    date        TEXT NOT NULL,   -- YYYY-MM-DD (UTC 기준 봉 날짜)
    value       REAL NOT NULL,
    volume      REAL,            -- 없으면 NULL. 0 으로 채우지 않는다
    source      TEXT NOT NULL,   -- "yahoo:005930.KS" 등
    PRIMARY KEY (series_id, date)
);

-- 마지막으로 성공한 수집. 같은 날 두 번 받지 않는다 (incremental fetch).
CREATE TABLE IF NOT EXISTS alt_fetch_log (
    series_id    TEXT NOT NULL PRIMARY KEY,
    fetched_date TEXT NOT NULL,  -- 수집한 날 (UTC)
    last_bar     TEXT NOT NULL,  -- 마지막 봉 날짜
    source       TEXT NOT NULL,
    points       INTEGER NOT NULL
);

-- Investment Intelligence 결과 스냅샷. 기존 snapshots 와 분리한다 —
-- 기존 화면이 이 계층의 계산 시간에 묶이지 않게.
CREATE TABLE IF NOT EXISTS investment_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stream_key  TEXT NOT NULL,
    as_of       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_investment_stream_as_of
    ON investment_snapshots (stream_key, as_of);

-- 애널리스트 리비전 (CSV 적재 또는 MOCK). 날짜별 upsert.
CREATE TABLE IF NOT EXISTS analyst_revision (
    stock_id     TEXT NOT NULL,
    date         TEXT NOT NULL,
    broker       TEXT NOT NULL DEFAULT '',
    rating       TEXT,
    target_price REAL,
    eps_fy1      REAL,
    source       TEXT NOT NULL,
    PRIMARY KEY (stock_id, date, broker)
);

-- 수기 해설. FACT / NEWS / ANALYST / INTERPRETATION / UNKNOWN 을 분리해 저장.
CREATE TABLE IF NOT EXISTS commentary (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,   -- market | stock | alternative | analyst
    entity      TEXT NOT NULL,   -- stock id, alt id, 'MARKET'
    as_of       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    source_mode TEXT NOT NULL,   -- manual | api
    confidence  TEXT NOT NULL,
    payload     TEXT NOT NULL    -- Commentary JSON
);
CREATE INDEX IF NOT EXISTS ix_commentary_entity ON commentary (entity, as_of DESC);
