import pyupbit
import pandas as pd
from datetime import datetime, timedelta
import sys
import telegram
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
import numpy as np
import os
from telegram import Update
import yfinance as yf
import FinanceDataReader as fdr
from datetime import time as datetime_time
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional, Union

# dotenv 지원 (설치되어 있으면 사용)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 설정 클래스
@dataclass
class Config:
    """애플리케이션 설정"""
    # 분석 기간 설정 (일 단위)
    PERIODS: Dict[str, int] = field(default_factory=lambda: {
        '5년': 365 * 5,
        '3년': 365 * 3,
        '1년': 365,
        '1개월': 30,
        '1주일': 7,
        '3일': 3
    })

    # 보고서 설정
    TOP_N_STOCKS: int = 10  # 상위 N개 종목 표시

    # API 요청 설정
    REQUEST_DELAY: float = 0.1  # 요청 간 딜레이 (초)
    MAX_CONCURRENT_REQUESTS: int = 10  # 동시 요청 수
    MAX_RETRIES: int = 3  # 최대 재시도 횟수

    # 한국 주식 설정
    KOREAN_STOCK_LIMIT: int = 100  # 각 시장별 처리할 종목 수 (0 = 전체)


# 전역 설정 인스턴스
config = Config()

# 텔레그램 설정 (환경 변수에서 로드)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def validate_telegram_config():
    """텔레그램 설정 검증"""
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN 환경 변수가 설정되지 않았습니다.")
    if not TELEGRAM_CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID 환경 변수가 설정되지 않았습니다.")


class MarketDataCollector:
    """각 시장의 데이터를 수집하는 기본 클래스"""
    def __init__(self, market_name):
        self.market_name = market_name

    async def collect_data(self):
        """데이터 수집을 위한 추상 메서드"""
        raise NotImplementedError


class CryptoDataCollector(MarketDataCollector):
    """암호화폐 시장 데이터 수집기"""
    def __init__(self):
        super().__init__("암호화폐")

    async def collect_data(self):
        print(f"{self.market_name} 데이터 수집 시작...")
        return collect_crypto_data_parallel()


class GlobalStockDataCollector(MarketDataCollector):
    """글로벌 주식 시장 데이터 수집기"""
    def __init__(self):
        super().__init__("글로벌 주식")

    async def collect_data(self):
        print(f"{self.market_name} 데이터 수집 시작...")
        return collect_stock_data_parallel()


class KoreanStockDataCollector(MarketDataCollector):
    """한국 주식 시장 데이터 수집기"""
    def __init__(self):
        super().__init__("한국 주식")

    async def collect_data(self):
        print(f"{self.market_name} 데이터 수집 시작...")
        return collect_korean_stock_data_parallel()


class MarketReport:
    """시장 보고서 생성기"""
    def __init__(self, collector: MarketDataCollector):
        self.collector = collector
        self.currency_symbol = "₩" if isinstance(collector, (CryptoDataCollector, KoreanStockDataCollector)) else "$"

    async def generate_report(self):
        """보고서 생성 및 전송"""
        try:
            print(f"{self.collector.market_name} 보고서 생성 시작...")
            result_df = await self.collector.collect_data()

            # 하락률 메시지 생성
            drop_message = self._create_drop_message(result_df)
            await send_telegram_message(drop_message)

            # 상승률 메시지 생성
            rise_message = self._create_rise_message(result_df)
            await send_telegram_message(rise_message)

        except Exception as e:
            error_message = f"오류 발생: {str(e)}"
            print(f"보고서 생성 중 오류: {error_message}")
            await send_telegram_message(error_message)
            raise e

    def _create_drop_message(self, df):
        """하락률 메시지 생성"""
        message = f"<b>{self.collector.market_name} 고점대비 하락률 분석</b>\n\n"
        message += f"분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        if '시장' in df.columns:
            market_counts = df['시장'].value_counts()
            message += f"총 분석 종목 수: {len(df)}개\n"
            for market, count in market_counts.items():
                message += f"- {market}: {count}개\n"
        else:
            message += f"총 분석 종목 수: {len(df)}개\n"

        message += "\n<b>고점대비 하락률 상위</b>\n"

        periods = {
            '5년_고점대비': '5년',
            '3년_고점대비': '3년',
            '1년_고점대비': '1년',
            '1개월_고점대비': '1개월',
            '1주일_고점대비': '1주일',
            '3일_고점대비': '3일'
        }

        for period_key, period_name in periods.items():
            message += f"\n<b>{period_name} 고점대비 하락률 상위 종목</b>\n"
            period_data = df[df[period_key].notna()].nsmallest(config.TOP_N_STOCKS, period_key)
            for _, stock in period_data.iterrows():
                value = stock[period_key]
                current = stock['현재가']
                high = stock[f'{period_name}_고점']
                market = stock['시장'] if '시장' in stock else self.collector.market_name
                if pd.notna(value) and pd.notna(current) and pd.notna(high):
                    message += (f"[{market}] {stock['종목명']}: {value:.1f}% "
                              f"(현재가: {self.currency_symbol}{current:,.0f}, "
                              f"고점: {self.currency_symbol}{high:,.0f})\n")

        return message

    def _create_rise_message(self, df):
        """상승률 메시지 생성"""
        message = f"<b>{self.collector.market_name} 저점대비 상승률 분석</b>\n\n"
        message += f"분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        message += "<b>저점대비 상승률 상위</b>\n"

        periods = {
            '5년_고점대비': '5년',
            '3년_고점대비': '3년',
            '1년_고점대비': '1년',
            '1개월_고점대비': '1개월',
            '1주일_고점대비': '1주일',
            '3일_고점대비': '3일'
        }

        for period_key, period_name in periods.items():
            rise_key = period_key.replace('고점대비', '저점대비')
            message += f"\n<b>{period_name} 저점대비 상승률 상위 종목</b>\n"
            period_data = df[df[rise_key].notna()].nlargest(config.TOP_N_STOCKS, rise_key)
            for _, stock in period_data.iterrows():
                value = stock[rise_key]
                current = stock['현재가']
                low = stock[f'{period_name}_저점']
                market = stock['시장'] if '시장' in stock else self.collector.market_name
                if pd.notna(value) and pd.notna(current) and pd.notna(low):
                    message += (f"[{market}] {stock['종목명']}: {value:.1f}% "
                              f"(현재가: {self.currency_symbol}{current:,.0f}, "
                              f"저점: {self.currency_symbol}{low:,.0f})\n")

        return message


class SectorReport:
    """섹터별 수익률 보고서 생성기"""
    def __init__(self):
        self.sectors = {
            'XLK': 'Information Technology',
            'XLC': 'Communication Services',
            'XLY': 'Consumer Discretionary',
            'XLP': 'Consumer Staples',
            'XLE': 'Energy',
            'XLF': 'Financials',
            'XLV': 'Health Care',
            'XLI': 'Industrials',
            'XLB': 'Materials',
            'XLRE': 'Real Estate',
            'XLU': 'Utilities'
        }

        self.periods = {
            '3Y': ('3년', 1095),
            '1Y': ('1년', 365),
            '1M': ('1개월', 30),
            '1W': ('1주일', 7),
            '3D': ('3일', 3)
        }

    async def generate_report(self):
        try:
            sector_returns = await self._get_sector_returns()
            if sector_returns:
                message = self._create_sector_message(sector_returns)
                await send_telegram_message(message)
        except Exception as e:
            print(f"섹터 분석 중 오류 발생: {str(e)}")

    def _fetch_sector_data(self, sector_etf: str) -> Optional[pd.DataFrame]:
        """단일 섹터 ETF 데이터를 가져옵니다."""
        try:
            ticker = yf.Ticker(sector_etf)
            return ticker.history(period="3y")
        except Exception as e:
            print(f"Error fetching {sector_etf}: {str(e)}")
            return None

    async def _get_sector_returns(self):
        try:
            sector_returns = {}
            end_date = datetime.now()

            # 모든 섹터 데이터를 병렬로 한 번에 가져오기
            sector_data = {}
            with ThreadPoolExecutor(max_workers=len(self.sectors)) as executor:
                futures = {
                    executor.submit(self._fetch_sector_data, etf): (etf, name)
                    for etf, name in self.sectors.items()
                }

                for future in as_completed(futures):
                    etf, name = futures[future]
                    try:
                        data = future.result()
                        if data is not None and not data.empty:
                            sector_data[name] = data
                    except Exception as e:
                        print(f"Error processing {etf}: {str(e)}")

            # 각 기간별 수익률 계산
            for period_code, (period_name, days) in self.periods.items():
                start_date = end_date - timedelta(days=days)
                period_returns = {}

                for sector_name, hist in sector_data.items():
                    try:
                        period_hist = hist[hist.index >= start_date]
                        if not period_hist.empty and len(period_hist) > 1:
                            start_price = period_hist['Close'].iloc[0]
                            end_price = period_hist['Close'].iloc[-1]
                            returns = ((end_price - start_price) / start_price) * 100
                            period_returns[sector_name] = returns
                    except Exception as e:
                        print(f"Error calculating {sector_name} returns: {str(e)}")

                if period_returns:
                    sector_returns[period_code] = period_returns

            return sector_returns

        except Exception as e:
            print(f"Error getting sector returns: {str(e)}")
            return None

    def _create_sector_message(self, sector_returns):
        message = f"미국 섹터별 수익률 분석\n\n"
        message += f"분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        for period_code, (period_name, _) in self.periods.items():
            if period_code in sector_returns:
                message += f"{period_name} 수익률\n"
                sorted_returns = sorted(
                    sector_returns[period_code].items(),
                    key=lambda x: x[1],
                    reverse=True
                )

                for sector_name, returns in sorted_returns:
                    emoji = "+" if returns > 0 else ""
                    message += f"  {sector_name}: {emoji}{returns:.1f}%\n"
                message += "\n"

        return message


# 명령어 처리 함수들
async def btcreport_command(update, context):
    """암호화폐 보고서 생성 명령어를 처리합니다."""
    try:
        await update.message.reply_text("암호화폐 보고서 생성을 시작합니다. 잠시만 기다려주세요...")
        report = MarketReport(CryptoDataCollector())
        await report.generate_report()
        await update.message.reply_text("암호화폐 보고서 생성 및 전송이 완료되었습니다!")
    except Exception as e:
        await update.message.reply_text(f"보고서 생성 중 오류가 발생했습니다: {str(e)}")


async def btcreport_daily_command(update, context):
    """암호화폐 일일 보고서 생성 명령어를 처리합니다."""
    try:
        await update.message.reply_text("암호화폐 일일 보고서 생성을 시작합니다. 잠시만 기다려주세요...")
        report = CryptoDailyReport()
        await report.generate_report()
        await update.message.reply_text("암호화폐 일일 보고서 생성 및 전송이 완료되었습니다!")
    except Exception as e:
        await update.message.reply_text(f"보고서 생성 중 오류가 발생했습니다: {str(e)}")


async def stockreport_command(update, context):
    """주식 보고서 생성 명령어를 처리합니다."""
    try:
        await update.message.reply_text("주식 보고서 생성을 시작합니다. 잠시만 기다려주세요...")
        report = MarketReport(GlobalStockDataCollector())
        await report.generate_report()
        await update.message.reply_text("주식 보고서 생성 및 전송이 완료되었습니다!")
    except Exception as e:
        await update.message.reply_text(f"보고서 생성 중 오류가 발생했습니다: {str(e)}")


async def stockreport2_command(update, context):
    """한국 주식 보고서 생성 명령어를 처리합니다."""
    try:
        await update.message.reply_text("한국 주식 보고서 생성을 시작합니다. 잠시만 기다려주세요...")
        report = MarketReport(KoreanStockDataCollector())
        await report.generate_report()
        await update.message.reply_text("한국 주식 보고서 생성 및 전송이 완료되었습니다!")
    except Exception as e:
        await update.message.reply_text(f"보고서 생성 중 오류가 발생했습니다: {str(e)}")


async def sectorreport_command(update, context):
    """섹터 수익률 보고서 생성 명령어를 처리합니다."""
    try:
        await update.message.reply_text("섹터 수익률 보고서 생성을 시작합니다. 잠시만 기다려주세요...")
        report = SectorReport()
        await report.generate_report()
        await update.message.reply_text("섹터 수익률 보고서 생성 및 전송이 완료되었습니다!")
    except Exception as e:
        await update.message.reply_text(f"보고서 생성 중 오류가 발생했습니다: {str(e)}")


async def start_command(update, context):
    """시작 명령어를 처리합니다."""
    welcome_message = """시장 분석 봇 사용 설명서

사용 가능한 명령어:
/btcreport - 암호화폐 고점/저점 대비 보고서
/btcreport_daily - 암호화폐 일일 보고서 (전일대비, 거래대금)
/stockreport - 미국 주식 보고서
/stockreport2 - 한국 주식 보고서
/sectorreport - 섹터 수익률 보고서
/help - 도움말 표시

봇이 자동으로 매일 아침 7시 30분에 보고서를 전송합니다."""

    await update.message.reply_text(welcome_message)


async def help_command(update, context):
    """도움말을 표시합니다."""
    help_text = (
        "사용 가능한 명령어:\n\n"
        "/start - 봇 시작\n"
        "/help - 도움말 표시\n"
        "/btcreport - 암호화폐 고점/저점 대비 보고서\n"
        "/btcreport_daily - 암호화폐 일일 보고서\n"
        "/stockreport - 미국 주식 보고서\n"
        "/stockreport2 - 한국 주식 보고서\n"
        "/sectorreport - 섹터별 수익률 보고서"
    )
    await update.message.reply_text(help_text)


async def send_telegram_message(message):
    """텔레그램으로 메시지를 전송합니다."""
    validate_telegram_config()
    retry_delay = 10

    for attempt in range(config.MAX_RETRIES):
        try:
            bot = telegram.Bot(token=TELEGRAM_TOKEN)
            result = await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='HTML')
            print(f"메시지 전송 성공: {result.message_id}")
            return
        except Exception as e:
            print(f"메시지 전송 시도 {attempt + 1}/{config.MAX_RETRIES} 실패: {str(e)}")
            if attempt < config.MAX_RETRIES - 1:
                print(f"{retry_delay}초 후 재시도합니다...")
                await asyncio.sleep(retry_delay)
            else:
                print("최대 재시도 횟수를 초과했습니다.")
                raise e


def validate_price_data(df, col_prefix: str = '') -> bool:
    """가격 데이터 유효성 검사"""
    if df is None or df.empty:
        return False
    if col_prefix:
        required_cols = [f'{col_prefix}{col}' for col in ['Open', 'High', 'Low', 'Close']]
    else:
        required_cols = ['Open', 'High', 'Low', 'Close']
    return all(col in df.columns for col in required_cols)


def calculate_price_levels(df, high_col: str = 'high', low_col: str = 'low', close_col: str = 'close') -> Optional[dict]:
    """현재가 대비 과거 고점/저점 수준을 계산합니다.

    Args:
        df: 가격 데이터 DataFrame
        high_col: 고가 컬럼명
        low_col: 저가 컬럼명
        close_col: 종가 컬럼명

    Returns:
        계산된 가격 레벨 딕셔너리 또는 None
    """
    if df is None or len(df) == 0:
        return None

    try:
        current_price = float(df[close_col].iloc[-1])
    except (KeyError, IndexError):
        return None

    result = {'현재가': current_price}
    periods_items = list(config.PERIODS.items())

    for period_name, days in periods_items:
        if len(df) >= days:
            period_data = df.tail(days)
            high = float(period_data[high_col].max())
            low = float(period_data[low_col].min())

            result[f'{period_name}_고점'] = high
            result[f'{period_name}_저점'] = low
            result[f'{period_name}_고점대비'] = ((current_price - high) / high) * 100
            result[f'{period_name}_저점대비'] = ((current_price - low) / low) * 100
        else:
            result[f'{period_name}_고점'] = np.nan
            result[f'{period_name}_저점'] = np.nan
            result[f'{period_name}_고점대비'] = np.nan
            result[f'{period_name}_저점대비'] = np.nan

    return result


def fetch_single_crypto(ticker: str, retry_count: int = 3) -> Optional[dict]:
    """단일 암호화폐 데이터를 가져옵니다."""
    import time as time_module

    for attempt in range(retry_count):
        try:
            df = pyupbit.get_ohlcv(ticker, interval="day", count=365*5)
            if df is not None and not df.empty:
                levels = calculate_price_levels(df)
                if levels:
                    levels['종목명'] = ticker
                    levels['시장'] = 'UPBIT'
                    return levels
            # 데이터가 없으면 잠시 대기 후 재시도
            if attempt < retry_count - 1:
                time_module.sleep(0.2)
        except Exception as e:
            if attempt < retry_count - 1:
                time_module.sleep(0.3)
            else:
                print(f"Error fetching {ticker}: {str(e)}")
    return None


def collect_crypto_data_parallel():
    """암호화폐 데이터를 순차적으로 수집합니다 (API 제한 회피)."""
    import time as time_module

    tickers = pyupbit.get_tickers(fiat="KRW")
    results = []

    total = len(tickers)
    print(f"총 {total}개 암호화폐 데이터 수집 시작...")

    # pyupbit API는 rate limit이 있어서 순차 처리 + 딜레이 적용
    for idx, ticker in enumerate(tickers, 1):
        try:
            result = fetch_single_crypto(ticker)
            if result:
                results.append(result)
                print(f"[{idx}/{total}] {ticker} 완료")
            else:
                print(f"[{idx}/{total}] {ticker} 데이터 없음")
        except Exception as e:
            print(f"[{idx}/{total}] {ticker} 오류: {str(e)}")

        # API 제한 회피를 위한 딜레이
        if idx % 10 == 0:
            time_module.sleep(0.5)
        else:
            time_module.sleep(0.1)

    if not results:
        print("수집된 데이터가 없습니다.")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values('1년_고점대비', ascending=True)
    print(f"\n총 {len(result_df)}개 암호화폐 데이터 수집 완료")
    return result_df


def _fetch_prev_day_from_sql():
    """SQL Server에서 전일 OHLCV를 조회합니다. 실패 시 None 반환."""
    try:
        from sqlalchemy import create_engine, text as sa_text

        SQL_SERVER = r"CH-PC1\SQLEXPRESS"
        DB_NAME = "CryptoDB"
        ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

        conn_str = (
            f"mssql+pyodbc://@{SQL_SERVER}/{DB_NAME}"
            f"?driver={ODBC_DRIVER.replace(' ', '+')}"
            "&Trusted_Connection=yes&TrustServerCertificate=yes"
        )
        engine = create_engine(conn_str, pool_pre_ping=True, connect_args={"timeout": 5})

        query = sa_text("""
            WITH latest AS (
                SELECT MAX(candle_date) AS max_date
                FROM dbo.ohlcv_daily
                WHERE exchange = 'upbit' AND market LIKE 'KRW-%%'
                  AND candle_date < CAST(GETDATE() AS DATE)
            )
            SELECT d.market, d.high_price, d.low_price, d.close_price
            FROM dbo.ohlcv_daily d
            INNER JOIN latest l ON d.candle_date = l.max_date
            WHERE d.exchange = 'upbit' AND d.market LIKE 'KRW-%%'
        """)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        engine.dispose()

        if not df.empty:
            print(f"SQL Server 전일 데이터 조회 성공: {len(df)}개")
            return {
                row["market"]: {
                    "high": row["high_price"],
                    "low": row["low_price"],
                    "close": row["close_price"],
                }
                for _, row in df.iterrows()
            }
    except Exception as e:
        print(f"SQL Server 연결 실패 (API fallback 사용): {e}")
    return None


def _fetch_prev_day_from_api(api_session, markets):
    """Upbit API /v1/candles/days 로 전일 OHLCV를 조회합니다."""
    import time as time_module

    prev_data = {}
    total = len(markets)
    print(f"Upbit API에서 전일 데이터 조회 중... ({total}개)")

    for idx, market in enumerate(markets, 1):
        for attempt in range(3):
            try:
                resp = api_session.get(
                    "https://api.upbit.com/v1/candles/days",
                    params={"market": market, "count": 2},
                    timeout=10,
                )
                resp.raise_for_status()
                candles = resp.json()
                if len(candles) >= 2:
                    prev = candles[1]  # index 0=오늘, 1=전일
                    prev_data[market] = {
                        "high": prev["high_price"],
                        "low": prev["low_price"],
                        "close": prev["trade_price"],
                    }
                break
            except Exception:
                if attempt < 2:
                    time_module.sleep(0.3)

        # Upbit rate limit: 10 req/sec
        time_module.sleep(0.11)
        if idx % 50 == 0:
            print(f"  진행: {idx}/{total}")

    print(f"전일 데이터 조회 완료: {len(prev_data)}개")
    return prev_data


def collect_crypto_daily_data_from_sql() -> pd.DataFrame:
    """전일 고/저/종가 + 현재가로 일일 모멘텀 데이터를 수집합니다.
    SQL Server 우선, 실패 시 Upbit API fallback."""
    import time as time_module
    import requests as req

    UPBIT_BASE = "https://api.upbit.com/v1"

    api_session = req.Session()
    api_session.headers.update({"Accept": "application/json"})

    # 1) 마켓 목록 + 한글명 조회
    print("마켓 목록 조회 중...")
    resp = api_session.get(f"{UPBIT_BASE}/market/all", params={"is_details": "true"}, timeout=10)
    resp.raise_for_status()
    krw_markets = [item for item in resp.json() if item["market"].startswith("KRW-")]
    name_map = {item["market"]: item.get("korean_name", "") for item in krw_markets}
    markets = list(name_map.keys())
    print(f"KRW 마켓: {len(markets)}개")

    # 2) 전일 데이터 (SQL 우선, 실패 시 API)
    prev_data = _fetch_prev_day_from_sql()
    if prev_data is None:
        prev_data = _fetch_prev_day_from_api(api_session, markets)

    if not prev_data:
        print("전일 데이터를 가져올 수 없습니다.")
        return pd.DataFrame()

    # 3) 현재가 조회 (배치)
    print("현재가 조회 중...")
    ticker_map = {}
    target_markets = [m for m in markets if m in prev_data]
    for i in range(0, len(target_markets), 100):
        batch = target_markets[i:i+100]
        resp = api_session.get(
            f"{UPBIT_BASE}/ticker",
            params={"markets": ",".join(batch)},
            timeout=10,
        )
        resp.raise_for_status()
        for item in resp.json():
            ticker_map[item["market"]] = item
        if i + 100 < len(target_markets):
            time_module.sleep(0.12)

    print(f"현재가 조회 완료: {len(ticker_map)}개")

    # 4) 분석
    results = []
    for market in target_markets:
        if market not in ticker_map:
            continue

        ticker = ticker_map[market]
        current_price = ticker["trade_price"]
        prev = prev_data[market]
        prev_high = prev["high"]
        prev_low = prev["low"]
        prev_close = prev["close"]
        trade_value_24h = ticker.get("acc_trade_price_24h", 0)

        chg_from_low = ((current_price - prev_low) / prev_low) * 100 if prev_low > 0 else 0
        chg_from_high = ((current_price - prev_high) / prev_high) * 100 if prev_high > 0 else 0
        chg_from_close = ((current_price - prev_close) / prev_close) * 100 if prev_close > 0 else 0

        results.append({
            "종목명": market,
            "한글명": name_map.get(market, ""),
            "현재가": current_price,
            "전일고점": prev_high,
            "전일저점": prev_low,
            "전일종가": prev_close,
            "전일고점대비": round(chg_from_high, 2),
            "전일저점대비": round(chg_from_low, 2),
            "변동률": round(chg_from_close, 2),
            "거래대금": trade_value_24h,
        })

    result_df = pd.DataFrame(results)
    print(f"총 {len(result_df)}개 종목 분석 완료")
    return result_df


class CryptoDailyReport:
    """암호화폐 일일 보고서 생성기 (SQL 전일 데이터 + API 현재가)"""

    def __init__(self):
        self.market_name = "암호화폐 일일"

    async def generate_report(self):
        """일일 보고서 생성 및 전송"""
        try:
            print(f"{self.market_name} 보고서 생성 시작...")
            result_df = collect_crypto_daily_data_from_sql()

            if result_df.empty:
                await send_telegram_message("데이터 수집에 실패했습니다.")
                return

            messages = self._create_daily_messages(result_df)
            for msg in messages:
                await send_telegram_message(msg)

        except Exception as e:
            error_message = f"일일 보고서 오류: {str(e)}"
            print(error_message)
            await send_telegram_message(error_message)
            raise e

    def _fmt_vol(self, v):
        b = v / 1e8
        if b >= 1:
            return f"{b:,.0f}억"
        return f"{v/1e4:,.0f}만"

    def _create_daily_messages(self, df: pd.DataFrame) -> List[str]:
        """일일 보고서 메시지 생성 (텔레그램 모바일 1줄 최적화)"""
        messages = []
        up_count = (df["변동률"] > 0).sum()
        down_count = (df["변동률"] < 0).sum()
        flat_count = (df["변동률"] == 0).sum()

        # ── 저가 대비 오름폭 상위 20 ──
        top_up = df.nlargest(20, "전일저점대비")
        msg = "<b>저가대비 오름폭 TOP20</b>\n"
        msg += f"상승{up_count} 하락{down_count} 보합{flat_count}\n"
        msg += "<pre>"
        msg += "종목   현재가  저가  고가\n"
        msg += "-------------------------\n"
        for _, r in top_up.iterrows():
            tk = r["종목명"].replace("KRW-", "")[:6]
            p = r['현재가']
            if p >= 1000:
                pf = f"{p:,.0f}"
            elif p >= 1:
                pf = f"{p:.1f}"
            else:
                pf = f"{p:.4f}"
            msg += (f"{tk:<6}"
                    f"{pf:>8}"
                    f"{r['전일저점대비']:>+6.1f}"
                    f"{r['전일고점대비']:>+6.1f}\n")
        msg += "</pre>"
        messages.append(msg)

        # ── 고가 대비 하락폭 상위 20 ──
        top_down = df.nsmallest(20, "전일고점대비")
        msg2 = "<b>고가대비 하락폭 TOP20</b>\n"
        msg2 += "<pre>"
        msg2 += "종목   현재가  고가  저가\n"
        msg2 += "-------------------------\n"
        for _, r in top_down.iterrows():
            tk = r["종목명"].replace("KRW-", "")[:6]
            p = r['현재가']
            if p >= 1000:
                pf = f"{p:,.0f}"
            elif p >= 1:
                pf = f"{p:.1f}"
            else:
                pf = f"{p:.4f}"
            msg2 += (f"{tk:<6}"
                     f"{pf:>8}"
                     f"{r['전일고점대비']:>+6.1f}"
                     f"{r['전일저점대비']:>+6.1f}\n")
        msg2 += "</pre>"
        messages.append(msg2)

        # ── 시장 요약 ──
        total_vol = df["거래대금"].sum()
        msg3 = "<b>시장 요약</b>\n"
        msg3 += f"총 {len(df)}종목\n"
        msg3 += f"상승{up_count} 하락{down_count} 보합{flat_count}\n"
        msg3 += f"종가대비 평균: {df['변동률'].mean():+.2f}%\n"
        msg3 += f"저가대비 평균: {df['전일저점대비'].mean():+.2f}%\n"
        msg3 += f"고가대비 평균: {df['전일고점대비'].mean():+.2f}%\n"
        msg3 += f"24h 거래대금: {total_vol/1e8:,.0f}억원\n"
        messages.append(msg3)

        return messages


def get_stock_tickers():
    """S&P500과 NASDAQ100 종목들의 티커를 가져옵니다."""
    try:
        # S&P500 종목 가져오기
        sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        sp500_df = pd.read_html(sp500_url)[0]
        sp500_tickers = sp500_df['Symbol'].tolist()

        # NASDAQ100 종목 가져오기
        nasdaq_url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(nasdaq_url)

        nasdaq_tickers = []
        for table in tables:
            if 'Symbol' in table.columns:
                nasdaq_tickers = table['Symbol'].tolist()
                break
            elif 'Ticker' in table.columns:
                nasdaq_tickers = table['Ticker'].tolist()
                break

        # 두 리스트 합치기 및 중복 제거
        all_tickers = list(set(sp500_tickers + nasdaq_tickers))
        all_tickers = [ticker.replace('.', '-').strip() for ticker in all_tickers if isinstance(ticker, str)]
        all_tickers = sorted(all_tickers)

        return all_tickers
    except Exception as e:
        print(f"주식 티커 가져오기 실패: {str(e)}")
        raise e


def get_stock_historical_data(ticker: str) -> Optional[pd.DataFrame]:
    """특정 주식의 과거 데이터를 가져옵니다."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="5y")

        if df is not None and not df.empty and len(df) > 0:
            df = df.reset_index()
            return df

        return None
    except Exception as e:
        print(f"Error fetching data for {ticker}: {str(e)}")
        return None


def fetch_single_stock(ticker: str, market: str = 'US') -> Optional[dict]:
    """단일 주식 데이터를 가져옵니다."""
    try:
        df = get_stock_historical_data(ticker)
        if df is not None and not df.empty:
            levels = calculate_price_levels(df, high_col='High', low_col='Low', close_col='Close')
            if levels:
                levels['종목명'] = ticker
                levels['시장'] = market
                return levels
    except Exception as e:
        print(f"Error processing {ticker}: {str(e)}")
    return None


def collect_stock_data_parallel():
    """주식 데이터를 병렬로 수집합니다."""
    tickers = get_stock_tickers()
    results = []

    total = len(tickers)
    print(f"총 {total}개 주식 데이터 수집 시작...")

    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        futures = {executor.submit(fetch_single_stock, ticker, 'US'): ticker for ticker in tickers}

        for idx, future in enumerate(as_completed(futures), 1):
            ticker = futures[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                    print(f"[{idx}/{total}] {ticker} 완료")
                else:
                    print(f"[{idx}/{total}] {ticker} 데이터 없음")
            except Exception as e:
                print(f"[{idx}/{total}] {ticker} 오류: {str(e)}")

    if not results:
        print("주의: 수집된 주식 데이터가 없습니다.")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values('1년_고점대비', ascending=True)

    print(f"\n총 {len(result_df)}개 종목의 데이터 수집 완료")
    return result_df


def get_korean_stock_tickers():
    """코스피와 코스닥 종목들의 티커를 가져옵니다."""
    try:
        # 코스피 종목 가져오기
        kospi = fdr.StockListing('KOSPI')
        kospi_data = [(f"{code}.KS", name) for code, name in zip(kospi['Code'].astype(str).str.zfill(6), kospi['Name'])]

        # 코스닥 종목 가져오기
        kosdaq = fdr.StockListing('KOSDAQ')
        kosdaq_data = [(f"{code}.KQ", name) for code, name in zip(kosdaq['Code'].astype(str).str.zfill(6), kosdaq['Name'])]

        return kospi_data, kosdaq_data

    except Exception as e:
        print(f"한국 주식 티커 가져오기 실패: {str(e)}")
        raise e


def fetch_single_korean_stock(ticker_info: Tuple[str, str], market: str) -> Optional[dict]:
    """단일 한국 주식 데이터를 가져옵니다."""
    ticker, name = ticker_info
    try:
        df = get_stock_historical_data(ticker)
        if df is not None and not df.empty:
            levels = calculate_price_levels(df, high_col='High', low_col='Low', close_col='Close')
            if levels:
                levels['종목명'] = f"{name} ({ticker})"
                levels['시장'] = market
                return levels
    except Exception as e:
        print(f"Error processing {ticker}: {str(e)}")
    return None


def collect_korean_stock_data_parallel():
    """한국 주식 데이터를 병렬로 수집합니다."""
    kospi_tickers, kosdaq_tickers = get_korean_stock_tickers()

    # 종목 수 제한 적용 (0이면 전체)
    limit = config.KOREAN_STOCK_LIMIT
    if limit > 0:
        kospi_tickers = kospi_tickers[:limit]
        kosdaq_tickers = kosdaq_tickers[:limit]

    # 모든 종목을 하나의 리스트로 통합 (시장 정보 포함)
    all_tickers = [(ticker_info, 'KOSPI') for ticker_info in kospi_tickers]
    all_tickers += [(ticker_info, 'KOSDAQ') for ticker_info in kosdaq_tickers]

    total = len(all_tickers)
    print(f"\n한국 주식 데이터 처리 중... (KOSPI: {len(kospi_tickers)}개, KOSDAQ: {len(kosdaq_tickers)}개, 총: {total}개)")

    results = []

    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_REQUESTS) as executor:
        futures = {
            executor.submit(fetch_single_korean_stock, ticker_info, market): (ticker_info[0], market)
            for ticker_info, market in all_tickers
        }

        for idx, future in enumerate(as_completed(futures), 1):
            ticker, market = futures[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
                    print(f"[{market} {idx}/{total}] {ticker} 완료")
                else:
                    print(f"[{market} {idx}/{total}] {ticker} 데이터 없음")
            except Exception as e:
                print(f"[{market} {idx}/{total}] {ticker} 오류: {str(e)}")

    if not results:
        raise Exception("수집된 데이터가 없습니다. 모든 시도가 실패했습니다.")

    print(f"\n총 {len(results)}개 종목 데이터 수집 완료")
    return pd.DataFrame(results)


async def send_daily_korean_stock_report():
    """일일 한국 주식 보고서를 생성하고 텔레그램으로 전송합니다."""
    try:
        print("한국 주식 보고서 생성 시작...")
        report = MarketReport(KoreanStockDataCollector())
        await report.generate_report()
    except Exception as e:
        error_message = f"오류 발생: {str(e)}"
        print(f"보고서 생성 중 오류: {error_message}")
        try:
            await send_telegram_message(error_message)
        except Exception as e2:
            print(f"오류 메시지 전송 실패: {str(e2)}")
        raise e


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "telegram":
            print("텔레그램 봇 시작...")

            # 환경 변수 검증
            try:
                validate_telegram_config()
            except ValueError as e:
                print(f"설정 오류: {str(e)}")
                print("TELEGRAM_TOKEN과 TELEGRAM_CHAT_ID 환경 변수를 설정하거나 .env 파일을 생성하세요.")
                sys.exit(1)

            # Windows에서 이벤트 루프 정책 설정
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

            try:
                # 봇 설정
                application = (
                    Application.builder()
                    .token(TELEGRAM_TOKEN)
                    .get_updates_read_timeout(30)
                    .get_updates_write_timeout(30)
                    .get_updates_connect_timeout(30)
                    .get_updates_pool_timeout(None)
                    .build()
                )

                # 에러 핸들러 추가
                async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
                    print(f"봇에서 오류 발생: {context.error}")
                    if isinstance(context.error, telegram.error.Conflict):
                        print("다른 봇 인스턴스가 실행 중입니다. 프로그램을 종료합니다.")
                        if application.running:
                            await application.stop()
                        return

                application.add_error_handler(error_handler)

                # 명령어 핸들러 등록
                application.add_handler(CommandHandler("start", start_command))
                application.add_handler(CommandHandler("help", help_command))
                application.add_handler(CommandHandler("btcreport", btcreport_command))
                application.add_handler(CommandHandler("btcreport_daily", btcreport_daily_command))
                application.add_handler(CommandHandler("stockreport", stockreport_command))
                application.add_handler(CommandHandler("stockreport2", stockreport2_command))
                application.add_handler(CommandHandler("sectorreport", sectorreport_command))

                # 스케줄러 설정
                async def scheduled_job(context):
                    try:
                        if hasattr(context.application, 'running_task'):
                            try:
                                context.application.running_task.cancel()
                            except:
                                pass
                            print("기존 예약 작업을 중단하고 새로운 작업을 시작합니다...")

                        task = asyncio.create_task(send_daily_korean_stock_report())
                        context.application.running_task = task
                        await task
                    except asyncio.CancelledError:
                        print("예약 작업이 취소되었습니다.")
                    except Exception as e:
                        print(f"스케줄 실행 중 오류 발생: {str(e)}")
                    finally:
                        if hasattr(context.application, 'running_task'):
                            delattr(context.application, 'running_task')

                print("텔레그램 봇이 시작되었습니다.")
                print("사용 가능한 명령어: /start, /help, /btcreport, /btcreport_daily, /stockreport, /stockreport2, /sectorreport")

                # 매일 7시 30분에 실행되도록 스케줄 설정
                daily_time = datetime_time(7, 30)
                application.job_queue.run_daily(scheduled_job, time=daily_time)

                # 봇 실행
                print("봇 폴링 시작...")
                application.run_polling(
                    drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES,
                    stop_signals=None
                )

            except KeyboardInterrupt:
                print("\n키보드 인터럽트 감지: 봇을 종료합니다...")
            except Exception as e:
                print(f"봇 실행 중 오류 발생: {str(e)}")
                import traceback
                traceback.print_exc()
            finally:
                print("봇을 종료합니다...")
        else:
            print("사용법: python upbit_cursor.py [telegram]")
    else:
        print("사용법: python upbit_cursor.py [telegram]")
