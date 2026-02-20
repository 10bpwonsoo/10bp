"""
데이터 수집 모듈 - Upbit / Binance API에서 OHLCV, 호가, 체결 데이터를 수집하여 DB에 적재

주요 기능:
  - Upbit KRW 마켓 전체 코인 일봉/분봉 OHLCV 수집
  - Binance USDT 마켓 글로벌 시세 수집
  - 호가(orderbook) 수집
  - 에러 핸들링, 재시도 로직, 로깅
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd
import requests

from .config import config
from .db_manager import DBManager

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# Upbit 데이터 수집기
# ═══════════════════════════════════════════════

class UpbitCollector:
    """Upbit REST API를 사용한 데이터 수집기"""

    BASE_URL = "https://api.upbit.com/v1"

    def __init__(self, db: Optional[DBManager] = None):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    # ── API 요청 헬퍼 ─────────────────────────

    def _request(self, endpoint: str, params: Optional[dict] = None) -> list:
        """API 요청 + 재시도 로직"""
        url = f"{self.BASE_URL}{endpoint}"
        last_error = None

        for attempt in range(1, config.collector.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=10)
                resp.raise_for_status()

                remaining = resp.headers.get("Remaining-Req", "")
                if remaining:
                    self._check_rate_limit(remaining)

                return resp.json()
            except requests.exceptions.HTTPError as e:
                last_error = e
                if resp.status_code == 429:
                    wait = config.collector.retry_delay * attempt * 2
                    logger.warning("Rate limit 초과, %0.1f초 대기 (시도 %d/%d)",
                                   wait, attempt, config.collector.max_retries)
                    time.sleep(wait)
                elif resp.status_code >= 500:
                    logger.warning("서버 오류 %d, 재시도 %d/%d",
                                   resp.status_code, attempt, config.collector.max_retries)
                    time.sleep(config.collector.retry_delay * attempt)
                else:
                    raise
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning("요청 실패: %s (시도 %d/%d)",
                               str(e), attempt, config.collector.max_retries)
                time.sleep(config.collector.retry_delay * attempt)

        raise last_error

    def _check_rate_limit(self, remaining_header: str):
        """Remaining-Req 헤더를 파싱하여 rate limit이 낮으면 대기"""
        try:
            parts = dict(
                item.strip().split("=")
                for item in remaining_header.split(";")
                if "=" in item
            )
            sec_remaining = int(parts.get("sec", "10"))
            if sec_remaining <= 1:
                time.sleep(0.5)
        except (ValueError, KeyError):
            pass

    # ── 마켓 정보 ──────────────────────────────

    def fetch_markets(self, fiat: str = "KRW") -> pd.DataFrame:
        """Upbit 마켓 정보를 가져옵니다.

        Args:
            fiat: 필터링할 기축통화 ("KRW", "BTC", "USDT" 또는 None=전체)

        Returns:
            DataFrame[market, korean_name, english_name, exchange, market_type, is_active]
        """
        data = self._request("/market/all", {"is_details": "true"})
        rows = []
        for item in data:
            market = item["market"]
            if fiat and not market.startswith(f"{fiat}-"):
                continue
            rows.append({
                "market": market,
                "korean_name": item.get("korean_name", ""),
                "english_name": item.get("english_name", ""),
                "exchange": "upbit",
                "market_type": market.split("-")[0],
                "is_active": 1,
            })

        df = pd.DataFrame(rows)
        logger.info("Upbit %s 마켓 %d개 조회", fiat, len(df))
        return df

    # ── 일봉 OHLCV ────────────────────────────

    def fetch_daily_ohlcv(self, market: str, count: int = 200, to: Optional[str] = None) -> pd.DataFrame:
        """특정 마켓의 일봉 데이터를 가져옵니다.

        Args:
            market: 마켓 코드 (예: "KRW-BTC")
            count: 캔들 수 (최대 200)
            to: 마지막 캔들 기준 시각 (ISO 8601, 예: "2024-01-01T00:00:00")

        Returns:
            DataFrame[market, exchange, candle_date,
                       open_price, high_price, low_price, close_price,
                       volume, trade_value]
        """
        params = {"market": market, "count": min(count, 200)}
        if to:
            params["to"] = to

        data = self._request("/candles/days", params)
        if not data:
            return pd.DataFrame()

        rows = []
        for c in data:
            rows.append({
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

        return pd.DataFrame(rows)

    # ── 분봉 OHLCV ────────────────────────────

    def fetch_minute_ohlcv(
        self,
        market: str,
        unit: int = 1,
        count: int = 200,
        to: Optional[str] = None,
    ) -> pd.DataFrame:
        """특정 마켓의 분봉 데이터를 가져옵니다.

        Args:
            market: 마켓 코드
            unit: 분봉 단위 (1, 3, 5, 10, 15, 30, 60, 240)
            count: 캔들 수 (최대 200)
            to: 마지막 캔들 기준 시각

        Returns:
            DataFrame[market, exchange, candle_dt, unit,
                       open_price, high_price, low_price, close_price,
                       volume, trade_value]
        """
        params = {"market": market, "count": min(count, 200)}
        if to:
            params["to"] = to

        data = self._request(f"/candles/minutes/{unit}", params)
        if not data:
            return pd.DataFrame()

        rows = []
        for c in data:
            rows.append({
                "market": market,
                "exchange": "upbit",
                "candle_dt": c["candle_date_time_kst"].replace("T", " ")[:19],
                "unit": unit,
                "open_price": c["opening_price"],
                "high_price": c["high_price"],
                "low_price": c["low_price"],
                "close_price": c["trade_price"],
                "volume": c.get("candle_acc_trade_volume", 0),
                "trade_value": c.get("candle_acc_trade_price", 0),
            })

        return pd.DataFrame(rows)

    # ── 호가 ───────────────────────────────────

    def fetch_orderbook(self, markets: List[str]) -> pd.DataFrame:
        """호가 데이터를 가져옵니다.

        Args:
            markets: 마켓 코드 리스트 (최대 15개)

        Returns:
            DataFrame[market, exchange, timestamp_utc, level,
                       ask_price, ask_size, bid_price, bid_size,
                       total_ask_size, total_bid_size]
        """
        all_rows = []

        for i in range(0, len(markets), 15):
            batch = markets[i:i + 15]
            data = self._request("/orderbook", {"markets": ",".join(batch)})

            for item in data:
                mkt = item["market"]
                ts = datetime.fromtimestamp(
                    item["timestamp"] / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S.%f")[:23]
                total_ask = item.get("total_ask_size", 0)
                total_bid = item.get("total_bid_size", 0)

                for level, unit in enumerate(item.get("orderbook_units", []), start=1):
                    all_rows.append({
                        "market": mkt,
                        "exchange": "upbit",
                        "timestamp_utc": ts,
                        "level": level,
                        "ask_price": unit["ask_price"],
                        "ask_size": unit["ask_size"],
                        "bid_price": unit["bid_price"],
                        "bid_size": unit["bid_size"],
                        "total_ask_size": total_ask,
                        "total_bid_size": total_bid,
                    })

            if i + 15 < len(markets):
                time.sleep(config.collector.request_delay)

        return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()

    # ── 현재가(Ticker) ─────────────────────────

    def fetch_tickers(self, markets: List[str]) -> pd.DataFrame:
        """현재가 데이터를 가져옵니다 (최대 100개씩 배치)."""
        all_rows = []

        for i in range(0, len(markets), 100):
            batch = markets[i:i + 100]
            data = self._request("/ticker", {"markets": ",".join(batch)})

            ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            for item in data:
                all_rows.append({
                    "market": item["market"],
                    "trade_price": item["trade_price"],
                    "signed_change_rate": item.get("signed_change_rate", 0),
                    "acc_trade_price_24h": item.get("acc_trade_price_24h", 0),
                    "acc_trade_volume_24h": item.get("acc_trade_volume_24h", 0),
                    "highest_52_week_price": item.get("highest_52_week_price", 0),
                    "lowest_52_week_price": item.get("lowest_52_week_price", 0),
                    "timestamp_utc": ts_utc,
                })

            if i + 100 < len(markets):
                time.sleep(config.collector.request_delay)

        return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()

    # ── 전체 수집 + DB 적재 ────────────────────

    def collect_all_daily(self, fiat: str = "KRW") -> Dict[str, int]:
        """KRW 마켓 전체의 일봉 데이터를 수집하여 DB에 적재합니다.

        Returns:
            {"markets": 마켓 수, "rows": 적재 행 수}
        """
        markets_df = self.fetch_markets(fiat)
        market_list = markets_df["market"].tolist()

        if self.db:
            self.db.upsert_market_info(markets_df)

        all_ohlcv = []
        total = len(market_list)
        for idx, market in enumerate(market_list, 1):
            try:
                df = self.fetch_daily_ohlcv(market, count=config.collector.daily_count)
                if not df.empty:
                    all_ohlcv.append(df)
                    logger.info("[%d/%d] %s 일봉 %d건", idx, total, market, len(df))
                else:
                    logger.debug("[%d/%d] %s 데이터 없음", idx, total, market)
            except Exception as e:
                logger.error("[%d/%d] %s 수집 실패: %s", idx, total, market, str(e))

            time.sleep(config.collector.request_delay)

        if not all_ohlcv:
            logger.warning("수집된 일봉 데이터가 없습니다")
            return {"markets": total, "rows": 0}

        combined = pd.concat(all_ohlcv, ignore_index=True)
        rows = 0
        if self.db:
            rows = self.db.upsert_ohlcv_daily(combined)

        logger.info("일봉 수집 완료: %d 마켓, %d 행 적재", total, rows)
        return {"markets": total, "rows": rows}

    def collect_all_minute(self, fiat: str = "KRW", unit: int = 1) -> Dict[str, int]:
        """KRW 마켓 전체의 분봉 데이터를 수집하여 DB에 적재합니다.

        Returns:
            {"markets": 마켓 수, "rows": 적재 행 수}
        """
        markets_df = self.fetch_markets(fiat)
        market_list = markets_df["market"].tolist()

        all_ohlcv = []
        total = len(market_list)
        for idx, market in enumerate(market_list, 1):
            try:
                df = self.fetch_minute_ohlcv(
                    market, unit=unit, count=config.collector.minute_count,
                )
                if not df.empty:
                    all_ohlcv.append(df)
                    logger.info("[%d/%d] %s %d분봉 %d건", idx, total, market, unit, len(df))
            except Exception as e:
                logger.error("[%d/%d] %s 수집 실패: %s", idx, total, market, str(e))

            time.sleep(config.collector.request_delay)

        if not all_ohlcv:
            logger.warning("수집된 분봉 데이터가 없습니다")
            return {"markets": total, "rows": 0}

        combined = pd.concat(all_ohlcv, ignore_index=True)
        rows = 0
        if self.db:
            rows = self.db.upsert_ohlcv_minute(combined)

        logger.info("%d분봉 수집 완료: %d 마켓, %d 행 적재", unit, total, rows)
        return {"markets": total, "rows": rows}

    def collect_orderbook(self, fiat: str = "KRW") -> Dict[str, int]:
        """KRW 마켓 전체의 호가 데이터를 수집하여 DB에 적재합니다."""
        markets_df = self.fetch_markets(fiat)
        market_list = markets_df["market"].tolist()

        df = self.fetch_orderbook(market_list)
        rows = 0
        if self.db and not df.empty:
            rows = self.db.upsert_orderbook(df)

        logger.info("호가 수집 완료: %d 마켓, %d 행 적재", len(market_list), rows)
        return {"markets": len(market_list), "rows": rows}


# ═══════════════════════════════════════════════
# Binance 데이터 수집기
# ═══════════════════════════════════════════════

class BinanceCollector:
    """Binance REST API를 사용한 글로벌 시세 수집기"""

    BASE_URL = "https://api.binance.com/api/v3"

    def __init__(self, db: Optional[DBManager] = None):
        self.db = db
        self.session = requests.Session()

    # ── API 요청 헬퍼 ─────────────────────────

    def _request(self, endpoint: str, params: Optional[dict] = None) -> list:
        """API 요청 + 재시도"""
        url = f"{self.BASE_URL}{endpoint}"
        last_error = None

        for attempt in range(1, config.collector.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=10)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.HTTPError as e:
                last_error = e
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    logger.warning("Binance rate limit, %d초 대기", retry_after)
                    time.sleep(retry_after)
                elif resp.status_code >= 500:
                    time.sleep(config.collector.retry_delay * attempt)
                else:
                    raise
            except requests.exceptions.RequestException as e:
                last_error = e
                time.sleep(config.collector.retry_delay * attempt)

        raise last_error

    # ── 마켓 정보 ──────────────────────────────

    def fetch_markets(self, quote: str = "USDT") -> pd.DataFrame:
        """Binance 거래쌍 정보를 가져옵니다."""
        data = self._request("/exchangeInfo")
        rows = []
        for sym in data.get("symbols", []):
            if sym["quoteAsset"] == quote and sym["status"] == "TRADING":
                rows.append({
                    "market": sym["symbol"],
                    "korean_name": "",
                    "english_name": sym["baseAsset"],
                    "exchange": "binance",
                    "market_type": quote,
                    "is_active": 1,
                })
        df = pd.DataFrame(rows)
        logger.info("Binance %s 마켓 %d개 조회", quote, len(df))
        return df

    # ── 일봉 OHLCV ────────────────────────────

    def _fetch_single_klines(self, symbol: str, interval: str = "1d", limit: int = 200) -> pd.DataFrame:
        """단일 심볼의 klines 데이터를 가져옵니다."""
        data = self._request("/klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        })
        if not data:
            return pd.DataFrame()

        rows = []
        for k in data:
            rows.append({
                "market": symbol,
                "exchange": "binance",
                "candle_date": datetime.fromtimestamp(
                    k[0] / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d"),
                "open_price": float(k[1]),
                "high_price": float(k[2]),
                "low_price": float(k[3]),
                "close_price": float(k[4]),
                "volume": float(k[5]),
                "trade_value": float(k[7]),
            })

        return pd.DataFrame(rows)

    def fetch_daily_ohlcv(self, symbol: str, limit: int = 200) -> pd.DataFrame:
        """특정 심볼의 일봉 데이터를 가져옵니다."""
        return self._fetch_single_klines(symbol, interval="1d", limit=limit)

    # ── 분봉 OHLCV ────────────────────────────

    def fetch_minute_ohlcv(self, symbol: str, unit: int = 1, limit: int = 200) -> pd.DataFrame:
        """특정 심볼의 분봉 데이터를 가져옵니다."""
        interval_map = {1: "1m", 3: "3m", 5: "5m", 15: "15m", 30: "30m", 60: "1h", 240: "4h"}
        interval = interval_map.get(unit, "1m")

        data = self._request("/klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        })
        if not data:
            return pd.DataFrame()

        rows = []
        for k in data:
            rows.append({
                "market": symbol,
                "exchange": "binance",
                "candle_dt": datetime.fromtimestamp(
                    k[0] / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "unit": unit,
                "open_price": float(k[1]),
                "high_price": float(k[2]),
                "low_price": float(k[3]),
                "close_price": float(k[4]),
                "volume": float(k[5]),
                "trade_value": float(k[7]),
            })

        return pd.DataFrame(rows)

    # ── 전체 수집 + DB 적재 ────────────────────

    def collect_all_daily(self, quote: str = "USDT") -> Dict[str, int]:
        """USDT 마켓 전체의 일봉 데이터를 수집하여 DB에 적재합니다."""
        markets_df = self.fetch_markets(quote)
        symbols = markets_df["market"].tolist()

        if self.db:
            self.db.upsert_market_info(markets_df)

        all_ohlcv = []
        total = len(symbols)

        def _fetch(symbol):
            try:
                return self._fetch_single_klines(symbol, interval="1d", limit=config.collector.daily_count)
            except Exception as e:
                logger.error("Binance %s 수집 실패: %s", symbol, str(e))
                return pd.DataFrame()

        with ThreadPoolExecutor(max_workers=config.collector.max_concurrent) as executor:
            futures = {executor.submit(_fetch, sym): sym for sym in symbols}
            for idx, future in enumerate(as_completed(futures), 1):
                sym = futures[future]
                try:
                    df = future.result()
                    if not df.empty:
                        all_ohlcv.append(df)
                        logger.info("[%d/%d] Binance %s 일봉 %d건", idx, total, sym, len(df))
                except Exception as e:
                    logger.error("[%d/%d] Binance %s 오류: %s", idx, total, sym, str(e))

        if not all_ohlcv:
            logger.warning("Binance 수집된 일봉 데이터가 없습니다")
            return {"markets": total, "rows": 0}

        combined = pd.concat(all_ohlcv, ignore_index=True)
        rows = 0
        if self.db:
            rows = self.db.upsert_ohlcv_daily(combined)

        logger.info("Binance 일봉 수집 완료: %d 마켓, %d 행 적재", total, rows)
        return {"markets": total, "rows": rows}


# ═══════════════════════════════════════════════
# 통합 데이터 수집기
# ═══════════════════════════════════════════════

class DataCollectorService:
    """Upbit + Binance 통합 데이터 수집 서비스

    사용 예시:
        db = DBManager()
        db.init_tables()

        service = DataCollectorService(db)
        service.run_daily_collection()
        service.run_minute_collection()
    """

    def __init__(self, db: Optional[DBManager] = None):
        self.db = db
        self.upbit = UpbitCollector(db)
        self.binance = BinanceCollector(db)

    def run_daily_collection(self) -> Dict[str, Dict[str, int]]:
        """일봉 데이터 전체 수집 (Upbit + Binance)"""
        logger.info("=== 일봉 수집 시작 ===")
        results = {}

        try:
            results["upbit"] = self.upbit.collect_all_daily("KRW")
        except Exception as e:
            logger.error("Upbit 일봉 수집 실패: %s", str(e))
            results["upbit"] = {"markets": 0, "rows": 0, "error": str(e)}

        try:
            results["binance"] = self.binance.collect_all_daily("USDT")
        except Exception as e:
            logger.error("Binance 일봉 수집 실패: %s", str(e))
            results["binance"] = {"markets": 0, "rows": 0, "error": str(e)}

        logger.info("=== 일봉 수집 완료: %s ===", results)
        return results

    def run_minute_collection(self, unit: int = 1) -> Dict[str, Dict[str, int]]:
        """분봉 데이터 전체 수집 (Upbit만 - Binance는 rate limit이 엄격)"""
        logger.info("=== %d분봉 수집 시작 ===", unit)
        results = {}

        try:
            results["upbit"] = self.upbit.collect_all_minute("KRW", unit=unit)
        except Exception as e:
            logger.error("Upbit %d분봉 수집 실패: %s", unit, str(e))
            results["upbit"] = {"markets": 0, "rows": 0, "error": str(e)}

        logger.info("=== %d분봉 수집 완료: %s ===", unit, results)
        return results

    def run_orderbook_collection(self) -> Dict[str, int]:
        """호가 데이터 수집 (Upbit)"""
        logger.info("=== 호가 수집 시작 ===")
        try:
            result = self.upbit.collect_orderbook("KRW")
        except Exception as e:
            logger.error("호가 수집 실패: %s", str(e))
            result = {"markets": 0, "rows": 0, "error": str(e)}
        return result


# ═══════════════════════════════════════════════
# CLI 실행
# ═══════════════════════════════════════════════

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    """커맨드라인 실행 엔트리포인트"""
    import argparse

    parser = argparse.ArgumentParser(description="Upbit/Binance 데이터 수집기")
    parser.add_argument(
        "mode",
        choices=["daily", "minute", "orderbook", "all", "init"],
        help="수집 모드: daily(일봉), minute(분봉), orderbook(호가), all(전체), init(테이블 초기화)",
    )
    parser.add_argument("--unit", type=int, default=1, help="분봉 단위 (기본: 1)")
    parser.add_argument("--no-db", action="store_true", help="DB 적재 없이 수집만")
    args = parser.parse_args()

    setup_logging()

    db = None
    if not args.no_db:
        db = DBManager()
        db.init_tables()

    service = DataCollectorService(db)

    if args.mode == "init":
        if db:
            db.init_tables()
        logger.info("테이블 초기화 완료")

    elif args.mode == "daily":
        results = service.run_daily_collection()
        logger.info("결과: %s", results)

    elif args.mode == "minute":
        results = service.run_minute_collection(unit=args.unit)
        logger.info("결과: %s", results)

    elif args.mode == "orderbook":
        result = service.run_orderbook_collection()
        logger.info("결과: %s", result)

    elif args.mode == "all":
        daily_results = service.run_daily_collection()
        minute_results = service.run_minute_collection(unit=args.unit)
        orderbook_result = service.run_orderbook_collection()
        logger.info("일봉: %s", daily_results)
        logger.info("분봉: %s", minute_results)
        logger.info("호가: %s", orderbook_result)

    if db:
        db.dispose()


if __name__ == "__main__":
    main()
