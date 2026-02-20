"""
데이터 수집 품질 검증 스크립트
- Upbit KRW 마켓 전체 코인 일봉 데이터 수집
- 시가/고가/저가/종가 누락 여부 확인
- 가격 이상치 검증 (high >= low, high >= open/close 등)
"""

import sys
import time
import logging

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_URL = "https://api.upbit.com/v1"
session = requests.Session()
session.headers.update({"Accept": "application/json"})


def fetch_markets():
    """KRW 마켓 목록 조회"""
    resp = session.get(f"{BASE_URL}/market/all", params={"is_details": "true"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return [item for item in data if item["market"].startswith("KRW-")]


def fetch_daily_ohlcv(market, count=200):
    """일봉 OHLCV 데이터 조회"""
    resp = session.get(
        f"{BASE_URL}/candles/days",
        params={"market": market, "count": count},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    print("=" * 70)
    print("  Upbit KRW 마켓 데이터 품질 검증")
    print("=" * 70)

    # 1) 마켓 목록 조회
    logger.info("KRW 마켓 목록 조회 중...")
    markets = fetch_markets()
    print(f"\n총 KRW 마켓 수: {len(markets)}개\n")

    # 결과 저장용
    all_results = []
    issues = []

    # 2) 각 코인별 일봉 데이터 수집 및 검증
    total = len(markets)
    for idx, mkt_info in enumerate(markets, 1):
        market = mkt_info["market"]
        korean_name = mkt_info.get("korean_name", "")

        try:
            candles = fetch_daily_ohlcv(market, count=30)  # 최근 30일
            time.sleep(0.12)  # rate limit 방지

            if not candles:
                issues.append({
                    "market": market,
                    "name": korean_name,
                    "issue": "데이터 없음 (빈 응답)",
                    "severity": "HIGH",
                })
                logger.warning("[%d/%d] %s (%s) - 데이터 없음", idx, total, market, korean_name)
                continue

            df = pd.DataFrame(candles)

            # 필수 컬럼 확인
            price_cols = ["opening_price", "high_price", "low_price", "trade_price"]
            missing_cols = [c for c in price_cols if c not in df.columns]
            if missing_cols:
                issues.append({
                    "market": market,
                    "name": korean_name,
                    "issue": f"컬럼 누락: {missing_cols}",
                    "severity": "HIGH",
                })
                continue

            # OHLCV 값 검증
            candle_count = len(df)

            # NULL/0 체크
            null_open = df["opening_price"].isna().sum() + (df["opening_price"] == 0).sum()
            null_high = df["high_price"].isna().sum() + (df["high_price"] == 0).sum()
            null_low = df["low_price"].isna().sum() + (df["low_price"] == 0).sum()
            null_close = df["trade_price"].isna().sum() + (df["trade_price"] == 0).sum()
            null_volume = df["candle_acc_trade_volume"].isna().sum() if "candle_acc_trade_volume" in df.columns else -1

            # 가격 논리 검증
            high_lt_low = (df["high_price"] < df["low_price"]).sum()
            high_lt_open = (df["high_price"] < df["opening_price"]).sum()
            high_lt_close = (df["high_price"] < df["trade_price"]).sum()
            low_gt_open = (df["low_price"] > df["opening_price"]).sum()
            low_gt_close = (df["low_price"] > df["trade_price"]).sum()

            result = {
                "market": market,
                "name": korean_name,
                "candles": candle_count,
                "null_open": null_open,
                "null_high": null_high,
                "null_low": null_low,
                "null_close": null_close,
                "null_volume": null_volume,
                "high<low": high_lt_low,
                "high<open": high_lt_open,
                "high<close": high_lt_close,
                "low>open": low_gt_open,
                "low>close": low_gt_close,
                "latest_close": df["trade_price"].iloc[0] if len(df) > 0 else None,
                "latest_date": df["candle_date_time_kst"].iloc[0][:10] if len(df) > 0 else None,
            }
            all_results.append(result)

            # 이슈 기록
            has_issue = False
            if null_open > 0 or null_high > 0 or null_low > 0 or null_close > 0:
                issues.append({
                    "market": market,
                    "name": korean_name,
                    "issue": f"가격 NULL/0: 시가={null_open}, 고가={null_high}, 저가={null_low}, 종가={null_close}",
                    "severity": "HIGH",
                })
                has_issue = True

            if high_lt_low > 0:
                issues.append({
                    "market": market,
                    "name": korean_name,
                    "issue": f"고가 < 저가: {high_lt_low}건",
                    "severity": "HIGH",
                })
                has_issue = True

            if high_lt_open > 0 or high_lt_close > 0:
                issues.append({
                    "market": market,
                    "name": korean_name,
                    "issue": f"고가<시가: {high_lt_open}건, 고가<종가: {high_lt_close}건",
                    "severity": "MEDIUM",
                })
                has_issue = True

            if low_gt_open > 0 or low_gt_close > 0:
                issues.append({
                    "market": market,
                    "name": korean_name,
                    "issue": f"저가>시가: {low_gt_open}건, 저가>종가: {low_gt_close}건",
                    "severity": "MEDIUM",
                })
                has_issue = True

            status = "ISSUE" if has_issue else "OK"
            if idx % 20 == 0 or has_issue:
                logger.info("[%d/%d] %s (%s) - %d캔들 - %s", idx, total, market, korean_name, candle_count, status)

        except Exception as e:
            issues.append({
                "market": market,
                "name": korean_name,
                "issue": f"API 에러: {str(e)}",
                "severity": "HIGH",
            })
            logger.error("[%d/%d] %s (%s) - 에러: %s", idx, total, market, korean_name, str(e))
            time.sleep(1)  # 에러 시 추가 대기

    # 3) 결과 출력
    results_df = pd.DataFrame(all_results)

    print("\n" + "=" * 70)
    print("  검증 결과 요약")
    print("=" * 70)

    print(f"\n총 마켓 수: {len(markets)}개")
    print(f"정상 수집: {len(results_df)}개")
    print(f"이슈 발견: {len(issues)}건")

    if not results_df.empty:
        print(f"\n--- 데이터 통계 ---")
        print(f"평균 캔들 수: {results_df['candles'].mean():.1f}")
        print(f"캔들 수 범위: {results_df['candles'].min()} ~ {results_df['candles'].max()}")

        # NULL/0 가격 총계
        total_null_open = results_df["null_open"].sum()
        total_null_high = results_df["null_high"].sum()
        total_null_low = results_df["null_low"].sum()
        total_null_close = results_df["null_close"].sum()

        print(f"\n--- 가격 NULL/0 검사 ---")
        print(f"시가(Open) NULL/0:  {total_null_open}건 {'✓ 정상' if total_null_open == 0 else '✗ 이상'}")
        print(f"고가(High) NULL/0:  {total_null_high}건 {'✓ 정상' if total_null_high == 0 else '✗ 이상'}")
        print(f"저가(Low) NULL/0:   {total_null_low}건 {'✓ 정상' if total_null_low == 0 else '✗ 이상'}")
        print(f"종가(Close) NULL/0: {total_null_close}건 {'✓ 정상' if total_null_close == 0 else '✗ 이상'}")

        # 가격 논리 검증 총계
        total_hl = results_df["high<low"].sum()
        total_ho = results_df["high<open"].sum()
        total_hc = results_df["high<close"].sum()
        total_lo = results_df["low>open"].sum()
        total_lc = results_df["low>close"].sum()

        print(f"\n--- 가격 논리 검증 ---")
        print(f"고가 < 저가:  {total_hl}건 {'✓ 정상' if total_hl == 0 else '✗ 이상'}")
        print(f"고가 < 시가:  {total_ho}건 {'✓ 정상' if total_ho == 0 else '✗ 이상'}")
        print(f"고가 < 종가:  {total_hc}건 {'✓ 정상' if total_hc == 0 else '✗ 이상'}")
        print(f"저가 > 시가:  {total_lo}건 {'✓ 정상' if total_lo == 0 else '✗ 이상'}")
        print(f"저가 > 종가:  {total_lc}건 {'✓ 정상' if total_lc == 0 else '✗ 이상'}")

    # 이슈 상세
    if issues:
        print(f"\n--- 이슈 상세 ({len(issues)}건) ---")
        issues_df = pd.DataFrame(issues)
        for severity in ["HIGH", "MEDIUM", "LOW"]:
            sev_issues = issues_df[issues_df["severity"] == severity]
            if not sev_issues.empty:
                print(f"\n[{severity}]")
                for _, row in sev_issues.iterrows():
                    print(f"  {row['market']} ({row['name']}): {row['issue']}")
    else:
        print("\n모든 코인 데이터 정상!")

    # 4) 샘플 데이터 출력 (BTC, ETH)
    print(f"\n--- 샘플 데이터 (최근 5일) ---")
    for sample_market in ["KRW-BTC", "KRW-ETH", "KRW-XRP"]:
        try:
            candles = fetch_daily_ohlcv(sample_market, count=5)
            time.sleep(0.12)
            if candles:
                print(f"\n[{sample_market}]")
                for c in candles:
                    date = c["candle_date_time_kst"][:10]
                    o = f"{c['opening_price']:,.0f}"
                    h = f"{c['high_price']:,.0f}"
                    l = f"{c['low_price']:,.0f}"
                    cl = f"{c['trade_price']:,.0f}"
                    vol = f"{c.get('candle_acc_trade_volume', 0):,.2f}"
                    print(f"  {date} | 시가: {o:>15} | 고가: {h:>15} | 저가: {l:>15} | 종가: {cl:>15} | 거래량: {vol}")
        except Exception as e:
            print(f"\n[{sample_market}] 조회 실패: {e}")

    print("\n" + "=" * 70)
    print("  검증 완료")
    print("=" * 70)


if __name__ == "__main__":
    main()
