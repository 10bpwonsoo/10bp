"""
전략 분석 & 백테스팅 실행 스크립트
- Upbit API에서 주요 코인 일봉 데이터 로드
- 5개 전략 백테스팅 및 성과 비교
- 현재 시그널 분석
"""

import time
import logging
from datetime import datetime

import numpy as np
import pandas as pd
import requests

logging.basicConfig(level=logging.WARNING)

BASE_URL = "https://api.upbit.com/v1"
session = requests.Session()
session.headers.update({"Accept": "application/json"})


# ─── 데이터 로드 ────────────────────────────
def load_ohlcv(market, count=200):
    resp = session.get(
        f"{BASE_URL}/candles/days",
        params={"market": market, "count": count},
        timeout=10,
    )
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
    return df.sort_values("datetime").reset_index(drop=True)


# ─── 기술적 지표 (인라인) ────────────────────
def sma(s, p):
    return s.rolling(p, min_periods=p).mean()

def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def calc_rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0.0)
    l = -d.where(d < 0, 0.0)
    ag = g.ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    al = l.ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_macd(s, fast=12, slow=26, sig=9):
    ml = ema(s, fast) - ema(s, slow)
    sl = ema(ml, sig)
    return ml, sl, ml - sl

def calc_bb(s, p=20, n=2.0):
    mid = sma(s, p)
    std = s.rolling(p, min_periods=p).std()
    return mid + n*std, mid, mid - n*std

def calc_stoch(h, l, c, k_p=14, d_p=3):
    ll = l.rolling(k_p, min_periods=k_p).min()
    hh = h.rolling(k_p, min_periods=k_p).max()
    k = 100 * (c - ll) / (hh - ll).replace(0, np.nan)
    k = k.rolling(3, min_periods=1).mean()
    d = k.rolling(d_p, min_periods=1).mean()
    return k, d

def calc_atr(h, l, c, p=14):
    pc = c.shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/p, min_periods=p, adjust=False).mean()


# ─── 전략 시그널 생성 ────────────────────────
def signal_golden_cross(df, short_p=5, long_p=20):
    c = df["close"]
    s_ma = sma(c, short_p)
    l_ma = sma(c, long_p)
    if pd.isna(s_ma.iloc[-2]) or pd.isna(l_ma.iloc[-1]):
        return "HOLD", "데이터 부족", 0
    ps, pl = s_ma.iloc[-2], l_ma.iloc[-2]
    cs, cl = s_ma.iloc[-1], l_ma.iloc[-1]
    if ps <= pl and cs > cl:
        return "BUY", f"골든크로스 (SMA{short_p} > SMA{long_p})", min(abs(cs-cl)/cl*10, 1)
    if ps >= pl and cs < cl:
        return "SELL", f"데드크로스 (SMA{short_p} < SMA{long_p})", min(abs(cl-cs)/cl*10, 1)
    return "HOLD", f"교차 없음 (단기={cs:,.0f} 장기={cl:,.0f})", 0

def signal_rsi(df, period=14, oversold=30, overbought=70):
    r = calc_rsi(df["close"], period)
    cr, pr = r.iloc[-1], r.iloc[-2]
    if pd.isna(cr):
        return "HOLD", "RSI 미산출", 0
    if pr <= oversold and cr > oversold:
        return "BUY", f"RSI 과매도 탈출 ({pr:.1f}->{cr:.1f})", min((oversold-pr)/oversold, 1)
    if pr >= overbought and cr < overbought:
        return "SELL", f"RSI 과매수 탈출 ({pr:.1f}->{cr:.1f})", min((pr-overbought)/30, 1)
    return "HOLD", f"RSI={cr:.1f} (중립)", 0

def signal_bb(df, period=20, num_std=2.0):
    upper, mid, lower = calc_bb(df["close"], period, num_std)
    cc, pc = df["close"].iloc[-1], df["close"].iloc[-2]
    ul, ll = upper.iloc[-1], lower.iloc[-1]
    pu, pl2 = upper.iloc[-2], lower.iloc[-2]
    if pd.isna(ul):
        return "HOLD", "밴드 미산출", 0
    pct_b = (cc - ll) / (ul - ll) if ul != ll else 0.5
    if pc <= pl2 and cc > ll:
        return "BUY", f"하단밴드 반등 (%B={pct_b:.2f})", min(1-pct_b, 1) if pct_b < 0.5 else 0.5
    if pc >= pu and cc < ul:
        return "SELL", f"상단밴드 반락 (%B={pct_b:.2f})", min(pct_b, 1) if pct_b > 0.5 else 0.5
    return "HOLD", f"밴드 내부 (%B={pct_b:.2f})", 0

def signal_macd(df, fast=12, slow=26, sig_p=9):
    ml, sl, hist = calc_macd(df["close"], fast, slow, sig_p)
    ch, ph = hist.iloc[-1], hist.iloc[-2]
    if pd.isna(ch) or pd.isna(ph):
        return "HOLD", "MACD 미산출", 0
    if ph <= 0 and ch > 0:
        return "BUY", f"MACD 골든크로스 (hist={ch:.2f})", min(abs(ch)/(abs(ml.iloc[-1])+1e-10), 1)
    if ph >= 0 and ch < 0:
        return "SELL", f"MACD 데드크로스 (hist={ch:.2f})", min(abs(ch)/(abs(ml.iloc[-1])+1e-10), 1)
    return "HOLD", f"MACD 유지 (hist={ch:.2f})", 0

def signal_combined(df):
    signals = [
        signal_golden_cross(df),
        signal_rsi(df),
        signal_bb(df),
        signal_macd(df),
    ]
    score_map = {"BUY": 1, "SELL": -1, "HOLD": 0}
    total = sum(score_map[s[0]] * s[2] for s in signals) / 4
    if total >= 0.3:
        return "BUY", f"복합 BUY (score={total:.3f})", min(abs(total), 1)
    elif total <= -0.3:
        return "SELL", f"복합 SELL (score={total:.3f})", min(abs(total), 1)
    return "HOLD", f"복합 HOLD (score={total:.3f})", 0


# ─── 백테스터 ────────────────────────────────
def backtest(df, signal_func, name, capital=10_000_000, commission=0.0005, slippage=0.001):
    cap = capital
    pos = 0.0
    entry_price = 0.0
    trades = []
    equity = []

    for i in range(30, len(df)):
        window = df.iloc[:i+1]
        price = df["close"].iloc[i]
        eq = cap + pos * price
        equity.append(eq)

        sig, reason, conf = signal_func(window)

        if sig == "BUY" and pos == 0 and cap > 0:
            bp = price * (1 + slippage)
            pos = cap * (1 - commission) / bp
            entry_price = bp
            cap = 0

        elif sig == "SELL" and pos > 0:
            sp = price * (1 - slippage)
            proceeds = pos * sp * (1 - commission)
            pnl_pct = (sp - entry_price) / entry_price * 100
            trades.append({"pnl_pct": pnl_pct, "entry": entry_price, "exit": sp})
            cap = proceeds
            pos = 0
            entry_price = 0

    # 잔여 포지션 청산
    if pos > 0:
        sp = df["close"].iloc[-1] * (1 - slippage)
        proceeds = pos * sp * (1 - commission)
        pnl_pct = (sp - entry_price) / entry_price * 100
        trades.append({"pnl_pct": pnl_pct, "entry": entry_price, "exit": sp})
        cap = proceeds
        pos = 0

    eq_series = pd.Series(equity) if equity else pd.Series([capital])
    final = cap
    total_ret = (final - capital) / capital * 100

    # MDD
    cummax = eq_series.cummax()
    dd = (eq_series - cummax) / cummax
    mdd = dd.min() * 100

    # 승률
    wins = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    # 샤프비율
    daily_ret = eq_series.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if len(daily_ret) > 1 and daily_ret.std() > 0 else 0

    # 평균 수익률
    avg_pnl = np.mean([t["pnl_pct"] for t in trades]) if trades else 0

    # 연환산
    days = len(equity)
    ann_ret = ((final/capital) ** (365/days) - 1) * 100 if days > 0 else 0

    return {
        "strategy": name,
        "total_return_%": round(total_ret, 2),
        "annual_return_%": round(ann_ret, 2),
        "mdd_%": round(mdd, 2),
        "win_rate_%": round(win_rate, 1),
        "trades": len(trades),
        "sharpe": round(sharpe, 2),
        "avg_pnl_%": round(avg_pnl, 2),
        "final_capital": round(final),
    }


# ─── 메인 ────────────────────────────────────
def main():
    target_markets = [
        ("KRW-BTC", "비트코인"),
        ("KRW-ETH", "이더리움"),
        ("KRW-XRP", "리플"),
        ("KRW-SOL", "솔라나"),
        ("KRW-DOGE", "도지코인"),
    ]

    strategies = [
        (signal_golden_cross, "GoldenCross (SMA 5/20)"),
        (signal_rsi, "RSI (14, 30/70)"),
        (signal_bb, "BollingerBand (20, 2σ)"),
        (signal_macd, "MACD (12/26/9)"),
        (signal_combined, "Combined (복합)"),
    ]

    print("=" * 90)
    print("  Upbit 자동매매 전략 분석 리포트")
    print(f"  분석 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)

    # ─── 전략 설명 ───
    print("\n" + "=" * 90)
    print("  [전략 종류 및 설명]")
    print("=" * 90)
    print("""
  1. GoldenCross (골든크로스/데드크로스)
     - 단기 SMA(5일)가 장기 SMA(20일)을 상향돌파 → 매수
     - 단기 SMA(5일)가 장기 SMA(20일)을 하향돌파 → 매도
     - 추세 추종 전략, 중장기 트렌드 포착에 강점

  2. RSI (상대강도지수)
     - RSI(14일)가 30 이하에서 반등 → 매수 (과매도 탈출)
     - RSI(14일)가 70 이상에서 하락 → 매도 (과매수 탈출)
     - 역추세 전략, 과열/침체 구간 반전 포착

  3. BollingerBand (볼린저밴드)
     - 가격이 하단밴드(20일 SMA - 2σ) 아래에서 복귀 → 매수
     - 가격이 상단밴드(20일 SMA + 2σ) 위에서 복귀 → 매도
     - 변동성 기반 평균회귀 전략

  4. MACD (이동평균수렴확산)
     - MACD 히스토그램이 음→양 전환 → 매수
     - MACD 히스토그램이 양→음 전환 → 매도
     - 모멘텀 + 추세 복합 전략

  5. Combined (복합 전략)
     - 위 4개 전략의 신호를 가중 투표로 합산
     - 합산 점수 >= 0.3 → 매수, <= -0.3 → 매도
     - 다수결 기반 노이즈 필터링
""")

    # ─── 코인별 분석 ───
    for market, name in target_markets:
        print("=" * 90)
        print(f"  [{market}] {name}")
        print("=" * 90)

        try:
            df = load_ohlcv(market, count=200)
            time.sleep(0.15)
        except Exception as e:
            print(f"  데이터 로드 실패: {e}\n")
            continue

        latest = df.iloc[-1]
        print(f"\n  최신 데이터: {latest['datetime'].strftime('%Y-%m-%d')}")
        print(f"  현재가: {latest['close']:,.0f}원")
        print(f"  데이터 범위: {df['datetime'].iloc[0].strftime('%Y-%m-%d')} ~ {df['datetime'].iloc[-1].strftime('%Y-%m-%d')} ({len(df)}일)")

        # 기술적 지표 현황
        c = df["close"]
        r = calc_rsi(c)
        ml, sl_line, hist = calc_macd(c)
        upper, mid, lower = calc_bb(c)
        k, d = calc_stoch(df["high"], df["low"], c)
        atr_val = calc_atr(df["high"], df["low"], c)

        print(f"\n  --- 기술적 지표 현황 ---")
        print(f"  SMA(5):   {sma(c,5).iloc[-1]:>15,.0f}   SMA(20):  {sma(c,20).iloc[-1]:>15,.0f}   SMA(60): {sma(c,60).iloc[-1]:>15,.0f}")
        print(f"  EMA(12):  {ema(c,12).iloc[-1]:>15,.0f}   EMA(26):  {ema(c,26).iloc[-1]:>15,.0f}")
        print(f"  RSI(14):  {r.iloc[-1]:>8.1f}  {'(과매수)' if r.iloc[-1] > 70 else '(과매도)' if r.iloc[-1] < 30 else '(중립)'}")
        print(f"  MACD:     {ml.iloc[-1]:>12.2f}   Signal:  {sl_line.iloc[-1]:>12.2f}   Hist: {hist.iloc[-1]:>12.2f}")
        bb_pctb = (c.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]) if upper.iloc[-1] != lower.iloc[-1] else 0.5
        print(f"  BB상단:   {upper.iloc[-1]:>15,.0f}   BB중간:  {mid.iloc[-1]:>15,.0f}   BB하단: {lower.iloc[-1]:>15,.0f}  (%B={bb_pctb:.2f})")
        print(f"  Stoch %K: {k.iloc[-1]:>8.1f}   %D: {d.iloc[-1]:>8.1f}")
        print(f"  ATR(14):  {atr_val.iloc[-1]:>15,.0f}")

        # 현재 시그널
        print(f"\n  --- 현재 전략 시그널 ---")
        for sig_func, sig_name in strategies:
            sig, reason, conf = sig_func(df)
            marker = {"BUY": "[매수]", "SELL": "[매도]", "HOLD": "[관망]"}[sig]
            print(f"  {sig_name:30s} → {marker:6s} (신뢰도: {conf:.2f}) | {reason}")

        # 백테스팅
        print(f"\n  --- 백테스팅 결과 (최근 {len(df)}일, 초기자본 1,000만원) ---")
        bt_results = []
        for sig_func, sig_name in strategies:
            result = backtest(df, sig_func, sig_name)
            bt_results.append(result)

        bt_df = pd.DataFrame(bt_results)
        # 테이블 출력
        print(f"  {'전략':30s} | {'총수익률':>9s} | {'연환산':>9s} | {'MDD':>8s} | {'승률':>7s} | {'거래수':>5s} | {'샤프':>6s} | {'평균PnL':>8s} | {'최종자본':>13s}")
        print("  " + "-" * 115)
        for _, row in bt_df.iterrows():
            ret_mark = "+" if row["total_return_%"] > 0 else ""
            print(f"  {row['strategy']:30s} | {ret_mark}{row['total_return_%']:>8.2f}% | {row['annual_return_%']:>8.2f}% | {row['mdd_%']:>7.2f}% | {row['win_rate_%']:>6.1f}% | {row['trades']:>5d} | {row['sharpe']:>6.2f} | {row['avg_pnl_%']:>7.2f}% | {row['final_capital']:>12,.0f}원")

        # 최적 전략 추천
        if not bt_df.empty:
            best = bt_df.loc[bt_df["total_return_%"].idxmax()]
            print(f"\n  >> 최적 전략: {best['strategy']} (수익률 {best['total_return_%']:+.2f}%, 샤프 {best['sharpe']:.2f})")

        print()

    # ─── 전체 요약 ───
    print("=" * 90)
    print("  [전체 분석 요약]")
    print("=" * 90)
    print("""
  분석 방법론:
  - 최근 200일 일봉 데이터 기반 백테스팅
  - 수수료 0.05%, 슬리피지 0.1% 반영
  - 전액 투자 방식 (시그널 발생 시 전체 자본 투입)

  주요 지표 해석:
  - 총수익률: 초기 자본 대비 최종 수익률
  - 연환산 수익률: 연간 기준으로 환산한 수익률
  - MDD: 최대 낙폭 (고점 대비 최대 하락 비율)
  - 승률: 이익 거래 / 전체 거래
  - 샤프비율: 위험 대비 수익 (>1.0 양호, >2.0 우수)
  - 평균 PnL: 거래당 평균 손익률

  유의사항:
  - 과거 성과가 미래 수익을 보장하지 않습니다
  - 실제 매매 시 슬리피지, 유동성 등 추가 비용 발생 가능
  - 시장 상황에 따라 전략 파라미터 조정이 필요합니다
""")


if __name__ == "__main__":
    main()
