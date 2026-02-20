"""
SQL Server 적재 테스트 스크립트
- 기존 PC1\SQLEXPRESS / CryptoDB 서버 사용
- 테이블 생성 → Upbit 데이터 수집 → 적재 → 검증
"""

import time
import requests
import pandas as pd
from sqlalchemy import create_engine, text

# ============================================
# SQL Server 설정 (기존 upbitdata_sql.py 기반)
# ============================================
SQL_SERVER = r"CH-PC1\SQLEXPRESS"
DB_NAME = "CryptoDB"
ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

conn_str = (
    f"mssql+pyodbc://@{SQL_SERVER}/{DB_NAME}"
    f"?driver={ODBC_DRIVER.replace(' ', '+')}"
    "&Trusted_Connection=yes"
)

print("=" * 70)
print("  SQL Server 적재 테스트")
print("=" * 70)

# 1) DB 연결 테스트 (master에 먼저 연결하여 CryptoDB 생성)
print("\n[1] DB 연결 테스트...")
try:
    # 먼저 master DB에 연결하여 CryptoDB 존재 여부 확인/생성
    master_conn_str = (
        f"mssql+pyodbc://@{SQL_SERVER}/master"
        f"?driver={ODBC_DRIVER.replace(' ', '+')}"
        "&Trusted_Connection=yes"
    )
    master_engine = create_engine(master_conn_str, isolation_level="AUTOCOMMIT")
    with master_engine.connect() as conn:
        result = conn.execute(text("SELECT @@SERVERNAME AS server"))
        row = result.fetchone()
        print(f"    서버: {row[0]}")

        # CryptoDB 존재 확인
        db_exists = conn.execute(text(
            "SELECT DB_ID(:db_name)"
        ), {"db_name": DB_NAME}).scalar()

        if db_exists is None:
            print(f"    {DB_NAME} DB가 없으므로 생성합니다...")
            conn.execute(text(f"CREATE DATABASE [{DB_NAME}]"))
            print(f"    {DB_NAME} DB 생성 완료!")
        else:
            print(f"    {DB_NAME} DB 이미 존재")

    master_engine.dispose()

    # CryptoDB에 연결
    engine = create_engine(conn_str, pool_size=5, pool_pre_ping=True)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DB_NAME() AS db"))
        row = result.fetchone()
        print(f"    DB:   {row[0]}")
        print("    연결 성공!")
except Exception as e:
    print(f"    연결 실패: {e}")
    exit(1)

# 2) 테이블 생성
print("\n[2] 테이블 생성...")

DDL_LIST = [
    # market_info
    """
    IF OBJECT_ID('dbo.market_info', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.market_info (
            market        NVARCHAR(20)   NOT NULL,
            korean_name   NVARCHAR(100)  NULL,
            english_name  NVARCHAR(100)  NULL,
            exchange      NVARCHAR(20)   NOT NULL DEFAULT 'upbit',
            market_type   NVARCHAR(10)   NULL,
            is_active     BIT            NOT NULL DEFAULT 1,
            updated_at    DATETIME2(0)   NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_market_info PRIMARY KEY (market, exchange)
        );
    END
    """,
    # ohlcv_daily
    """
    IF OBJECT_ID('dbo.ohlcv_daily', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ohlcv_daily (
            id            BIGINT IDENTITY(1,1),
            market        NVARCHAR(20)  NOT NULL,
            exchange      NVARCHAR(20)  NOT NULL DEFAULT 'upbit',
            candle_date   DATE          NOT NULL,
            open_price    FLOAT         NOT NULL,
            high_price    FLOAT         NOT NULL,
            low_price     FLOAT         NOT NULL,
            close_price   FLOAT         NOT NULL,
            volume        FLOAT         NULL,
            trade_value   FLOAT         NULL,
            inserted_at   DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_ohlcv_daily PRIMARY KEY (market, exchange, candle_date)
        );
        CREATE INDEX IX_ohlcv_daily_date ON dbo.ohlcv_daily (candle_date);
    END
    """,
    # ohlcv_minute
    """
    IF OBJECT_ID('dbo.ohlcv_minute', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.ohlcv_minute (
            id            BIGINT IDENTITY(1,1),
            market        NVARCHAR(20)  NOT NULL,
            exchange      NVARCHAR(20)  NOT NULL DEFAULT 'upbit',
            candle_dt     DATETIME2(0)  NOT NULL,
            unit          INT           NOT NULL DEFAULT 1,
            open_price    FLOAT         NOT NULL,
            high_price    FLOAT         NOT NULL,
            low_price     FLOAT         NOT NULL,
            close_price   FLOAT         NOT NULL,
            volume        FLOAT         NULL,
            trade_value   FLOAT         NULL,
            inserted_at   DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_ohlcv_minute PRIMARY KEY (market, exchange, candle_dt, unit)
        );
        CREATE INDEX IX_ohlcv_minute_dt ON dbo.ohlcv_minute (candle_dt);
    END
    """,
    # orderbook
    """
    IF OBJECT_ID('dbo.orderbook', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.orderbook (
            id              BIGINT IDENTITY(1,1),
            market          NVARCHAR(20)  NOT NULL,
            exchange        NVARCHAR(20)  NOT NULL DEFAULT 'upbit',
            timestamp_utc   DATETIME2(3)  NOT NULL,
            ask_price       FLOAT         NOT NULL,
            ask_size        FLOAT         NOT NULL,
            bid_price       FLOAT         NOT NULL,
            bid_size        FLOAT         NOT NULL,
            level           INT           NOT NULL DEFAULT 1,
            total_ask_size  FLOAT         NULL,
            total_bid_size  FLOAT         NULL,
            inserted_at     DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_orderbook PRIMARY KEY (market, exchange, timestamp_utc, level)
        );
        CREATE INDEX IX_orderbook_ts ON dbo.orderbook (timestamp_utc);
    END
    """,
    # trade_history
    """
    IF OBJECT_ID('dbo.trade_history', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.trade_history (
            id              BIGINT IDENTITY(1,1),
            market          NVARCHAR(20)  NOT NULL,
            exchange        NVARCHAR(20)  NOT NULL DEFAULT 'upbit',
            trade_dt        DATETIME2(3)  NOT NULL,
            side            NVARCHAR(4)   NOT NULL,
            price           FLOAT         NOT NULL,
            quantity        FLOAT         NOT NULL,
            trade_value     FLOAT         NULL,
            order_id        NVARCHAR(100) NULL,
            fee             FLOAT         NULL,
            inserted_at     DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_trade_history PRIMARY KEY (market, exchange, trade_dt, side, price)
        );
        CREATE INDEX IX_trade_history_dt ON dbo.trade_history (trade_dt);
        CREATE INDEX IX_trade_history_order ON dbo.trade_history (order_id)
            WHERE order_id IS NOT NULL;
    END
    """,
]

table_names = ["market_info", "ohlcv_daily", "ohlcv_minute", "orderbook", "trade_history"]

with engine.begin() as conn:
    for i, ddl in enumerate(DDL_LIST):
        conn.execute(text(ddl))
        print(f"    {table_names[i]} - 생성/확인 완료")

print("    모든 테이블 준비 완료!")

# 3) Upbit 데이터 수집
print("\n[3] Upbit KRW 마켓 데이터 수집...")

session = requests.Session()
session.headers.update({"Accept": "application/json"})
BASE_URL = "https://api.upbit.com/v1"

# 마켓 목록
resp = session.get(f"{BASE_URL}/market/all", params={"is_details": "true"}, timeout=10)
resp.raise_for_status()
all_markets = [item for item in resp.json() if item["market"].startswith("KRW-")]
print(f"    KRW 마켓 수: {len(all_markets)}개")

# 마켓 정보 DataFrame
market_df = pd.DataFrame([{
    "market": m["market"],
    "korean_name": m.get("korean_name", ""),
    "english_name": m.get("english_name", ""),
    "exchange": "upbit",
    "market_type": "KRW",
    "is_active": 1,
} for m in all_markets])

# 일봉 데이터 수집 (전체 코인, 최근 30일)
print(f"    일봉 수집 중 (전체 {len(all_markets)}개 코인, 최근 30일)...")
all_daily = []
total = len(all_markets)
for idx, mkt in enumerate(all_markets, 1):
    market = mkt["market"]
    try:
        resp = session.get(
            f"{BASE_URL}/candles/days",
            params={"market": market, "count": 30},
            timeout=10,
        )
        resp.raise_for_status()
        candles = resp.json()
        for c in candles:
            all_daily.append({
                "market": market,
                "exchange": "upbit",
                "candle_date": c["candle_date_time_kst"][:10],
                "open_price": c["opening_price"],
                "high_price": c["high_price"],
                "low_price": c["low_price"],
                "close_price": c["trade_price"],
                "volume": c.get("candle_acc_trade_volume", 0),
                "trade_value": c.get("candle_acc_trade_price", 0),
            })
        if idx % 50 == 0:
            print(f"    [{idx}/{total}] {market} 수집 완료")
    except Exception as e:
        print(f"    [{idx}/{total}] {market} 수집 실패: {e}")
    time.sleep(0.12)

daily_df = pd.DataFrame(all_daily)
print(f"    일봉 총 {len(daily_df):,}행 수집 완료")

# 4) SQL Server 적재 (MERGE/UPSERT)
print("\n[4] SQL Server 적재 중...")


def upsert_via_staging(eng, df, target_table, staging_table, merge_keys, value_columns):
    """스테이징 테이블을 사용한 MERGE UPSERT"""
    if df.empty:
        return 0
    all_columns = merge_keys + value_columns
    with eng.begin() as conn:
        # 스테이징 테이블 삭제 후 재생성
        conn.execute(text(
            f"IF OBJECT_ID('dbo.{staging_table}','U') IS NOT NULL "
            f"DROP TABLE dbo.{staging_table};"
        ))
        conn.execute(text(
            f"SELECT TOP 0 {', '.join(all_columns)} "
            f"INTO dbo.{staging_table} FROM dbo.{target_table}"
        ))
        # 스테이징에 데이터 삽입
        df[all_columns].to_sql(
            staging_table, con=conn, schema="dbo",
            if_exists="append", index=False, method="multi", chunksize=100,
        )
        # MERGE
        on_clause = " AND ".join(f"T.{k} = S.{k}" for k in merge_keys)
        update_set = ", ".join(f"T.{c} = S.{c}" for c in value_columns)
        insert_cols = ", ".join(all_columns)
        insert_vals = ", ".join(f"S.{c}" for c in all_columns)
        merge_sql = f"""
            MERGE dbo.{target_table} AS T
            USING dbo.{staging_table} AS S ON {on_clause}
            WHEN MATCHED THEN UPDATE SET {update_set}
            WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals});
        """
        result = conn.execute(text(merge_sql))
        row_count = result.rowcount
        conn.execute(text(f"DROP TABLE dbo.{staging_table};"))
    return row_count


# market_info 적재
market_rows = upsert_via_staging(
    engine, market_df,
    target_table="market_info", staging_table="stg_market_info",
    merge_keys=["market", "exchange"],
    value_columns=["korean_name", "english_name", "market_type", "is_active"],
)
print(f"    market_info: {market_rows:,}행 UPSERT")

# ohlcv_daily 적재
daily_rows = upsert_via_staging(
    engine, daily_df,
    target_table="ohlcv_daily", staging_table="stg_ohlcv_daily",
    merge_keys=["market", "exchange", "candle_date"],
    value_columns=["open_price", "high_price", "low_price", "close_price", "volume", "trade_value"],
)
print(f"    ohlcv_daily: {daily_rows:,}행 UPSERT")

# 5) 적재 검증
print("\n[5] 적재 검증...")

with engine.connect() as conn:
    # 테이블별 행 수
    for tbl in table_names:
        result = conn.execute(text(f"SELECT COUNT(*) FROM dbo.{tbl}"))
        cnt = result.scalar()
        print(f"    dbo.{tbl}: {cnt:,}행")

    # market_info 샘플
    print("\n    --- dbo.market_info 샘플 (상위 5개) ---")
    result = conn.execute(text(
        "SELECT TOP 5 market, korean_name, english_name, exchange, market_type "
        "FROM dbo.market_info WHERE exchange = 'upbit' ORDER BY market"
    ))
    for row in result:
        print(f"    {row[0]:15s} | {row[1]:10s} | {row[2]:15s} | {row[3]} | {row[4]}")

    # ohlcv_daily 샘플 (BTC)
    print("\n    --- dbo.ohlcv_daily 샘플 (KRW-BTC 최근 5일) ---")
    result = conn.execute(text(
        "SELECT TOP 5 market, candle_date, open_price, high_price, low_price, close_price, volume "
        "FROM dbo.ohlcv_daily WHERE market = 'KRW-BTC' AND exchange = 'upbit' "
        "ORDER BY candle_date DESC"
    ))
    print(f"    {'마켓':15s} | {'날짜':12s} | {'시가':>15s} | {'고가':>15s} | {'저가':>15s} | {'종가':>15s} | {'거래량':>12s}")
    print("    " + "-" * 105)
    for row in result:
        print(f"    {row[0]:15s} | {str(row[1]):12s} | {row[2]:>15,.0f} | {row[3]:>15,.0f} | {row[4]:>15,.0f} | {row[5]:>15,.0f} | {row[6]:>12,.2f}")

    # NULL 검사
    print("\n    --- ohlcv_daily NULL/0 가격 검사 ---")
    null_check = conn.execute(text("""
        SELECT
            SUM(CASE WHEN open_price IS NULL OR open_price = 0 THEN 1 ELSE 0 END) AS null_open,
            SUM(CASE WHEN high_price IS NULL OR high_price = 0 THEN 1 ELSE 0 END) AS null_high,
            SUM(CASE WHEN low_price IS NULL OR low_price = 0 THEN 1 ELSE 0 END) AS null_low,
            SUM(CASE WHEN close_price IS NULL OR close_price = 0 THEN 1 ELSE 0 END) AS null_close,
            COUNT(*) AS total_rows
        FROM dbo.ohlcv_daily
        WHERE exchange = 'upbit'
    """))
    row = null_check.fetchone()
    print(f"    총 행: {row[4]:,}")
    print(f"    시가 NULL/0: {row[0]}건 {'OK' if row[0] == 0 else 'ISSUE'}")
    print(f"    고가 NULL/0: {row[1]}건 {'OK' if row[1] == 0 else 'ISSUE'}")
    print(f"    저가 NULL/0: {row[2]}건 {'OK' if row[2] == 0 else 'ISSUE'}")
    print(f"    종가 NULL/0: {row[3]}건 {'OK' if row[3] == 0 else 'ISSUE'}")

    # 가격 논리 검증
    print("\n    --- ohlcv_daily 가격 논리 검증 ---")
    logic_check = conn.execute(text("""
        SELECT
            SUM(CASE WHEN high_price < low_price THEN 1 ELSE 0 END) AS high_lt_low,
            SUM(CASE WHEN high_price < open_price THEN 1 ELSE 0 END) AS high_lt_open,
            SUM(CASE WHEN high_price < close_price THEN 1 ELSE 0 END) AS high_lt_close,
            SUM(CASE WHEN low_price > open_price THEN 1 ELSE 0 END) AS low_gt_open,
            SUM(CASE WHEN low_price > close_price THEN 1 ELSE 0 END) AS low_gt_close
        FROM dbo.ohlcv_daily
        WHERE exchange = 'upbit'
    """))
    lrow = logic_check.fetchone()
    print(f"    고가 < 저가: {lrow[0]}건 {'OK' if lrow[0] == 0 else 'ISSUE'}")
    print(f"    고가 < 시가: {lrow[1]}건 {'OK' if lrow[1] == 0 else 'ISSUE'}")
    print(f"    고가 < 종가: {lrow[2]}건 {'OK' if lrow[2] == 0 else 'ISSUE'}")
    print(f"    저가 > 시가: {lrow[3]}건 {'OK' if lrow[3] == 0 else 'ISSUE'}")
    print(f"    저가 > 종가: {lrow[4]}건 {'OK' if lrow[4] == 0 else 'ISSUE'}")

    # 코인별 데이터 건수 분포
    print("\n    --- 코인별 일봉 데이터 건수 분포 ---")
    dist = conn.execute(text("""
        SELECT
            MIN(cnt) AS min_cnt, MAX(cnt) AS max_cnt, AVG(cnt) AS avg_cnt,
            COUNT(*) AS coin_count
        FROM (
            SELECT market, COUNT(*) AS cnt
            FROM dbo.ohlcv_daily WHERE exchange = 'upbit'
            GROUP BY market
        ) sub
    """))
    drow = dist.fetchone()
    print(f"    코인 수: {drow[3]}개")
    print(f"    최소 건수: {drow[0]}일")
    print(f"    최대 건수: {drow[1]}일")
    print(f"    평균 건수: {drow[2]:.1f}일")

engine.dispose()

print("\n" + "=" * 70)
print("  적재 테스트 완료!")
print("=" * 70)
print(f"\n  서버: {SQL_SERVER}")
print(f"  DB:   {DB_NAME}")
print(f"  테이블 위치:")
print(f"    - [{DB_NAME}].[dbo].[market_info]    : 마켓 정보 (코인 목록)")
print(f"    - [{DB_NAME}].[dbo].[ohlcv_daily]    : 일봉 OHLCV 데이터")
print(f"    - [{DB_NAME}].[dbo].[ohlcv_minute]   : 분봉 OHLCV 데이터")
print(f"    - [{DB_NAME}].[dbo].[orderbook]      : 호가 데이터")
print(f"    - [{DB_NAME}].[dbo].[trade_history]  : 체결/매매 내역")
