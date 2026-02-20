"""
백테스팅 모듈 (Backtester)
- SQL Server에서 과거 OHLCV 데이터를 로드하여 전략 성과를 검증
- 수익률, MDD, 샤프비율, 승률 등 핵심 지표 계산
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .strategies import Signal, Strategy, TradeSignal

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 데이터 로더 (SQL Server) — db_manager.DBManager 연동
# ──────────────────────────────────────────────
def load_ohlcv_from_db(
    market: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval: str = "daily",
    limit: int = 500,
) -> pd.DataFrame:
    """
    SQL Server에서 OHLCV 데이터를 로드합니다.
    db_manager.DBManager를 우선 사용하고, 실패 시 직접 연결합니다.

    Parameters:
        market: 마켓 코드 (예: 'KRW-BTC')
        start_date: 시작일 ('YYYY-MM-DD')
        end_date: 종료일 ('YYYY-MM-DD')
        interval: 'daily' 또는 'minute'
        limit: 최대 로드 행 수

    Returns:
        OHLCV DataFrame (columns: datetime, open, high, low, close, volume)
    """
    try:
        from .db_manager import DBManager
        db = DBManager()
    except Exception:
        logger.warning("DBManager 인스턴스 생성 실패 — fallback 연결 시도")
        db = None

    if db is not None:
        try:
            if interval == "daily":
                df = db.get_ohlcv_daily(
                    market=market,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
            else:
                df = db.get_ohlcv_minute(market=market, limit=limit)

            if df is not None and not df.empty:
                return _normalize_ohlcv(df)
        except Exception as e:
            logger.warning("DBManager 로드 실패: %s — fallback 연결 시도", e)

    # Fallback: 직접 SQL 연결
    return _load_ohlcv_direct(market, start_date, end_date, interval)


def _load_ohlcv_direct(
    market: str,
    start_date: Optional[str],
    end_date: Optional[str],
    interval: str,
) -> pd.DataFrame:
    """sqlalchemy 직접 연결로 OHLCV 로드"""
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        logger.error("sqlalchemy가 설치되지 않았습니다.")
        return pd.DataFrame()

    try:
        from .config import config
        conn_str = config.db.connection_string
    except Exception:
        server = r"CH-PC1\SQLEXPRESS"
        db_name = "CryptoDB"
        driver = "ODBC+Driver+17+for+SQL+Server"
        conn_str = (
            f"mssql+pyodbc://@{server}/{db_name}"
            f"?driver={driver}&Trusted_Connection=yes"
        )

    engine = create_engine(conn_str)

    # db_manager.py 스키마에 맞춘 컬럼명
    if interval == "daily":
        date_col = "candle_date"
        table = "ohlcv_daily"
    else:
        date_col = "candle_dt"
        table = "ohlcv_minute"

    query = f"SELECT * FROM dbo.{table} WHERE market = :market"
    params: Dict = {"market": market}

    if start_date:
        query += f" AND {date_col} >= :start_date"
        params["start_date"] = start_date
    if end_date:
        query += f" AND {date_col} <= :end_date"
        params["end_date"] = end_date

    query += f" ORDER BY {date_col} ASC"

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params=params)
        return _normalize_ohlcv(df)
    except Exception as e:
        logger.error("SQL 데이터 로드 실패: %s", e)
        return pd.DataFrame()


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """db_manager 스키마의 컬럼명을 표준 OHLCV 형식으로 변환"""
    col_map = {}
    for col in df.columns:
        lower = col.lower()
        if lower in ("candle_date", "candle_dt", "datetime", "date", "ts_utc",
                      "candle_date_time_utc", "timestamp"):
            col_map[col] = "datetime"
        elif lower in ("open_price", "open", "opening_price"):
            col_map[col] = "open"
        elif lower in ("high_price", "high"):
            col_map[col] = "high"
        elif lower in ("low_price", "low"):
            col_map[col] = "low"
        elif lower in ("close_price", "close", "trade_price"):
            col_map[col] = "close"
        elif lower in ("volume", "candle_acc_trade_volume", "acc_trade_volume"):
            col_map[col] = "volume"

    df = df.rename(columns=col_map)
    required = {"datetime", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        logger.warning("누락된 컬럼: %s", missing)
        for col in missing:
            df[col] = np.nan

    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


# ──────────────────────────────────────────────
# Upbit API Fallback 로더
# ──────────────────────────────────────────────
def load_ohlcv_from_api(
    market: str = "KRW-BTC",
    count: int = 200,
) -> pd.DataFrame:
    """
    SQL에 데이터가 없는 경우 Upbit REST API로 일봉 데이터를 로드합니다.
    """
    import requests

    url = "https://api.upbit.com/v1/candles/days"
    params = {"market": market, "count": min(count, 200)}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()

    rows = []
    for c in resp.json():
        rows.append({
            "datetime": c["candle_date_time_utc"],
            "open": c["opening_price"],
            "high": c["high_price"],
            "low": c["low_price"],
            "close": c["trade_price"],
            "volume": c["candle_acc_trade_volume"],
        })

    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


# ──────────────────────────────────────────────
# 매매 기록
# ──────────────────────────────────────────────
@dataclass
class Trade:
    entry_date: datetime
    exit_date: Optional[datetime]
    entry_price: float
    exit_price: float = 0.0
    side: str = "BUY"
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    reason_entry: str = ""
    reason_exit: str = ""


# ──────────────────────────────────────────────
# 성과 지표
# ──────────────────────────────────────────────
@dataclass
class BacktestResult:
    strategy_name: str
    market: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    sharpe_ratio: float
    avg_trade_pnl_pct: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: Optional[pd.Series] = None


def _calculate_metrics(
    trades: List[Trade],
    equity_curve: pd.Series,
    initial_capital: float,
    start_date: datetime,
    end_date: datetime,
) -> Dict:
    """거래 목록과 자산 곡선으로부터 성과 지표를 계산"""
    final = equity_curve.iloc[-1] if len(equity_curve) > 0 else initial_capital
    total_return = (final - initial_capital) / initial_capital * 100

    # 연환산 수익률
    days = (end_date - start_date).days
    if days > 0:
        annualized = ((final / initial_capital) ** (365 / days) - 1) * 100
    else:
        annualized = 0.0

    # MDD (Maximum Drawdown)
    cummax = equity_curve.cummax()
    drawdown = (equity_curve - cummax) / cummax
    max_dd = drawdown.min() * 100

    # 승률
    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl <= 0]
    win_rate = len(winning) / len(trades) * 100 if trades else 0.0

    # 평균 수익률
    avg_pnl = np.mean([t.pnl_pct for t in trades]) if trades else 0.0

    # 샤프비율 (일간 수익률 기준, 연환산)
    daily_returns = equity_curve.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    return {
        "final_capital": final,
        "total_return_pct": total_return,
        "annualized_return_pct": annualized,
        "max_drawdown_pct": max_dd,
        "win_rate": win_rate,
        "total_trades": len(trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "sharpe_ratio": sharpe,
        "avg_trade_pnl_pct": avg_pnl,
    }


# ──────────────────────────────────────────────
# 백테스터
# ──────────────────────────────────────────────
class Backtester:
    """
    전략을 과거 데이터에 적용하여 성과를 검증합니다.

    사용법:
        bt = Backtester(initial_capital=1_000_000, commission=0.0005)
        result = bt.run(strategy, df)
    """

    def __init__(
        self,
        initial_capital: float = 10_000_000,  # 1천만원
        commission: float = 0.0005,            # Upbit 수수료 0.05%
        slippage: float = 0.001,               # 슬리피지 0.1%
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def run(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        market: str = "unknown",
    ) -> BacktestResult:
        """
        주어진 전략으로 백테스트를 실행합니다.

        Parameters:
            strategy: 매매 전략 인스턴스
            df: OHLCV DataFrame (columns: datetime, open, high, low, close, volume)
            market: 마켓 코드

        Returns:
            BacktestResult
        """
        if df.empty or len(df) < 30:
            logger.warning("백테스트용 데이터가 부족합니다 (rows=%d)", len(df))
            return BacktestResult(
                strategy_name=strategy.name,
                market=market,
                start_date="", end_date="",
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
                total_return_pct=0, annualized_return_pct=0,
                max_drawdown_pct=0, win_rate=0,
                total_trades=0, winning_trades=0, losing_trades=0,
                sharpe_ratio=0, avg_trade_pnl_pct=0,
            )

        capital = self.initial_capital
        position = 0.0
        entry_price = 0.0
        entry_date = None
        trades: List[Trade] = []
        equity_list = []

        lookback_start = 30

        for i in range(lookback_start, len(df)):
            window = df.iloc[:i + 1].copy()
            current_price = df["close"].iloc[i]
            current_date = df["datetime"].iloc[i]

            equity = capital + position * current_price
            equity_list.append({"datetime": current_date, "equity": equity})

            try:
                sig = strategy.generate_signal(window)
            except Exception as e:
                logger.debug("시그널 생성 실패 (i=%d): %s", i, e)
                continue

            # 매수
            if sig.signal == Signal.BUY and position == 0 and capital > 0:
                buy_price = current_price * (1 + self.slippage)
                cost = capital * (1 - self.commission)
                position = cost / buy_price
                entry_price = buy_price
                entry_date = current_date
                capital = 0.0

            # 매도
            elif sig.signal == Signal.SELL and position > 0:
                sell_price = current_price * (1 - self.slippage)
                proceeds = position * sell_price * (1 - self.commission)
                pnl = proceeds - (position * entry_price)
                pnl_pct = (sell_price - entry_price) / entry_price * 100

                trades.append(Trade(
                    entry_date=entry_date,
                    exit_date=current_date,
                    entry_price=entry_price,
                    exit_price=sell_price,
                    side="BUY",
                    quantity=position,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    reason_entry=sig.reason,
                    reason_exit=sig.reason,
                ))

                capital = proceeds
                position = 0.0
                entry_price = 0.0
                entry_date = None

        # 잔여 포지션 청산
        if position > 0:
            last_price = df["close"].iloc[-1] * (1 - self.slippage)
            proceeds = position * last_price * (1 - self.commission)
            pnl = proceeds - (position * entry_price)
            pnl_pct = (last_price - entry_price) / entry_price * 100

            trades.append(Trade(
                entry_date=entry_date,
                exit_date=df["datetime"].iloc[-1],
                entry_price=entry_price,
                exit_price=last_price,
                side="BUY",
                quantity=position,
                pnl=pnl,
                pnl_pct=pnl_pct,
                reason_entry="",
                reason_exit="기간종료 청산",
            ))
            capital = proceeds
            position = 0.0

        # 자산곡선
        if equity_list:
            eq_df = pd.DataFrame(equity_list)
            equity_curve = eq_df.set_index("datetime")["equity"]
        else:
            equity_curve = pd.Series([self.initial_capital], name="equity")

        start_dt = df["datetime"].iloc[lookback_start]
        end_dt = df["datetime"].iloc[-1]

        metrics = _calculate_metrics(trades, equity_curve, self.initial_capital, start_dt, end_dt)

        return BacktestResult(
            strategy_name=strategy.name,
            market=market,
            start_date=str(start_dt.date()) if hasattr(start_dt, "date") else str(start_dt),
            end_date=str(end_dt.date()) if hasattr(end_dt, "date") else str(end_dt),
            initial_capital=self.initial_capital,
            trades=trades,
            equity_curve=equity_curve,
            **metrics,
        )

    def run_multiple(
        self,
        strategies: List[Strategy],
        df: pd.DataFrame,
        market: str = "unknown",
    ) -> pd.DataFrame:
        """
        여러 전략을 동일 데이터에 대해 백테스트하고 결과를 비교합니다.

        Returns:
            성과 비교 DataFrame
        """
        results = []
        for strat in strategies:
            logger.info("백테스팅: %s on %s", strat.name, market)
            r = self.run(strat, df, market)
            results.append({
                "strategy": r.strategy_name,
                "market": r.market,
                "period": f"{r.start_date} ~ {r.end_date}",
                "total_return_%": round(r.total_return_pct, 2),
                "annual_return_%": round(r.annualized_return_pct, 2),
                "mdd_%": round(r.max_drawdown_pct, 2),
                "win_rate_%": round(r.win_rate, 2),
                "total_trades": r.total_trades,
                "sharpe": round(r.sharpe_ratio, 2),
                "avg_pnl_%": round(r.avg_trade_pnl_pct, 2),
            })

        return pd.DataFrame(results)


# ──────────────────────────────────────────────
# 편의 함수: 빠른 백테스트 실행
# ──────────────────────────────────────────────
def quick_backtest(
    market: str = "KRW-BTC",
    initial_capital: float = 10_000_000,
    use_api: bool = False,
) -> pd.DataFrame:
    """
    기본 전략 5개로 빠른 백테스트를 실행합니다.

    Parameters:
        market: Upbit 마켓 코드
        initial_capital: 초기 자본금
        use_api: True면 Upbit API에서 데이터 로드, False면 SQL

    Returns:
        전략별 성과 비교 DataFrame
    """
    from .strategies import (
        BollingerBandStrategy,
        CombinedStrategy,
        GoldenCrossStrategy,
        MACDStrategy,
        RSIStrategy,
    )

    if use_api:
        df = load_ohlcv_from_api(market, count=200)
    else:
        df = load_ohlcv_from_db(market)

    if df.empty:
        logger.error("데이터 로드 실패: %s", market)
        return pd.DataFrame()

    strategies = [
        GoldenCrossStrategy(short_period=5, long_period=20),
        RSIStrategy(period=14, oversold=30, overbought=70),
        BollingerBandStrategy(period=20, num_std=2.0),
        MACDStrategy(fast=12, slow=26, signal_period=9),
        CombinedStrategy(),
    ]

    bt = Backtester(initial_capital=initial_capital)
    return bt.run_multiple(strategies, df, market)
