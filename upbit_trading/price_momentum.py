"""
전일 저가/고가 대비 현재가 모멘텀 분석
- 전일 저가 대비 오름폭 상위 20종목 (반등 모멘텀)
- 전일 고가 대비 하락폭 상위 20종목 (급락 종목)
- 전일 데이터: SQL Server (ohlcv_daily)
- 현재가: Upbit API 실시간 조회
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from sqlalchemy import create_engine, text

# ─── 설정 ────────────────────────────────────
SQL_SERVER = r"CH-PC1\SQLEXPRESS"
DB_NAME = "CryptoDB"
ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

UPBIT_BASE = "https://api.upbit.com/v1"
session = requests.Session()
session.headers.update({"Accept": "application/json"})


def get_db_engine():
    conn_str = (
        f"mssql+pyodbc://@{SQL_SERVER}/{DB_NAME}"
        f"?driver={ODBC_DRIVER.replace(' ', '+')}"
        "&Trusted_Connection=yes"
    )
    return create_engine(conn_str, pool_pre_ping=True)


def get_previous_day_prices(engine):
    """SQL Server에서 전일 저가/고가 조회 (KRW 마켓, 가장 최근 완료일)"""
    query = text("""
        WITH latest AS (
            SELECT MAX(candle_date) AS max_date
            FROM dbo.ohlcv_daily
            WHERE exchange = 'upbit'
              AND market LIKE 'KRW-%'
              AND candle_date < CAST(GETDATE() AS DATE)
        )
        SELECT
            d.market,
            d.candle_date,
            d.open_price,
            d.high_price,
            d.low_price,
            d.close_price,
            d.volume,
            d.trade_value
        FROM dbo.ohlcv_daily d
        INNER JOIN latest l ON d.candle_date = l.max_date
        WHERE d.exchange = 'upbit'
          AND d.market LIKE 'KRW-%'
        ORDER BY d.market
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df


def get_current_prices(markets):
    """Upbit API에서 현재가 실시간 조회 (최대 100개씩 배치)"""
    all_data = []
    for i in range(0, len(markets), 100):
        batch = markets[i:i+100]
        resp = session.get(
            f"{UPBIT_BASE}/ticker",
            params={"markets": ",".join(batch)},
            timeout=10,
        )
        resp.raise_for_status()
        all_data.extend(resp.json())
        if i + 100 < len(markets):
            time.sleep(0.12)
    return {item["market"]: item for item in all_data}


def get_market_names():
    """Upbit 마켓 한글명 조회"""
    resp = session.get(
        f"{UPBIT_BASE}/market/all",
        params={"is_details": "true"},
        timeout=10,
    )
    resp.raise_for_status()
    return {
        item["market"]: item.get("korean_name", "")
        for item in resp.json()
        if item["market"].startswith("KRW-")
    }


def main():
    print("=" * 95)
    print("  전일 저가/고가 대비 현재가 모멘텀 분석")
    print(f"  조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 95)

    # 1) SQL에서 전일 데이터 조회
    print("\n[1] SQL Server에서 전일 OHLCV 데이터 조회 중...")
    engine = get_db_engine()
    prev_df = get_previous_day_prices(engine)
    engine.dispose()

    if prev_df.empty:
        print("    전일 데이터가 없습니다. 먼저 데이터 수집을 실행하세요.")
        return

    prev_date = prev_df["candle_date"].iloc[0]
    print(f"    전일 날짜: {prev_date}")
    print(f"    조회 종목 수: {len(prev_df)}개")

    # 2) 마켓 한글명 조회
    print("\n[2] 마켓 한글명 조회 중...")
    name_map = get_market_names()

    # 3) 현재가 조회
    print("\n[3] Upbit API에서 현재가 실시간 조회 중...")
    markets = prev_df["market"].tolist()
    ticker_map = get_current_prices(markets)
    print(f"    현재가 조회 완료: {len(ticker_map)}개")

    # 4) 분석
    results = []
    for _, row in prev_df.iterrows():
        market = row["market"]
        if market not in ticker_map:
            continue

        ticker = ticker_map[market]
        current_price = ticker["trade_price"]
        prev_low = row["low_price"]
        prev_high = row["high_price"]
        prev_close = row["close_price"]
        prev_open = row["open_price"]

        # 전일 저가 대비 현재가 변동률
        chg_from_low = ((current_price - prev_low) / prev_low) * 100 if prev_low > 0 else 0
        # 전일 고가 대비 현재가 변동률
        chg_from_high = ((current_price - prev_high) / prev_high) * 100 if prev_high > 0 else 0
        # 전일 종가 대비
        chg_from_close = ((current_price - prev_close) / prev_close) * 100 if prev_close > 0 else 0

        # 24시간 거래대금
        trade_value_24h = ticker.get("acc_trade_price_24h", 0)

        results.append({
            "market": market,
            "name": name_map.get(market, ""),
            "current_price": current_price,
            "prev_open": prev_open,
            "prev_high": prev_high,
            "prev_low": prev_low,
            "prev_close": prev_close,
            "chg_from_low_%": round(chg_from_low, 2),
            "chg_from_high_%": round(chg_from_high, 2),
            "chg_from_close_%": round(chg_from_close, 2),
            "trade_value_24h": trade_value_24h,
        })

    df = pd.DataFrame(results)

    if df.empty:
        print("    분석할 데이터가 없습니다.")
        return

    def fmt_price(p):
        if p >= 1_000:
            return f"{p:,.0f}"
        elif p >= 1:
            return f"{p:,.1f}"
        else:
            return f"{p:,.4f}"

    # ─── 전일 저가 대비 오름폭 상위 10 ───
    top_up = df.nlargest(20, "chg_from_low_%")

    print("\n" + "=" * 120)
    print("  [전일 저가 대비 오름폭 상위 20종목] - 반등 모멘텀 강한 종목")
    print("=" * 120)
    print(f"  {'#':>3s}  {'종목':15s} {'이름':10s} {'현재가':>14s} {'전일저가':>14s} {'저가대비':>9s} {'전일고가':>14s} {'고가대비':>9s} {'종가대비':>9s} {'24h거래대금':>12s}")
    print("  " + "-" * 115)
    for rank, (_, r) in enumerate(top_up.iterrows(), 1):
        vol_fmt = f"{r['trade_value_24h']/1e8:,.0f}억"
        print(f"  {rank:3d}. {r['market']:15s} {r['name']:10s}"
              f" {fmt_price(r['current_price']):>14s}"
              f" {fmt_price(r['prev_low']):>14s} {r['chg_from_low_%']:>+8.2f}%"
              f" {fmt_price(r['prev_high']):>14s} {r['chg_from_high_%']:>+8.2f}%"
              f" {r['chg_from_close_%']:>+8.2f}%"
              f" {vol_fmt:>12s}")

    # ─── 전일 고가 대비 하락폭 상위 10 ───
    top_down = df.nsmallest(20, "chg_from_high_%")

    print("\n" + "=" * 120)
    print("  [전일 고가 대비 하락폭 상위 20종목] - 급락 종목")
    print("=" * 120)
    print(f"  {'#':>3s}  {'종목':15s} {'이름':10s} {'현재가':>14s} {'전일고가':>14s} {'고가대비':>9s} {'전일저가':>14s} {'저가대비':>9s} {'종가대비':>9s} {'24h거래대금':>12s}")
    print("  " + "-" * 115)
    for rank, (_, r) in enumerate(top_down.iterrows(), 1):
        vol_fmt = f"{r['trade_value_24h']/1e8:,.0f}억"
        print(f"  {rank:3d}. {r['market']:15s} {r['name']:10s}"
              f" {fmt_price(r['current_price']):>14s}"
              f" {fmt_price(r['prev_high']):>14s} {r['chg_from_high_%']:>+8.2f}%"
              f" {fmt_price(r['prev_low']):>14s} {r['chg_from_low_%']:>+8.2f}%"
              f" {r['chg_from_close_%']:>+8.2f}%"
              f" {vol_fmt:>12s}")

    # ─── 전체 시장 요약 ───
    print("\n" + "=" * 95)
    print("  [시장 요약]")
    print("=" * 95)
    avg_chg_close = df["chg_from_close_%"].mean()
    up_count = (df["chg_from_close_%"] > 0).sum()
    down_count = (df["chg_from_close_%"] < 0).sum()
    flat_count = (df["chg_from_close_%"] == 0).sum()
    total_vol = df["trade_value_24h"].sum()

    print(f"  총 종목: {len(df)}개")
    print(f"  상승: {up_count}개 | 하락: {down_count}개 | 보합: {flat_count}개")
    print(f"  전일 종가 대비 평균 변동률: {avg_chg_close:+.2f}%")
    print(f"  전일 저가 대비 평균 오름폭: {df['chg_from_low_%'].mean():+.2f}%")
    print(f"  전일 고가 대비 평균 하락폭: {df['chg_from_high_%'].mean():+.2f}%")
    print(f"  24시간 총 거래대금: {total_vol/1e8:,.0f}억원")
    print()


if __name__ == "__main__":
    main()
