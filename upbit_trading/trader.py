"""Upbit API 자동 매매 실행 모듈

pyupbit 라이브러리를 활용한 Upbit 거래소 API 연동.
시장가/지정가 매수/매도, 주문 취소, 계좌 조회 기능을 제공한다.
"""

import os
import uuid
import hashlib
import logging
import time
from datetime import datetime
from urllib.parse import urlencode
from typing import Optional

import jwt
import requests
import pyupbit

logger = logging.getLogger(__name__)


class UpbitTrader:
    """Upbit 거래소 매매 실행 클래스

    pyupbit 라이브러리와 직접 REST API 호출을 조합하여
    주문, 조회, 취소 등의 거래 기능을 제공한다.
    """

    SERVER_URL = "https://api.upbit.com"
    COMMISSION_RATE = 0.0005  # 0.05%

    def __init__(self, access_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.access_key = access_key or os.environ.get("UPBIT_ACCESS_KEY", "")
        self.secret_key = secret_key or os.environ.get("UPBIT_SECRET_KEY", "")

        if not self.access_key or not self.secret_key:
            logger.warning("Upbit API 키가 설정되지 않았습니다. 환경변수를 확인하세요.")

        # pyupbit Upbit 인스턴스 (인증된 API 호출용)
        self._upbit: Optional[pyupbit.Upbit] = None
        self._init_upbit()

    def _init_upbit(self):
        """pyupbit Upbit 인스턴스를 초기화한다."""
        if self.access_key and self.secret_key:
            try:
                self._upbit = pyupbit.Upbit(self.access_key, self.secret_key)
                logger.info("Upbit API 연결 성공")
            except Exception as e:
                logger.error(f"Upbit API 연결 실패: {e}")
                self._upbit = None

    # ─── JWT 인증 ───

    def _create_jwt_token(self, query_string: Optional[bytes] = None) -> str:
        """JWT 인증 토큰을 생성한다."""
        payload = {
            "access_key": self.access_key,
            "nonce": str(uuid.uuid4()),
        }
        if query_string is not None:
            msg = hashlib.sha512()
            msg.update(query_string)
            payload["query_hash"] = msg.hexdigest()
            payload["query_hash_alg"] = "SHA512"

        return jwt.encode(payload, self.secret_key)

    def _get_auth_headers(self, query_string: Optional[bytes] = None) -> dict:
        """인증 헤더를 생성한다."""
        token = self._create_jwt_token(query_string)
        return {"Authorization": f"Bearer {token}"}

    # ─── HTTP 요청 헬퍼 ───

    def _request_get(self, url: str, params=None, headers=None) -> Optional[dict]:
        """GET 요청을 보낸다."""
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"GET 요청 실패 ({url}): {e}")
            return None

    def _request_post(self, url: str, params=None, headers=None) -> Optional[dict]:
        """POST 요청을 보낸다."""
        try:
            resp = requests.post(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"POST 요청 실패 ({url}): {e}")
            return None

    def _request_delete(self, url: str, params=None, headers=None) -> Optional[dict]:
        """DELETE 요청을 보낸다."""
        try:
            resp = requests.delete(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"DELETE 요청 실패 ({url}): {e}")
            return None

    # ─── 주문 기능 ───

    def buy_market_order(self, ticker: str, price: float) -> Optional[dict]:
        """시장가 매수 주문

        Args:
            ticker: 마켓 코드 (예: "KRW-BTC")
            price: 매수에 사용할 KRW 금액

        Returns:
            주문 결과 dict 또는 None
        """
        if price <= 0:
            logger.error(f"매수 금액이 유효하지 않습니다: {price}")
            return None

        logger.info(f"[매수-시장가] {ticker} | 금액: {price:,.0f} KRW")

        query = {
            "market": ticker,
            "side": "bid",
            "price": str(price),
            "ord_type": "price",
        }
        query_string = urlencode(query).encode()
        headers = self._get_auth_headers(query_string)
        result = self._request_post(
            f"{self.SERVER_URL}/v1/orders", params=query_string, headers=headers
        )

        if result:
            logger.info(f"[매수-시장가] 주문 성공 | UUID: {result.get('uuid')}")
        else:
            logger.error(f"[매수-시장가] 주문 실패 | {ticker}")

        return result

    def buy_limit_order(self, ticker: str, price: float, volume: float) -> Optional[dict]:
        """지정가 매수 주문

        Args:
            ticker: 마켓 코드 (예: "KRW-BTC")
            price: 매수 희망 가격
            volume: 매수 수량

        Returns:
            주문 결과 dict 또는 None
        """
        if price <= 0 or volume <= 0:
            logger.error(f"매수 파라미터가 유효하지 않습니다: price={price}, volume={volume}")
            return None

        logger.info(f"[매수-지정가] {ticker} | 가격: {price:,.0f} | 수량: {volume}")

        query = {
            "market": ticker,
            "side": "bid",
            "volume": str(volume),
            "price": str(price),
            "ord_type": "limit",
        }
        query_string = urlencode(query).encode()
        headers = self._get_auth_headers(query_string)
        result = self._request_post(
            f"{self.SERVER_URL}/v1/orders", params=query_string, headers=headers
        )

        if result:
            logger.info(f"[매수-지정가] 주문 성공 | UUID: {result.get('uuid')}")
        else:
            logger.error(f"[매수-지정가] 주문 실패 | {ticker}")

        return result

    def sell_market_order(self, ticker: str, volume: float) -> Optional[dict]:
        """시장가 매도 주문

        Args:
            ticker: 마켓 코드 (예: "KRW-BTC")
            volume: 매도 수량

        Returns:
            주문 결과 dict 또는 None
        """
        if volume <= 0:
            logger.error(f"매도 수량이 유효하지 않습니다: {volume}")
            return None

        logger.info(f"[매도-시장가] {ticker} | 수량: {volume}")

        query = {
            "market": ticker,
            "side": "ask",
            "volume": str(volume),
            "ord_type": "market",
        }
        query_string = urlencode(query).encode()
        headers = self._get_auth_headers(query_string)
        result = self._request_post(
            f"{self.SERVER_URL}/v1/orders", params=query_string, headers=headers
        )

        if result:
            logger.info(f"[매도-시장가] 주문 성공 | UUID: {result.get('uuid')}")
        else:
            logger.error(f"[매도-시장가] 주문 실패 | {ticker}")

        return result

    def sell_limit_order(self, ticker: str, price: float, volume: float) -> Optional[dict]:
        """지정가 매도 주문

        Args:
            ticker: 마켓 코드 (예: "KRW-BTC")
            price: 매도 희망 가격
            volume: 매도 수량

        Returns:
            주문 결과 dict 또는 None
        """
        if price <= 0 or volume <= 0:
            logger.error(f"매도 파라미터가 유효하지 않습니다: price={price}, volume={volume}")
            return None

        logger.info(f"[매도-지정가] {ticker} | 가격: {price:,.0f} | 수량: {volume}")

        query = {
            "market": ticker,
            "side": "ask",
            "volume": str(volume),
            "price": str(price),
            "ord_type": "limit",
        }
        query_string = urlencode(query).encode()
        headers = self._get_auth_headers(query_string)
        result = self._request_post(
            f"{self.SERVER_URL}/v1/orders", params=query_string, headers=headers
        )

        if result:
            logger.info(f"[매도-지정가] 주문 성공 | UUID: {result.get('uuid')}")
        else:
            logger.error(f"[매도-지정가] 주문 실패 | {ticker}")

        return result

    def cancel_order(self, order_uuid: str) -> Optional[dict]:
        """주문 취소

        Args:
            order_uuid: 취소할 주문의 UUID

        Returns:
            취소 결과 dict 또는 None
        """
        logger.info(f"[주문취소] UUID: {order_uuid}")

        query = {"uuid": order_uuid}
        query_string = urlencode(query).encode()
        headers = self._get_auth_headers(query_string)
        result = self._request_delete(
            f"{self.SERVER_URL}/v1/order", params=query_string, headers=headers
        )

        if result:
            logger.info(f"[주문취소] 성공 | UUID: {order_uuid}")
        else:
            logger.error(f"[주문취소] 실패 | UUID: {order_uuid}")

        return result

    # ─── 조회 기능 ───

    def get_balance(self, ticker: str = "KRW") -> float:
        """특정 화폐의 잔고를 조회한다.

        Args:
            ticker: 화폐 코드 (기본값: "KRW")

        Returns:
            잔고 금액 (float). 조회 실패 시 0.0
        """
        if self._upbit is None:
            logger.error("Upbit 인스턴스가 초기화되지 않았습니다.")
            return 0.0

        try:
            balance = self._upbit.get_balance(ticker)
            return float(balance) if balance is not None else 0.0
        except Exception as e:
            logger.error(f"잔고 조회 실패 ({ticker}): {e}")
            return 0.0

    def get_balances(self) -> list:
        """전체 보유 자산 목록을 조회한다.

        Returns:
            보유 자산 리스트. 각 항목은 dict (currency, balance, locked, avg_buy_price 등)
        """
        headers = self._get_auth_headers()
        result = self._request_get(f"{self.SERVER_URL}/v1/accounts", headers=headers)
        return result if result else []

    def get_order(self, order_uuid: str) -> Optional[dict]:
        """개별 주문 상세를 조회한다.

        Args:
            order_uuid: 조회할 주문의 UUID

        Returns:
            주문 상세 dict 또는 None
        """
        query = {"uuid": order_uuid}
        query_string = urlencode(query).encode()
        headers = self._get_auth_headers(query_string)
        return self._request_get(
            f"{self.SERVER_URL}/v1/order", params=query_string, headers=headers
        )

    def get_open_orders(self, ticker: Optional[str] = None) -> list:
        """미체결 주문 목록을 조회한다.

        Args:
            ticker: 마켓 코드 (None이면 전체)

        Returns:
            미체결 주문 리스트
        """
        query = {"state": "wait"}
        if ticker:
            query["market"] = ticker
        query_string = urlencode(query).encode()
        headers = self._get_auth_headers(query_string)
        result = self._request_get(
            f"{self.SERVER_URL}/v1/orders", params=query_string, headers=headers
        )
        return result if result else []

    def get_current_price(self, ticker: str) -> Optional[float]:
        """현재가를 조회한다.

        Args:
            ticker: 마켓 코드 (예: "KRW-BTC")

        Returns:
            현재가 또는 None
        """
        try:
            price = pyupbit.get_current_price(ticker)
            return float(price) if price is not None else None
        except Exception as e:
            logger.error(f"현재가 조회 실패 ({ticker}): {e}")
            return None

    def get_avg_buy_price(self, ticker: str) -> float:
        """보유 종목의 평균 매수가를 조회한다.

        Args:
            ticker: 화폐 코드 (예: "BTC", "ETH")

        Returns:
            평균 매수가. 보유하지 않으면 0.0
        """
        balances = self.get_balances()
        for item in balances:
            if item.get("currency") == ticker:
                return float(item.get("avg_buy_price", 0))
        return 0.0

    def get_holding_amount(self, ticker: str) -> float:
        """보유 수량을 조회한다.

        Args:
            ticker: 화폐 코드 (예: "BTC")

        Returns:
            보유 수량. 보유하지 않으면 0.0
        """
        balances = self.get_balances()
        for item in balances:
            if item.get("currency") == ticker:
                return float(item.get("balance", 0))
        return 0.0

    def wait_order_complete(self, order_uuid: str, timeout: int = 60, interval: float = 1.0) -> Optional[dict]:
        """주문이 체결될 때까지 대기한다.

        Args:
            order_uuid: 주문 UUID
            timeout: 최대 대기 시간 (초)
            interval: 폴링 간격 (초)

        Returns:
            체결 완료된 주문 정보 또는 None (타임아웃)
        """
        start = time.time()
        while time.time() - start < timeout:
            order = self.get_order(order_uuid)
            if order is None:
                return None
            state = order.get("state", "")
            if state in ("done", "cancel"):
                return order
            time.sleep(interval)

        logger.warning(f"주문 체결 대기 타임아웃 | UUID: {order_uuid}")
        return None
