"""
실데이터 공급자들.

각 공급자는 (symbol, bars) 를 받아 `(timestamps, values)` 를 돌려준다.
Instrument 를 모르고 MarketSeries 도 모른다 — 조립은 composite 가 한다.
공급자를 갈아끼워도 엔진은커녕 어댑터 조립부도 바뀌지 않게 하기 위해서다
(요구 15-5).

돌려주는 것은 **일봉 종가**다. 요구 12 의 실시간성은 P4 범위 밖이고,
무료 공급자로 장중 틱을 받는 것은 어차피 불가능하다. DataMeta.mode 가
DELAYED 로 나가는 이유가 이것이다 — 지연 데이터를 실시간이라 표시하지
않는다.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from ..http import FetchError, HttpClient

logger = logging.getLogger(__name__)

#: 요청할 일수에 곱하는 여유. 휴장일 때문에 달력일 > 거래일 이다.
CALENDAR_SLACK = 1.6
Point = tuple[datetime, float]


def _utc(ts: float | int) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def _clean(points: Sequence[Point], bars: int) -> list[Point]:
    """시간 오름차순 정렬, 중복 제거, 마지막 bars 개."""
    seen: dict[datetime, float] = {}
    for ts, value in points:
        if value is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if v != v or v in (float("inf"), float("-inf")):  # NaN/inf
            continue
        seen[ts] = v
    ordered = sorted(seen.items())
    return ordered[-bars:] if bars > 0 else ordered


class Provider(ABC):
    """시계열 하나를 가져오는 공급자."""

    name: str
    #: 키가 필요하면 그 환경변수 이름. 없으면 None.
    requires_key: str | None = None

    @abstractmethod
    def fetch(self, spec: dict, *, bars: int, as_of: datetime) -> list[Point]:
        """spec 은 sources.yaml 의 한 항목이다. 실패하면 FetchError."""

    def available(self) -> tuple[bool, str]:
        """(쓸 수 있는가, 이유). probe CLI 가 그대로 출력한다."""
        return True, "사용 가능"


# ══════════════════════════════════════════════════════════════
class YahooProvider(Provider):
    """
    Yahoo Finance 차트 API. 키가 필요 없고 커버리지가 가장 넓다.

    ^TNX 같은 금리 심볼은 4.2% 를 42 로 준다. sources.yaml 의 scale 이
    그것을 되돌린다 — 어댑터가 아는 체하지 않고 설정이 말하게 한다.
    """

    name = "yahoo"
    BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def fetch(self, spec: dict, *, bars: int, as_of: datetime) -> list[Point]:
        symbol = str(spec["symbol"])
        start = as_of - timedelta(days=int(bars * CALENDAR_SLACK) + 10)
        raw = self.client.get(
            self.BASE + symbol,
            params={
                "period1": int(start.timestamp()),
                "period2": int(as_of.timestamp()),
                "interval": "1d",
                "events": "div,split",
            },
        )
        return self.parse(raw, bars=bars, scale=float(spec.get("scale", 1.0)))

    @staticmethod
    def parse(raw: bytes, *, bars: int, scale: float = 1.0) -> list[Point]:
        """응답 파싱을 따로 둔다. 네트워크 없이 고정 응답으로 테스트한다."""
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FetchError(f"JSON 이 아니다: {exc}", kind="parse", permanent=True) from exc

        chart = (doc or {}).get("chart") or {}
        if chart.get("error"):
            err = chart["error"]
            raise FetchError(
                f"Yahoo 오류: {err.get('description') or err}", kind="api", permanent=True
            )
        results = chart.get("result") or []
        if not results:
            raise FetchError("결과가 비어 있다", kind="empty", permanent=True)

        node = results[0]
        stamps = node.get("timestamp") or []
        quote = ((node.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        # 배당·분할 조정 종가가 있으면 그쪽이 수익률 계산에 맞다.
        adj = ((node.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")
        series = adj if adj and len(adj) == len(stamps) else closes
        if not stamps or not series:
            raise FetchError("종가 계열이 없다", kind="empty", permanent=True)

        return _clean(
            [(_utc(t), v * scale) for t, v in zip(stamps, series) if v is not None],
            bars,
        )


# ══════════════════════════════════════════════════════════════
class StooqProvider(Provider):
    """stooq CSV. Yahoo 가 죽었을 때의 대체재다. 키가 필요 없다."""

    name = "stooq"
    BASE = "https://stooq.com/q/d/l/"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def fetch(self, spec: dict, *, bars: int, as_of: datetime) -> list[Point]:
        raw = self.client.get(
            self.BASE, params={"s": str(spec["symbol"]), "i": "d"}
        )
        return self.parse(raw, bars=bars, scale=float(spec.get("scale", 1.0)))

    @staticmethod
    def parse(raw: bytes, *, bars: int, scale: float = 1.0) -> list[Point]:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text or text.lower().startswith("<"):
            raise FetchError("CSV 가 아니다 (HTML 응답)", kind="parse", permanent=True)
        if text.lower() in ("no data", "exceeded the daily hits limit"):
            raise FetchError(text, kind="api", permanent=True)

        rows = list(csv.DictReader(io.StringIO(text)))
        points: list[Point] = []
        for row in rows:
            date, close = row.get("Date"), row.get("Close")
            if not date or not close:
                continue
            try:
                ts = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                points.append((ts, float(close) * scale))
            except ValueError:
                continue
        if not points:
            raise FetchError("파싱된 행이 없다", kind="empty", permanent=True)
        return _clean(points, bars)


# ══════════════════════════════════════════════════════════════
class FredProvider(Provider):
    """
    FRED. 금리·크레딧·기대인플레이션의 정본이다.

    키가 필요하다. 키가 없으면 사용 불가로 보고하고 다음 공급자로 넘어간다 —
    조용히 다른 값을 채우지 않는다.
    """

    name = "fred"
    requires_key = "FRED_API_KEY"
    BASE = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, client: HttpClient, api_key: str | None) -> None:
        self.client = client
        self.api_key = api_key

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "FRED_API_KEY 가 없다. https://fred.stlouisfed.org/docs/api/api_key.html"
        return True, "사용 가능"

    def fetch(self, spec: dict, *, bars: int, as_of: datetime) -> list[Point]:
        if not self.api_key:
            raise FetchError("FRED_API_KEY 가 없다", kind="auth", permanent=True)
        start = as_of - timedelta(days=int(bars * CALENDAR_SLACK) + 10)
        raw = self.client.get(
            self.BASE,
            params={
                "series_id": str(spec["symbol"]),
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": start.date().isoformat(),
                "observation_end": as_of.date().isoformat(),
            },
        )
        return self.parse(raw, bars=bars, scale=float(spec.get("scale", 1.0)))

    @staticmethod
    def parse(raw: bytes, *, bars: int, scale: float = 1.0) -> list[Point]:
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FetchError(f"JSON 이 아니다: {exc}", kind="parse", permanent=True) from exc
        if "error_message" in doc:
            raise FetchError(f"FRED 오류: {doc['error_message']}", kind="api", permanent=True)

        points: list[Point] = []
        for obs in doc.get("observations") or []:
            value = obs.get("value")
            # FRED 는 휴일을 "." 로 준다. 0 이 아니라 결측이다.
            if value in (None, "", "."):
                continue
            try:
                ts = datetime.strptime(obs["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                points.append((ts, float(value) * scale))
            except (KeyError, ValueError):
                continue
        if not points:
            raise FetchError("관측치가 없다", kind="empty", permanent=True)
        return _clean(points, bars)


# ══════════════════════════════════════════════════════════════
class KrxProvider(Provider):
    """
    KRX 정보데이터시스템. 한국 수급·업종지수의 유일한 무료 경로다.

    OTP 를 받아 조회하는 2단 요청이고 공개 계약이 아니다. 언제든 바뀔 수
    있다는 뜻이라 **실패를 정상 경로로 취급한다** — 실패하면 CSV 로,
    그것도 없으면 missing 이다. 요구 5 의 Theme Flow Momentum 과 요구 7 의
    가격↔수급 괴리가 여기 의존하므로, 실패했을 때 조용히 0 이 되지 않는
    것이 특히 중요하다 (설계서 STEP 7.1 Gap).
    """

    name = "krx"
    OTP = "http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd"
    DOWNLOAD = "http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd"
    REFERER = "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"

    #: dataset 이름 → KRX 화면 ID. sources.yaml 이 dataset 으로 고른다.
    SCREENS = {
        "investor_flow": "MDCSTAT02203",
        "trading_value": "MDCSTAT01602",
        "sector_index": "MDCSTAT00101",
        "bond_yield": "MDCSTAT10101",
        "index": "MDCSTAT00101",
    }

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def fetch(self, spec: dict, *, bars: int, as_of: datetime) -> list[Point]:
        dataset = str(spec.get("dataset") or "investor_flow")
        screen = self.SCREENS.get(dataset)
        if screen is None:
            raise FetchError(f"알 수 없는 KRX dataset: {dataset}", kind="config", permanent=True)

        start = as_of - timedelta(days=int(bars * CALENDAR_SLACK) + 10)
        otp = self.client.get(
            self.OTP,
            params={
                "bld": f"dbms/MDC/STAT/standard/{screen}",
                "strtDd": start.strftime("%Y%m%d"),
                "endDd": as_of.strftime("%Y%m%d"),
                "share": "1",
                "money": "1",
                "csvxls_isNo": "false",
            },
            headers={"Referer": self.REFERER},
        ).decode("utf-8", errors="replace")
        if not otp or "<" in otp:
            raise FetchError("OTP 발급 실패", kind="api")

        raw = self.client.get(
            self.DOWNLOAD, data={"code": otp}, headers={"Referer": self.REFERER}
        )
        return self.parse(raw, label=str(spec["symbol"]), bars=bars)

    @staticmethod
    def parse(raw: bytes, *, label: str, bars: int) -> list[Point]:
        """
        KRX CSV 는 EUC-KR 이고 열 이름이 화면마다 다르다. 날짜처럼 보이는
        열과 label 이 붙은 값 열을 찾는다.
        """
        for encoding in ("euc-kr", "cp949", "utf-8"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise FetchError("인코딩을 알 수 없다", kind="parse", permanent=True)

        rows = list(csv.DictReader(io.StringIO(text.strip())))
        if not rows:
            raise FetchError("행이 없다", kind="empty", permanent=True)

        headers = list(rows[0].keys())
        date_col = next((h for h in headers if "일자" in h or "날짜" in h), None)
        value_col = next((h for h in headers if label in h), None)
        if value_col is None:
            # 투자자별 화면은 행이 투자자, 열이 값이다. 뒤집혀 있다.
            value_col = next((h for h in headers if "순매수" in h or "종가" in h), None)
        if date_col is None or value_col is None:
            raise FetchError(
                f"열을 찾지 못했다. 받은 열: {headers[:8]}", kind="parse", permanent=True
            )

        points: list[Point] = []
        for row in rows:
            date_raw = (row.get(date_col) or "").strip().replace("/", "-")
            value_raw = (row.get(value_col) or "").strip().replace(",", "")
            if not date_raw or not value_raw or value_raw == "-":
                continue
            try:
                ts = datetime.strptime(date_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                points.append((ts, float(value_raw)))
            except ValueError:
                continue
        if not points:
            raise FetchError("파싱된 행이 없다", kind="empty", permanent=True)
        return _clean(points, bars)


# ══════════════════════════════════════════════════════════════
class CsvProvider(Provider):
    """
    로컬 CSV. 모든 instrument 의 마지막 후보로 자동 등록된다.

    막힌 네트워크에서도, 무료 API 가 없는 breadth 계열에서도, 그리고
    시연을 똑같이 재현해야 할 때도 이 경로가 답이다. 파일 하나로 LIVE 에
    준하는 화면이 나온다 (설계서 STEP 7.1 대응).

        data/replay/<instrument_id>.csv
        date,close
        2026-01-02,4.21
    """

    name = "csv"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def available(self) -> tuple[bool, str]:
        if not self.directory.exists():
            return False, f"{self.directory} 가 없다"
        n = len(list(self.directory.glob("*.csv")))
        return (n > 0), (f"{n}개 파일" if n else f"{self.directory} 가 비어 있다")

    def path_for(self, instrument_id: str) -> Path:
        return self.directory / f"{instrument_id}.csv"

    def fetch(self, spec: dict, *, bars: int, as_of: datetime) -> list[Point]:
        path = self.path_for(str(spec["symbol"]))
        if not path.exists():
            raise FetchError(f"{path.name} 이 없다", kind="missing", permanent=True)
        return self.parse(path.read_bytes(), bars=bars, scale=float(spec.get("scale", 1.0)))

    #: 값 열로 인정하는 이름. 내려받는 곳마다 다르다.
    VALUE_HEADERS = (
        "close", "adj close", "adjclose", "종가", "수정종가",
        "value", "값", "price", "현재가", "last", "settle",
    )
    #: 날짜 열로 인정하는 이름. FRED 는 observation_date, KRX 는 일자다.
    DATE_HEADERS = ("date", "observation_date", "일자", "날짜", "datetime", "time")
    #: 받아들이는 날짜 형식. 이 밖의 형식은 그 행을 건너뛴다.
    DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y%m%d", "%d-%m-%Y", "%m/%d/%Y")

    @classmethod
    def _columns(cls, headers: list[str]) -> tuple[str | None, str | None]:
        """
        날짜 열과 값 열을 고른다.

        FRED 는 `observation_date,DGS10` 처럼 값 열 이름이 심볼이다. 알려진
        이름이 없으면 **열이 둘뿐일 때만** 나머지를 값으로 본다. 열이 여럿인데
        짐작해서 고르면 Open 을 종가로 읽는 사고가 난다.
        """
        lowered = {h.lower().strip(): h for h in headers}
        date_col = next((lowered[k] for k in cls.DATE_HEADERS if k in lowered), None)
        value_col = next((lowered[k] for k in cls.VALUE_HEADERS if k in lowered), None)
        if value_col is None and date_col is not None and len(headers) == 2:
            value_col = next(h for h in headers if h != date_col)
        return date_col, value_col

    @staticmethod
    def _number(raw: str) -> float | None:
        """
        "1,380.5" · "4.21%" · "." 를 다룬다.

        FRED 는 휴일을 "." 로 준다. 결측이지 0 이 아니다 — 0 으로 읽으면
        금리가 4.21 에서 0 으로 떨어진 것이 되어 z-score 가 폭발한다.
        """
        cleaned = raw.strip().replace(",", "").replace("%", "").replace("\u2212", "-")
        if not cleaned or cleaned in (".", "-", "--", "N/A", "n/a"):
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    @classmethod
    def parse(cls, raw: bytes, *, bars: int, scale: float = 1.0) -> list[Point]:
        for encoding in ("utf-8-sig", "cp949", "euc-kr"):
            try:
                text = raw.decode(encoding).strip()
                break
            except UnicodeDecodeError:
                continue
        else:
            raise FetchError("인코딩을 알 수 없다", kind="parse", permanent=True)

        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            raise FetchError("행이 없다", kind="empty", permanent=True)

        headers = [h for h in rows[0].keys() if h is not None]
        date_col, value_col = cls._columns(headers)
        if date_col is None or value_col is None:
            raise FetchError(
                "날짜 열과 값 열을 찾지 못했다. "
                f"받은 열: {headers[:6]} / 인정하는 이름: date·일자 + close·종가·value·price "
                "(열이 둘뿐이면 두 번째를 값으로 본다)",
                kind="parse",
                permanent=True,
            )

        points: list[Point] = []
        for row in rows:
            date_raw = (row.get(date_col) or "").strip().replace("/", "-")
            value = cls._number(row.get(value_col) or "")
            if not date_raw or value is None:
                continue
            for fmt in cls.DATE_FORMATS:
                try:
                    ts = datetime.strptime(date_raw[:19], fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                continue
            points.append((ts, value * scale))

        if not points:
            raise FetchError(
                f"'{date_col}' / '{value_col}' 열은 찾았으나 읽을 수 있는 행이 없다. "
                "날짜 형식은 YYYY-MM-DD 를 권한다",
                kind="empty",
                permanent=True,
            )
        return _clean(points, bars)
