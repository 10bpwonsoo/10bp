# Upbit Trading Bot

업비트 자동매매 시스템 (Python)

## 구조

```
upbit_cursor.py               # 메인 트레이딩 스크립트
upbit_trading/                # 트레이딩 모듈 패키지
├── config.py                 # 설정 (API 키, 파라미터)
├── trader.py                 # 주문 실행
├── trading_engine.py         # 메인 트레이딩 엔진
├── scalp_engine.py           # 스캘핑 전략
├── strategies.py             # 전략 목록
├── strategy_box_range.py     # 박스권 전략
├── strategy_historical_low.py# 역사적 저점 전략
├── price_momentum.py         # 가격 모멘텀 분석
├── data_collector.py         # 시장 데이터 수집
├── db_manager.py             # 데이터베이스 관리
├── backtester.py             # 백테스트
├── risk_manager.py           # 리스크 관리
├── notification_manager.py   # 알림 (텔레그램)
├── telegram_bot.py           # 텔레그램 봇
├── telegram_commands.py      # 텔레그램 명령어
├── technical_indicators.py   # 기술적 지표
├── rate_limiter.py           # API 요청 제한
└── position_tracker.py       # 포지션 추적
```

## 설정

1. `.env.example`을 `.env`로 복사 후 입력:
```bash
cp .env.example .env
```

2. `.env`에 텔레그램 정보 입력:
```
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

3. `upbit_trading/config.py`에서 업비트 API 키 및 트레이딩 파라미터 설정

## 실행

```bash
python upbit_cursor.py
```

## 패키지 설치

```bash
pip install pyupbit python-telegram-bot requests pandas numpy
```
