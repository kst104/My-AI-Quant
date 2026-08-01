#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kquant_node_backtest.py
────────────────────────────────────────────────────────────────────────────
한국 주식 "노드 조합" 백테스트 엔진 (localhost:3000 노드 빌더 아이디어를 코드로).

목표 예시: ₩1,000,000 로 시작해 1년 일봉으로 여러 '노드 조합'을 백테스트하고,
          자산이 ₩4,000,000(= 수익 ₩3,000,000)에 도달하는 가장 좋은 조합과
          '도달까지 걸린 기간'을 찾아 보고한다.

⚠️  중요(꼭 읽으세요): 과거 데이터에서 목표 수익(예: 300%)에 '맞는' 조합을
    사후적으로 고르는 것은 본질적으로 커브피팅(과최적화)입니다. 아래 결과는
    "과거에 이랬다"일 뿐, 미래 수익을 보장하지 않습니다. 검증(워크포워드/아웃오브
    샘플)과 리스크 관리 없이는 실매매에 쓰지 마세요.

노드 개념
─────────
- 지표 노드   : SMA, EMA, RSI, MACD, Bollinger, ATR, Momentum, VolMA
- 조건 노드   : cross_up/down, price_above_sma, rsi_below/above, breakout ...
- 논리 노드   : AND / OR (여러 조건 노드를 조합 → 이게 "노드들의 조합")
- 진입 노드   : 조합된 진입조건이 참이고 현금 상태면 매수
- 청산 노드   : 목표수익(TP) / 손절(SL) / 트레일링 / 기간청산 / 신호청산
- 사이징 노드 : 자본의 몇 %를 태울지

데이터
──────
로컬에서 실행하세요(이 저장소를 clone 한 당신의 Mac). 아래 중 하나:
  1) CSV 폴더:  각 종목 CSV(Date,Open,High,Low,Close,Volume) →  --csv ./data
  2) FinanceDataReader:  pip install finance-datareader  →  --fdr 005930,247540,...
  (원격 CI 환경에서는 금융 데이터 host 가 막혀 있어 --demo 합성데이터만 됩니다.)

사용 예
───────
  python3 kquant_node_backtest.py --demo                      # 합성데이터 자체검증
  python3 kquant_node_backtest.py --fdr 247540,091990,293490 --start 2024-08-01 --end 2025-08-01
  python3 kquant_node_backtest.py --csv ./data --target 4000000 --capital 1000000
"""
from __future__ import annotations
import argparse
import itertools
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# ────────────────────────── 비용 가정(한국 주식) ──────────────────────────
BUY_FEE  = 0.00015          # 매수 수수료 ~0.015%
SELL_FEE = 0.00015 + 0.0018 # 매도 수수료 + 거래세(0.18%, 코스피 기준 2024)
SLIPPAGE = 0.0010           # 편도 슬리피지 0.1% (체결 불리 가정)


# ══════════════════════════ 1) 지표 노드 ══════════════════════════
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean().replace(0, np.nan)
    rs = up / dn
    return (100 - 100 / (1 + rs)).fillna(50)

def macd(s: pd.Series, fast=12, slow=26, sig=9):
    line = ema(s, fast) - ema(s, slow)
    signal = ema(line, sig)
    return line, signal

def bollinger(s: pd.Series, n=20, k=2.0):
    mid = sma(s, n)
    sd = s.rolling(n).std()
    return mid - k * sd, mid, mid + k * sd

def atr(df: pd.DataFrame, n=14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def momentum(s: pd.Series, n=20) -> pd.Series:
    return s / s.shift(n) - 1.0


# ══════════════════════════ 2) 진입 조건 노드(→ bool 시리즈) ══════════════════════════
# 각 함수는 df 를 받아 "진입 신호 bool 시리즈"를 반환. params 로 세부값 조정.
def entry_ma_cross(df, p):
    c = df["Close"]
    f, s = sma(c, p["fast"]), sma(c, p["slow"])
    return (f > s) & (f.shift() <= s.shift())          # 골든크로스

def entry_breakout(df, p):
    c = df["Close"]
    hh = df["High"].rolling(p["look"]).max().shift(1)
    return c > hh                                       # n일 신고가 돌파

def entry_rsi_dip(df, p):
    c = df["Close"]
    r = rsi(c, p["rsi_n"])
    trend = c > sma(c, p["trend"])                      # 상승추세에서만
    return (r < p["rsi_buy"]) & trend                   # 눌림목 과매도 반등

def entry_macd(df, p):
    line, sig = macd(df["Close"])
    return (line > sig) & (line.shift() <= sig.shift()) & (line < 0)  # 저점 골든

def entry_boll_breakout(df, p):
    c = df["Close"]
    _, _, up = bollinger(c, p["bb_n"], p["bb_k"])
    return (c > up) & (c.shift() <= up.shift())         # 밴드 상단 돌파(추세)

def entry_momentum(df, p):
    c = df["Close"]
    mom = momentum(c, p["mom_n"])
    return (mom > p["mom_th"]) & (c > sma(c, p["trend"]))

ENTRY_NODES = {
    "MA_cross":       (entry_ma_cross,     dict(fast=[5,10,20], slow=[20,60,120])),
    "Breakout":       (entry_breakout,     dict(look=[20,40,60])),
    "RSI_dip":        (entry_rsi_dip,      dict(rsi_n=[14], rsi_buy=[30,35,40], trend=[60,120])),
    "MACD_gc":        (entry_macd,         dict()),
    "Boll_breakout":  (entry_boll_breakout,dict(bb_n=[20], bb_k=[2.0,2.5])),
    "Momentum":       (entry_momentum,     dict(mom_n=[20,60], mom_th=[0.10,0.20], trend=[60,120])),
}


# ══════════════════════════ 3) 논리 노드: 진입조건 조합 ══════════════════════════
def combine_and(sigs):  # 여러 진입조건을 AND (노드들의 조합)
    out = sigs[0].copy()
    for s in sigs[1:]:
        out = out & s
    return out


# ══════════════════════════ 4) 청산 노드 설정 ══════════════════════════
@dataclass
class ExitCfg:
    tp: float | None = None      # 목표수익률 (예: 0.15 = +15%)
    sl: float | None = None      # 손절률     (예: 0.07 = -7%)
    trail: float | None = None   # 트레일링스탑 (고점 대비 %)
    max_hold: int | None = None  # 최대 보유 봉수(기간청산)
    exit_below_sma: int | None = None  # 종가가 SMA(n) 하회 시 청산

    def label(self):
        parts = []
        if self.tp: parts.append(f"TP{int(self.tp*100)}")
        if self.sl: parts.append(f"SL{int(self.sl*100)}")
        if self.trail: parts.append(f"TR{int(self.trail*100)}")
        if self.max_hold: parts.append(f"HOLD{self.max_hold}")
        if self.exit_below_sma: parts.append(f"<SMA{self.exit_below_sma}")
        return "+".join(parts) or "none"


EXIT_MENU = [
    ExitCfg(tp=0.20, sl=0.08),
    ExitCfg(tp=0.30, sl=0.10),
    ExitCfg(trail=0.12),
    ExitCfg(trail=0.08, sl=0.10),
    ExitCfg(exit_below_sma=20, sl=0.10),
    ExitCfg(tp=0.15, sl=0.06, max_hold=15),
]


# ══════════════════════════ 5) 단일 종목 백테스트(롱, 1포지션) ══════════════════════════
def backtest_single(df: pd.DataFrame, entry: pd.Series, ex: ExitCfg,
                    capital: float, size: float = 1.0):
    """진입신호 entry(bool) + 청산 ExitCfg 로 자본 곡선/체결을 계산."""
    c = df["Close"].values
    high = df["High"].values
    idx = df.index
    sma_exit = sma(df["Close"], ex.exit_below_sma).values if ex.exit_below_sma else None
    entry = entry.reindex(df.index).fillna(False).values

    cash = capital
    shares = 0.0
    in_pos = False
    buy_px = peak = 0.0
    held = 0
    equity = np.empty(len(df))
    trades = 0

    for i in range(len(df)):
        px = c[i]
        # ── 청산 판정(보유 중) ──
        if in_pos:
            held += 1
            peak = max(peak, high[i])
            ret = px / buy_px - 1.0
            hit = None
            if ex.sl is not None and ret <= -ex.sl: hit = "SL"
            elif ex.tp is not None and ret >= ex.tp: hit = "TP"
            elif ex.trail is not None and px <= peak * (1 - ex.trail): hit = "TRAIL"
            elif ex.max_hold is not None and held >= ex.max_hold: hit = "TIME"
            elif sma_exit is not None and not math.isnan(sma_exit[i]) and px < sma_exit[i]: hit = "SMA"
            if hit:
                cash = shares * px * (1 - SELL_FEE - SLIPPAGE)
                shares = 0.0; in_pos = False; trades += 1
        # ── 진입 판정(현금 상태) ──
        if (not in_pos) and entry[i] and cash > 0:
            invest = cash * size
            eff_px = px * (1 + SLIPPAGE)
            shares = invest * (1 - BUY_FEE) / eff_px
            cash -= invest
            buy_px = px; peak = high[i]; held = 0; in_pos = True
        equity[i] = cash + shares * px

    eq = pd.Series(equity, index=idx)
    return eq, trades


# ══════════════════════════ 6) 성과 지표 ══════════════════════════
def first_cross_date(eq: pd.Series, target: float):
    hit = eq[eq >= target]
    return hit.index[0] if len(hit) else None

def max_drawdown(eq: pd.Series) -> float:
    roll = eq.cummax()
    return float(((eq - roll) / roll).min())

def summarize(eq: pd.Series, trades: int, capital: float, target: float):
    final = float(eq.iloc[-1])
    d = first_cross_date(eq, target)
    days = None
    if d is not None:
        days = (d - eq.index[0]).days
    return dict(
        final=final,
        ret_pct=(final / capital - 1) * 100,
        mdd_pct=max_drawdown(eq) * 100,
        trades=trades,
        reached=d is not None,
        reach_date=(str(d.date()) if d is not None else None),
        reach_days=days,
    )


# ══════════════════════════ 7) 조합 탐색 ══════════════════════════
def param_grid(space: dict):
    if not space:
        return [dict()]
    keys = list(space.keys())
    return [dict(zip(keys, vals)) for vals in itertools.product(*[space[k] for k in keys])]

def entry_variants():
    """모든 단일 진입노드 + (노드 2개 AND 조합)까지 생성."""
    singles = []
    for name, (fn, space) in ENTRY_NODES.items():
        for p in param_grid(space):
            singles.append((name, fn, p))
    variants = [("1|" + n, [(n, fn, p)]) for (n, fn, p) in singles]
    # 노드 2개 AND 조합(대표값만: 과다 조합 방지를 위해 각 노드의 첫 파라미터 사용)
    reps = {}
    for name, (fn, space) in ENTRY_NODES.items():
        reps[name] = (fn, param_grid(space)[0])
    names = list(reps.keys())
    for a, b in itertools.combinations(names, 2):
        variants.append((f"2|{a}&{b}",
                         [(a, reps[a][0], reps[a][1]), (b, reps[b][0], reps[b][1])]))
    return variants

def build_entry(df, node_list):
    sigs = [fn(df, p) for (_, fn, p) in node_list]
    return combine_and(sigs)

def search_ticker(ticker, df, capital, target):
    rows = []
    for vlabel, nodes in entry_variants():
        try:
            entry = build_entry(df, nodes)
        except Exception:
            continue
        for ex in EXIT_MENU:
            eq, tr = backtest_single(df, entry, ex, capital)
            s = summarize(eq, tr, capital, target)
            s.update(ticker=ticker, entry=vlabel, exit=ex.label())
            s["_eq"] = eq
            rows.append(s)
    return rows


# ══════════════════════════ 8) 데이터 로더 ══════════════════════════
def load_csv_dir(path: str) -> dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(Path(path).glob("*.csv")):
        df = pd.read_csv(f, parse_dates=["Date"]).set_index("Date").sort_index()
        need = {"Open", "High", "Low", "Close"}
        if not need.issubset(df.columns):
            print(f"  skip {f.name}: 컬럼 부족 {need - set(df.columns)}"); continue
        if "Volume" not in df: df["Volume"] = 0
        out[f.stem] = df
    return out

def load_fdr(tickers, start, end) -> dict[str, pd.DataFrame]:
    try:
        import FinanceDataReader as fdr  # 로컬에서만 동작
    except ImportError:
        print("FinanceDataReader 미설치.  →  pip install finance-datareader")
        sys.exit(1)
    out = {}
    for t in tickers:
        try:
            df = fdr.DataReader(t, start, end)
            df = df.rename(columns=str.title)[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(df) > 30:
                out[t] = df
                print(f"  loaded {t}: {len(df)} rows")
            else:
                print(f"  skip {t}: rows={len(df)} (기간/티커 확인)")
        except Exception as e:
            msg = repr(e)
            if "403" in msg or "ProxyError" in msg or "Tunnel" in msg:
                print(f"  {t} 데이터 host 차단(403). 이 환경(원격/CI)에선 금융 데이터가 막혀 있습니다.")
                print("  → 당신 Mac(로컬)에서 실행하거나, --csv 로 내보낸 CSV를 쓰세요.")
                sys.exit(2)
            print(f"  {t} 로드 실패: {msg[:120]}")
    return out

def make_demo(n_tickers=6, days=252, seed=7) -> dict[str, pd.DataFrame]:
    """합성 일봉: 일부 종목에 큰 추세를 심어 엔진 동작을 자체검증."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-08-01", periods=days)
    out = {}
    for k in range(n_tickers):
        drift = rng.choice([0.0003, 0.001, 0.0025, -0.0005])   # 종목별 추세 강도
        vol = rng.uniform(0.015, 0.035)
        shock = np.zeros(days)
        # 무작위 급등 구간(추세추종이 잡을 수 있게)
        for _ in range(rng.integers(1, 3)):
            st = rng.integers(20, days - 40); ln = rng.integers(15, 35)
            shock[st:st+ln] += rng.uniform(0.004, 0.012)
        ret = rng.normal(drift, vol, days) + shock
        close = 10000 * np.exp(np.cumsum(ret))
        high = close * (1 + rng.uniform(0, 0.02, days))
        low = close * (1 - rng.uniform(0, 0.02, days))
        openp = close * (1 + rng.uniform(-0.01, 0.01, days))
        vol_ = rng.integers(1e5, 1e6, days)
        out[f"DEMO{k+1}"] = pd.DataFrame(
            dict(Open=openp, High=high, Low=low, Close=close, Volume=vol_), index=dates)
    return out


# ══════════════════════════ 9) 리포트 ══════════════════════════
def run(data: dict[str, pd.DataFrame], capital: float, target: float, topn: int = 10):
    all_rows = []
    for t, df in data.items():
        all_rows += search_ticker(t, df, capital, target)
    if not all_rows:
        print("결과 없음(데이터 확인)"); return

    res = pd.DataFrame(all_rows)
    reached = res[res.reached].copy()

    print("\n" + "=" * 78)
    print(f"자본 ₩{capital:,.0f}  →  목표 ₩{target:,.0f} (수익 ₩{target-capital:,.0f})")
    print(f"종목 {len(data)}개 · 조합 {len(res):,}개 백테스트")
    print("=" * 78)

    if len(reached):
        # 목표 도달한 것 중 '가장 빨리' 도달한 조합 우선
        best = reached.sort_values(["reach_days", "final"], ascending=[True, False])
        print(f"\n✅ 목표 도달 조합: {len(reached):,}개 — 도달 빠른 순 Top{topn}\n")
        cols = ["ticker", "entry", "exit", "final", "ret_pct", "reach_days", "reach_date", "mdd_pct", "trades"]
        show = best[cols].head(topn).copy()
        show["final"] = show["final"].map(lambda x: f"{x:,.0f}")
        show["ret_pct"] = show["ret_pct"].map(lambda x: f"{x:+.0f}%")
        show["mdd_pct"] = show["mdd_pct"].map(lambda x: f"{x:.0f}%")
        print(show.to_string(index=False))
        top = best.iloc[0]
        print("\n" + "-" * 78)
        print("🏆 최고 조합(가장 빨리 목표 도달)")
        print(f"  종목      : {top.ticker}")
        print(f"  진입 노드 : {top.entry}")
        print(f"  청산 노드 : {top.exit}")
        print(f"  최종 자산 : ₩{top.final:,.0f}  ({top.ret_pct:+.0f}%)")
        print(f"  도달 기간 : {top.reach_days}일 (첫 도달일 {top.reach_date})")
        print(f"  최대낙폭  : {top.mdd_pct:.0f}%  ·  체결 {top.trades}회")
        print("-" * 78)
    else:
        print("\n❌ 목표에 도달한 조합이 과거 데이터엔 없습니다. "
              "가장 성과 좋은 조합 Top{}:\n".format(topn))
        best = res.sort_values("final", ascending=False)
        cols = ["ticker", "entry", "exit", "final", "ret_pct", "mdd_pct", "trades"]
        show = best[cols].head(topn).copy()
        show["final"] = show["final"].map(lambda x: f"{x:,.0f}")
        show["ret_pct"] = show["ret_pct"].map(lambda x: f"{x:+.0f}%")
        show["mdd_pct"] = show["mdd_pct"].map(lambda x: f"{x:.0f}%")
        print(show.to_string(index=False))

    print("\n⚠️  주의: 위는 과거 데이터에 맞춘 결과(커브피팅 위험). 미래 수익 보장 아님.")
    print("    실전 적용 전 반드시 아웃오브샘플/워크포워드 검증과 리스크 관리를 하세요.")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="종목 CSV 폴더 경로")
    ap.add_argument("--fdr", help="FinanceDataReader 티커들, 쉼표구분 (예: 005930,247540)")
    ap.add_argument("--start", default="2024-08-01")
    ap.add_argument("--end", default="2025-08-01")
    ap.add_argument("--demo", action="store_true", help="합성데이터 자체검증")
    ap.add_argument("--capital", type=float, default=1_000_000)
    ap.add_argument("--target", type=float, default=4_000_000)  # 수익 300만 = 자산 400만
    ap.add_argument("--topn", type=int, default=10)
    a = ap.parse_args()

    if a.demo:
        data = make_demo()
    elif a.csv:
        data = load_csv_dir(a.csv)
    elif a.fdr:
        data = load_fdr([t.strip() for t in a.fdr.split(",")], a.start, a.end)
    else:
        print("데이터 소스를 지정하세요: --demo | --csv <dir> | --fdr <tickers>")
        sys.exit(1)

    if not data:
        print("데이터가 비었습니다."); sys.exit(1)
    run(data, a.capital, a.target, a.topn)


if __name__ == "__main__":
    main()
