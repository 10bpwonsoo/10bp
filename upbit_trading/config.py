"""
설정 파일 - API 키, DB 연결 정보, 수집 주기 등 관리

환경변수 또는 .env 파일에서 설정을 로드합니다.
.env 파일 예시:
    UPBIT_ACCESS_KEY=your_access_key
    UPBIT_SECRET_KEY=your_secret_key
    BINANCE_API_KEY=your_binance_key
    BINANCE_SECRET_KEY=your_binance_secret
    DB_SERVER=PC1\\SQLEXPRESS
    DB_NAME=CryptoDB
    DB_DRIVER=ODBC Driver 17 for SQL Server
    TELEGRAM_TOKEN=your_telegram_token
    TELEGRAM_CHAT_ID=your_chat_id
"""

import os
from dataclasses import dataclass, field
from typing import Dict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class UpbitConfig:
    """Upbit API 설정"""
    access_key: str = ""
    secret_key: str = ""
    base_url: str = "https://api.upbit.com/v1"
    rate_limit_per_sec: int = 10
    rate_limit_per_min: int = 600

    def __post_init__(self):
        self.access_key = self.access_key or os.getenv("UPBIT_ACCESS_KEY", "")
        self.secret_key = self.secret_key or os.getenv("UPBIT_SECRET_KEY", "")


@dataclass
class BinanceConfig:
    """Binance API 설정"""
    api_key: str = ""
    secret_key: str = ""
    base_url: str = "https://api.binance.com/api/v3"
    rate_limit_per_min: int = 1200

    def __post_init__(self):
        self.api_key = self.api_key or os.getenv("BINANCE_API_KEY", "")
        self.secret_key = self.secret_key or os.getenv("BINANCE_SECRET_KEY", "")


@dataclass
class DBConfig:
    """SQL Server 연결 설정"""
    server: str = ""
    database: str = ""
    driver: str = ""
    trusted_connection: bool = True
    username: str = ""
    password: str = ""
    pool_size: int = 5
    pool_timeout: int = 30

    def __post_init__(self):
        self.server = self.server or os.getenv("DB_SERVER", r"CH-PC1\SQLEXPRESS")
        self.database = self.database or os.getenv("DB_NAME", "CryptoDB")
        self.driver = self.driver or os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
        self.username = self.username or os.getenv("DB_USERNAME", "")
        self.password = self.password or os.getenv("DB_PASSWORD", "")

    @property
    def connection_string(self) -> str:
        """SQLAlchemy 연결 문자열 생성"""
        driver_encoded = self.driver.replace(" ", "+")
        if self.trusted_connection:
            return (
                f"mssql+pyodbc://@{self.server}/{self.database}"
                f"?driver={driver_encoded}&Trusted_Connection=yes"
            )
        return (
            f"mssql+pyodbc://{self.username}:{self.password}"
            f"@{self.server}/{self.database}"
            f"?driver={driver_encoded}"
        )

    @property
    def pymssql_params(self) -> dict:
        """pymssql 연결 파라미터"""
        params = {
            "server": self.server,
            "database": self.database,
        }
        if not self.trusted_connection:
            params["user"] = self.username
            params["password"] = self.password
        return params


@dataclass
class TelegramConfig:
    """텔레그램 설정"""
    token: str = ""
    chat_id: str = ""

    def __post_init__(self):
        self.token = self.token or os.getenv("TELEGRAM_TOKEN", "")
        self.chat_id = self.chat_id or os.getenv("TELEGRAM_CHAT_ID", "")


@dataclass
class CollectorConfig:
    """데이터 수집 주기 설정"""
    # 일봉 수집 주기 (초)
    daily_interval: int = 86400  # 24시간
    # 분봉 수집 주기 (초)
    minute_interval: int = 60  # 1분
    # 호가 수집 주기 (초)
    orderbook_interval: int = 5  # 5초
    # 분봉 단위 (1, 3, 5, 10, 15, 30, 60, 240)
    minute_unit: int = 1
    # 일봉 수집 개수 (최대 200)
    daily_count: int = 200
    # 분봉 수집 개수 (최대 200)
    minute_count: int = 200
    # API 요청 간 딜레이 (초)
    request_delay: float = 0.1
    # API 요청 재시도 횟수
    max_retries: int = 3
    # 재시도 간 대기 시간 (초)
    retry_delay: float = 1.0
    # 병렬 요청 수 (Binance용)
    max_concurrent: int = 10
    # Binance 수집 대상 마켓
    binance_quote: str = "USDT"
    # 분석 기간 설정 (일 단위)
    analysis_periods: Dict[str, int] = field(default_factory=lambda: {
        "5년": 365 * 5,
        "3년": 365 * 3,
        "1년": 365,
        "1개월": 30,
        "1주일": 7,
        "3일": 3,
    })


@dataclass
class ScalpEngineConfig:
    """스캘핑 엔진 설정"""
    # 엔진 공통
    cycle_seconds: int = 12             # 메인 루프 주기 (초)
    api_rate_limit: int = 8             # 초당 API 호출 제한

    # 전략 1: 역사적 전저점 급등 매수
    hist_lookback_days: int = 60        # 과거 저점 탐색 기간
    hist_low_proximity_pct: float = 0.05  # 저점 근접 판단 (5%)
    hist_volume_surge: float = 3.0      # 거래량 급등 배수
    hist_invest_amount: float = 100_000 # 건당 투자금 (KRW)
    hist_max_positions: int = 3         # 동시 보유 최대
    hist_max_hold_minutes: int = 30     # 최대 보유 시간 (분)
    hist_stop_loss: float = -0.05       # 긴급 손절 (-5%)
    hist_scan_start_hour: int = 8       # 스캔 시작 시각
    hist_scan_start_minute: int = 50    # 스캔 시작 분
    hist_scan_end_hour: int = 9         # 스캔 종료 시각
    hist_scan_end_minute: int = 30      # 스캔 종료 분

    # 전략 2: 박스권 매매
    box_window_minutes: int = 300       # 박스 계산 구간 (5시간)
    box_min_range_pct: float = 0.02     # 최소 박스 폭 (2%)
    box_max_range_pct: float = 0.08     # 최대 박스 폭 (8%)
    box_buy_zone_pct: float = 0.20      # 매수 구간 (하단 20%)
    box_sell_zone_pct: float = 0.80     # 매도 구간 (상단 80%)
    box_invest_amount: float = 100_000  # 건당 투자금 (KRW)
    box_max_positions: int = 5          # 동시 보유 최대
    box_stop_loss: float = -0.05        # 손절 (-5%)
    box_max_hold_hours: int = 24         # 최대 보유 시간 (시간)
    box_daily_max_trades: int = 5       # 코인당 하루 매매 제한
    box_refresh_minutes: int = 5        # 박스 범위 갱신 주기 (분)
    box_top_n: int = 10                 # 거래대금 상위 N개 코인


@dataclass
class AppConfig:
    """전체 애플리케이션 설정"""
    upbit: UpbitConfig = field(default_factory=UpbitConfig)
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    db: DBConfig = field(default_factory=DBConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    log_level: str = "INFO"

    def __post_init__(self):
        self.log_level = os.getenv("LOG_LEVEL", self.log_level)


# 전역 설정 인스턴스
config = AppConfig()
