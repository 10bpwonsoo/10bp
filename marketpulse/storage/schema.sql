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
