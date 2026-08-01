#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
walk_forward.py  —  노드 조합의 '진짜 실력' 검증 (아웃오브샘플).

문제의식: 앞서 '그 해 3배 간 종목'을 사후에 골라 조합을 맞추면 +700%도 나오지만
그건 커브피팅이다. 여기서는 종목을 미리 고르지 않고, 넓은 유동성 유니버스 '전체'에
같은 노드 조합을 적용한다. 그리고 기간을 둘로 쪼갠다:

  TRAIN(학습): 2024-08-01 ~ 2025-01-31  →  이 구간에서 성적 좋은 조합을 '선택'
  TEST(검증) : 2025-02-01 ~ 2025-08-01  →  '선택한 조합'을 처음 보는 이 구간에 적용

각 종목에 ₩1,000,000씩 독립 투자했다고 보고, 조합별로 전 종목의
'중앙값 수익률(median)'을 성과 지표로 쓴다. TRAIN 상위 조합이 TEST에서도
살아남는지(=일반화되는지)를 본다. 대부분 TRAIN보다 TEST가 나빠지면 = 과최적화.

데이터: FinanceData/marcap parquet (오프라인 KRX 일봉).
실행 : python3 walk_forward.py --marcap /tmp/marcap/data
"""
import argparse
import numpy as np
import pandas as pd
import kquant_node_backtest as kq

WARMUP_START = "2024-03-01"     # 지표 워밍업용(장기 SMA 등)
TRAIN = (pd.Timestamp("2024-08-01"), pd.Timestamp("2025-01-31"))
TEST  = (pd.Timestamp("2025-02-01"), pd.Timestamp("2025-08-01"))
EVAL_START, EVAL_END = TRAIN[0], TEST[1]
CAP = 1_000_000


def load_universe(data_dir, liq_min=3e9, min_rows=240):
    frames = [pd.read_parquet(f"{data_dir}/marcap-{y}.parquet",
              columns=["Code", "Name", "Date", "Open", "High", "Low", "Close", "Volume", "Amount"])
              for y in (2024, 2025)]
    big = pd.concat(frames, ignore_index=True)
    ev = big[(big.Date >= EVAL_START) & (big.Date <= EVAL_END)]
    names = ev.groupby("Code")["Name"].last()
    # 유동성/상장 필터는 평가구간 기준
    keep = [c for c, g in ev.groupby("Code")
            if len(g) >= min_rows and g["Amount"].median() >= liq_min]
    # 실제 백테스트는 워밍업 포함 구간으로
    full = big[(big.Date >= pd.Timestamp(WARMUP_START)) & (big.Date <= EVAL_END)]
    data = {}
    for c in keep:
        g = full[full.Code == c].set_index("Date").sort_index()[["Open", "High", "Low", "Close", "Volume"]].dropna()
        g = g[g["Close"] > 0]
        if len(g) >= min_rows:
            data[c] = g
    return data, names


def win_mult(eq: pd.Series, s, e):
    seg = eq.loc[s:e]
    if len(seg) < 2 or seg.iloc[0] <= 0:
        return np.nan
    return seg.iloc[-1] / seg.iloc[0]


def entry_singles():
    out = []
    for name, (fn, space) in kq.ENTRY_NODES.items():
        for p in kq.param_grid(space):
            if name == "MA_cross" and p["fast"] >= p["slow"]:
                continue  # 단기≥장기면 크로스 없음(무의미) → 제외
            out.append((name, fn, p))
    return out


def buyhold_benchmark(data):
    tr, te = [], []
    for g in data.values():
        c = g["Close"]
        tr.append(win_mult(c, *TRAIN)); te.append(win_mult(c, *TEST))
    return np.nanmedian(tr), np.nanmedian(te)


def run(data_dir, liq_min, topn):
    data, names = load_universe(data_dir, liq_min)
    print(f"유니버스: {len(data)}종목 (거래대금 중앙값 ≥ {liq_min/1e8:.0f}억, 전기간 상장)")
    print(f"TRAIN {TRAIN[0].date()}~{TRAIN[1].date()}  |  TEST {TEST[0].date()}~{TEST[1].date()}\n")

    bh_tr, bh_te = buyhold_benchmark(data)
    print(f"[벤치마크] 단순보유(Buy&Hold) 중앙값수익  TRAIN {(bh_tr-1)*100:+.1f}%   TEST {(bh_te-1)*100:+.1f}%\n")

    singles = entry_singles()
    combos = []
    for (nm, fn, p) in singles:
        for ex in kq.EXIT_MENU:
            combos.append((f"{nm}|{ '/'.join(f'{k}={v}' for k,v in p.items()) or 'def'}",
                           [(nm, fn, p)], ex))

    rows = []
    for label, nodes, ex in combos:
        tr_m, te_m, tr_win, te_win, trades = [], [], [], [], []
        for g in data.values():
            try:
                entry = kq.build_entry(g, nodes)
            except Exception:
                continue
            eq, tcnt = kq.backtest_single(g, entry, ex, CAP)
            a = win_mult(eq, *TRAIN); b = win_mult(eq, *TEST)
            if not np.isnan(a): tr_m.append(a); tr_win.append(a > 1)
            if not np.isnan(b): te_m.append(b); te_win.append(b > 1)
            trades.append(tcnt)
        if len(tr_m) < 30:
            continue
        rows.append(dict(
            combo=label, exit=ex.label(),
            IS_med=(np.median(tr_m)-1)*100, OOS_med=(np.median(te_m)-1)*100,
            IS_mean=(np.mean(tr_m)-1)*100, OOS_mean=(np.mean(te_m)-1)*100,
            OOS_winrate=np.mean(te_win)*100, avg_trades=np.mean(trades),
            n=len(tr_m),
        ))

    res = pd.DataFrame(rows)
    res = res[res["avg_trades"] >= 0.3]   # 실제로 매매가 일어난 조합만
    # TRAIN 성적으로 '선택'(중앙값 우선, 동률이면 평균) → 그 조합들의 TEST 성적을 본다
    best_is = res.sort_values(["IS_med", "IS_mean"], ascending=False).head(topn).copy()

    print("=" * 96)
    print(f"TRAIN 상위 {topn} 조합을 선택 → 같은 조합의 TEST(처음 보는 구간) 성적")
    print("=" * 96)
    show = best_is[["combo", "exit", "IS_med", "OOS_med", "OOS_winrate", "avg_trades"]].copy()
    for c in ["IS_med", "OOS_med", "OOS_winrate"]:
        show[c] = show[c].map(lambda x: f"{x:+.1f}%" if "winrate" not in c else f"{x:.0f}%")
    show = show.rename(columns={"IS_med": "학습(중앙값)", "OOS_med": "검증(중앙값)",
                                "OOS_winrate": "검증승률", "avg_trades": "평균매매"})
    print(show.to_string(index=False))

    # 판정
    picked = best_is.iloc[0]
    print("\n" + "-" * 96)
    print("판정")
    print(f"  · TRAIN 최고 조합: {picked['combo']} + {picked['exit']}")
    print(f"      학습 중앙값 {picked['IS_med']:+.1f}%  →  검증 중앙값 {picked['OOS_med']:+.1f}%  (검증 승률 {picked['OOS_winrate']:.0f}%)")
    degr = picked["IS_med"] - picked["OOS_med"]
    if picked["OOS_med"] <= 0:
        verdict = "❌ 검증 구간에서 손실/무익 → 과최적화. 이 조합은 미래에 신뢰 불가."
    elif picked["OOS_med"] < picked["IS_med"] * 0.4:
        verdict = "⚠️ 검증에서 성과가 크게 줄어듦(과최적화 경향). 실전 신중."
    else:
        verdict = "🟢 검증에서도 양(+)의 성과 유지 → 상대적으로 견고. 그래도 분산·리스크관리 필수."
    print(f"  · {verdict}")

    # TEST 기준으로도 가장 견고한(검증 중앙값 최고) 조합 별도 표시
    best_oos = res.sort_values("OOS_med", ascending=False).iloc[0]
    print("\n  참고) 검증(OOS) 자체 중앙값이 가장 높은 조합:")
    print(f"      {best_oos['combo']} + {best_oos['exit']}  →  검증 중앙값 {best_oos['OOS_med']:+.1f}% (승률 {best_oos['OOS_winrate']:.0f}%), 학습 {best_oos['IS_med']:+.1f}%")
    print("-" * 96)
    print("\n※ 이건 '종목을 미리 고르지 않고' 전 종목 평균으로 조합의 실력을 본 것입니다.")
    print("  ₩100만→₩400만 같은 대박은 개별 대박종목을 맞혀야 나오며, 그건 사후에만 알 수 있습니다.")
    print("  현실적 기대치는 위 '검증 중앙값'에 가깝고, 분산투자·손절로 리스크를 통제해야 합니다.")

    res.sort_values("IS_med", ascending=False).to_csv("walkforward_results.csv", index=False)
    print("\n(전체 조합 성적 → walkforward_results.csv 저장)")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--marcap", default="/tmp/marcap/data")
    ap.add_argument("--liq", type=float, default=3e9, help="유동성 하한(거래대금 중앙값)")
    ap.add_argument("--topn", type=int, default=12)
    a = ap.parse_args()
    run(a.marcap, a.liq, a.topn)
