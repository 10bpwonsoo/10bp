"""
SQL Server 관리 모듈 - 테이블 생성, UPSERT, 연결 풀링

테이블 스키마:
  - market_info: 마켓 정보 (코인 목록, 심볼)
  - ohlcv_daily: 일봉 데이터
  - ohlcv_minute: 분봉 데이터
  - orderbook: 호가 데이터
  - trade_history: 체결 내역
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional

import pandas as pd
from sqlalchemy import create_engine, text, pool

from .config import config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# DDL: 테이블 생성 SQL
# ──────────────────────────────────────────────

DDL_MARKET_INFO = """
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
"""

DDL_OHLCV_DAILY = """
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
"""

DDL_OHLCV_MINUTE = """
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
"""

DDL_ORDERBOOK = """
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
"""

DDL_TRADE_HISTORY = """
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
"""

ALL_DDL = [
    DDL_MARKET_INFO,
    DDL_OHLCV_DAILY,
    DDL_OHLCV_MINUTE,
    DDL_ORDERBOOK,
    DDL_TRADE_HISTORY,
]


class DBManager:
    """SQL Server 데이터베이스 관리자

    - SQLAlchemy 엔진 기반 연결 풀링
    - 테이블 자동 생성
    - MERGE(UPSERT) 로직으로 중복 방지
    """

    def __init__(self, connection_string: Optional[str] = None):
        conn_str = connection_string or config.db.connection_string
        self._engine = create_engine(
            conn_str,
            pool_size=config.db.pool_size,
            pool_timeout=config.db.pool_timeout,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        logger.info("DB 엔진 생성 완료: %s", config.db.server)

    # ── 연결 컨텍스트 ──────────────────────────

    @contextmanager
    def connection(self):
        """트랜잭션이 포함된 DB 연결 컨텍스트 매니저"""
        with self._engine.begin() as conn:
            yield conn

    # ── 초기화 ─────────────────────────────────

    def init_tables(self):
        """모든 테이블을 생성합니다 (IF NOT EXISTS)."""
        with self.connection() as conn:
            for ddl in ALL_DDL:
                conn.execute(text(ddl))
        logger.info("테이블 초기화 완료")

    # ── 스테이징 + MERGE 헬퍼 ──────────────────

    def _upsert_via_staging(
        self,
        conn,
        df: pd.DataFrame,
        target_table: str,
        staging_table: str,
        merge_keys: List[str],
        value_columns: List[str],
    ):
        """스테이징 테이블을 사용한 MERGE UPSERT

        1) 스테이징 테이블 생성 (임시)
        2) DataFrame을 스테이징에 INSERT
        3) MERGE로 타깃 테이블에 UPSERT
        4) 스테이징 테이블 삭제
        """
        if df.empty:
            return 0

        all_columns = merge_keys + value_columns

        # 1) 스테이징 테이블 삭제 후 재생성
        conn.execute(text(
            f"IF OBJECT_ID('dbo.{staging_table}','U') IS NOT NULL "
            f"DROP TABLE dbo.{staging_table};"
        ))
        conn.execute(text(
            f"SELECT TOP 0 {', '.join(all_columns)} "
            f"INTO dbo.{staging_table} FROM dbo.{target_table}"
        ))

        # 2) 스테이징에 데이터 삽입
        df[all_columns].to_sql(
            staging_table,
            con=conn,
            schema="dbo",
            if_exists="append",
            index=False,
            method="multi",
            chunksize=100,
        )

        # 3) MERGE
        on_clause = " AND ".join(f"T.{k} = S.{k}" for k in merge_keys)
        update_set = ", ".join(f"T.{c} = S.{c}" for c in value_columns)
        insert_cols = ", ".join(all_columns)
        insert_vals = ", ".join(f"S.{c}" for c in all_columns)

        merge_sql = f"""
            MERGE dbo.{target_table} AS T
            USING dbo.{staging_table} AS S
            ON {on_clause}
            WHEN MATCHED THEN
                UPDATE SET {update_set}
            WHEN NOT MATCHED THEN
                INSERT ({insert_cols})
                VALUES ({insert_vals});
        """
        result = conn.execute(text(merge_sql))
        row_count = result.rowcount

        # 4) 스테이징 정리
        conn.execute(text(f"DROP TABLE dbo.{staging_table};"))

        return row_count

    # ── 마켓 정보 ──────────────────────────────

    def upsert_market_info(self, df: pd.DataFrame) -> int:
        """마켓 정보를 UPSERT합니다.

        Args:
            df: columns = [market, korean_name, english_name, exchange, market_type]

        Returns:
            영향 받은 행 수
        """
        with self.connection() as conn:
            count = self._upsert_via_staging(
                conn, df,
                target_table="market_info",
                staging_table="stg_market_info",
                merge_keys=["market", "exchange"],
                value_columns=["korean_name", "english_name", "market_type", "is_active"],
            )
        logger.info("market_info UPSERT: %d rows", count)
        return count

    # ── 일봉 데이터 ────────────────────────────

    def upsert_ohlcv_daily(self, df: pd.DataFrame) -> int:
        """일봉 OHLCV 데이터를 UPSERT합니다.

        Args:
            df: columns = [market, exchange, candle_date,
                           open_price, high_price, low_price, close_price,
                           volume, trade_value]

        Returns:
            영향 받은 행 수
        """
        with self.connection() as conn:
            count = self._upsert_via_staging(
                conn, df,
                target_table="ohlcv_daily",
                staging_table="stg_ohlcv_daily",
                merge_keys=["market", "exchange", "candle_date"],
                value_columns=[
                    "open_price", "high_price", "low_price", "close_price",
                    "volume", "trade_value",
                ],
            )
        logger.info("ohlcv_daily UPSERT: %d rows", count)
        return count

    # ── 분봉 데이터 ────────────────────────────

    def upsert_ohlcv_minute(self, df: pd.DataFrame) -> int:
        """분봉 OHLCV 데이터를 UPSERT합니다.

        Args:
            df: columns = [market, exchange, candle_dt, unit,
                           open_price, high_price, low_price, close_price,
                           volume, trade_value]

        Returns:
            영향 받은 행 수
        """
        with self.connection() as conn:
            count = self._upsert_via_staging(
                conn, df,
                target_table="ohlcv_minute",
                staging_table="stg_ohlcv_minute",
                merge_keys=["market", "exchange", "candle_dt", "unit"],
                value_columns=[
                    "open_price", "high_price", "low_price", "close_price",
                    "volume", "trade_value",
                ],
            )
        logger.info("ohlcv_minute UPSERT: %d rows", count)
        return count

    # ── 호가 데이터 ────────────────────────────

    def upsert_orderbook(self, df: pd.DataFrame) -> int:
        """호가 데이터를 UPSERT합니다.

        Args:
            df: columns = [market, exchange, timestamp_utc, level,
                           ask_price, ask_size, bid_price, bid_size,
                           total_ask_size, total_bid_size]

        Returns:
            영향 받은 행 수
        """
        with self.connection() as conn:
            count = self._upsert_via_staging(
                conn, df,
                target_table="orderbook",
                staging_table="stg_orderbook",
                merge_keys=["market", "exchange", "timestamp_utc", "level"],
                value_columns=[
                    "ask_price", "ask_size", "bid_price", "bid_size",
                    "total_ask_size", "total_bid_size",
                ],
            )
        logger.info("orderbook UPSERT: %d rows", count)
        return count

    # ── 체결 내역 ──────────────────────────────

    def upsert_trade_history(self, df: pd.DataFrame) -> int:
        """체결 내역을 UPSERT합니다.

        Args:
            df: columns = [market, exchange, trade_dt, side, price,
                           quantity, trade_value, order_id, fee]

        Returns:
            영향 받은 행 수
        """
        with self.connection() as conn:
            count = self._upsert_via_staging(
                conn, df,
                target_table="trade_history",
                staging_table="stg_trade_history",
                merge_keys=["market", "exchange", "trade_dt", "side", "price"],
                value_columns=[
                    "quantity", "trade_value", "order_id", "fee",
                ],
            )
        logger.info("trade_history UPSERT: %d rows", count)
        return count

    # ── 조회 ───────────────────────────────────

    def get_markets(self, exchange: str = "upbit", active_only: bool = True) -> pd.DataFrame:
        """등록된 마켓 목록을 조회합니다."""
        query = "SELECT * FROM dbo.market_info WHERE exchange = :exchange"
        if active_only:
            query += " AND is_active = 1"
        with self._engine.connect() as conn:
            return pd.read_sql(text(query), conn, params={"exchange": exchange})

    def get_ohlcv_daily(
        self,
        market: str,
        exchange: str = "upbit",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        """일봉 데이터를 조회합니다."""
        query = (
            "SELECT TOP(:limit) * FROM dbo.ohlcv_daily "
            "WHERE market = :market AND exchange = :exchange"
        )
        params = {"market": market, "exchange": exchange, "limit": limit}

        if start_date:
            query += " AND candle_date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            query += " AND candle_date <= :end_date"
            params["end_date"] = end_date

        query += " ORDER BY candle_date DESC"

        with self._engine.connect() as conn:
            return pd.read_sql(text(query), conn, params=params)

    def get_ohlcv_minute(
        self,
        market: str,
        exchange: str = "upbit",
        unit: int = 1,
        limit: int = 200,
    ) -> pd.DataFrame:
        """분봉 데이터를 조회합니다."""
        query = (
            "SELECT TOP(:limit) * FROM dbo.ohlcv_minute "
            "WHERE market = :market AND exchange = :exchange AND unit = :unit "
            "ORDER BY candle_dt DESC"
        )
        with self._engine.connect() as conn:
            return pd.read_sql(
                text(query), conn,
                params={"market": market, "exchange": exchange, "unit": unit, "limit": limit},
            )

    def get_latest_candle_date(self, market: str, exchange: str = "upbit") -> Optional[str]:
        """특정 마켓의 마지막 일봉 날짜를 반환합니다."""
        query = (
            "SELECT MAX(candle_date) as last_date FROM dbo.ohlcv_daily "
            "WHERE market = :market AND exchange = :exchange"
        )
        with self._engine.connect() as conn:
            result = conn.execute(text(query), {"market": market, "exchange": exchange})
            row = result.fetchone()
            if row and row[0]:
                return str(row[0])
        return None

    # ── 정리 ───────────────────────────────────

    def dispose(self):
        """엔진과 연결 풀을 정리합니다."""
        self._engine.dispose()
        logger.info("DB 엔진 종료")
