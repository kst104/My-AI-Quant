#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
두 노드 조합의 월별 수익 · MDD · 하락장 방어력 비교 (실 KRX 데이터).

포트폴리오 구성: ₩1,000,000 을 유동성 유니버스(368종목)에 '균등 분산'.
각 종목에 동일 자본을 주고 해당 노드 조합의 진입/청산을 따르며(청산 후 현금),
전 종목 자산을 합산 → 조합의 '분산 포트폴리오' 자산곡선.
벤치마크: 같은 유니버스 균등 '단순보유(Buy&Hold)'.
"""
import numpy as np
import pandas as pd
import kquant_node_backtest as kq

DATA = "/tmp/marcap/data"
WARMUP = pd.Timestamp("2024-03-01")
EVS, EVE = pd.Timestamp("2024-08-01"), pd.Timestamp("2025-08-01")
TOTAL = 1_000_000

COMBOS = {
    "MACD_gc + TR12": ([("MACD_gc", kq.ENTRY_NODES["MACD_gc"][0], {})], kq.ExitCfg(trail=0.12)),
    "MA10/20 + TR12": ([("MA_cross", kq.ENTRY_NODES["MA_cross"][0], {"fast": 10, "slow": 20})], kq.ExitCfg(trail=0.12)),
}

def load():
    fr = [pd.read_parquet(f"{DATA}/marcap-{y}.parquet",
          columns=["Code","Date","Open","High","Low","Close","Volume","Amount"]) for y in (2024,2025)]
    big = pd.concat(fr, ignore_index=True)
    ev = big[(big.Date>=EVS)&(big.Date<=EVE)]
    keep = [c for c,g in ev.groupby("Code") if len(g)>=240 and g["Amount"].median()>=3e9]
    full = big[(big.Date>=WARMUP)&(big.Date<=EVE)]
    data={}
    for c in keep:
        g=full[full.Code==c].set_index("Date").sort_index()[["Open","High","Low","Close","Volume"]].dropna()
        g=g[g["Close"]>0]
        if len(g)>=240: data[c]=g
    return data

def eval_index(data):
    idx=set()
    for g in data.values():
        idx |= set(g.loc[EVS:EVE].index)
    return pd.DatetimeIndex(sorted(idx))

def rebase(eq, idx, cap):
    seg = eq.loc[EVS:EVE]
    if len(seg)<2 or seg.iloc[0]<=0: return None
    seg = seg / seg.iloc[0] * cap
    return seg.reindex(idx).ffill().bfill()

def portfolio(data, idx, nodes, ex):
    cap = TOTAL/len(data)
    tot = pd.Series(0.0, index=idx)
    for g in data.values():
        try: entry=kq.build_entry(g,nodes)
        except Exception: continue
        eq,_=kq.backtest_single(g,entry,ex,cap)
        r=rebase(eq,idx,cap)
        if r is not None: tot=tot+r
    return tot

def buyhold(data, idx):
    cap=TOTAL/len(data)
    tot=pd.Series(0.0,index=idx)
    for g in data.values():
        c=g["Close"].loc[EVS:EVE]
        if len(c)<2 or c.iloc[0]<=0: continue
        r=(c/c.iloc[0]*cap).reindex(idx).ffill().bfill()
        tot=tot+r
    return tot

def mdd(eq):
    roll=eq.cummax(); return float(((eq-roll)/roll).min())*100

def monthly(eq):
    m=eq.resample("ME").last()
    return m.pct_change().dropna()*100

def main():
    data=load(); idx=eval_index(data)
    print(f"유니버스 {len(data)}종목 · ₩{TOTAL:,} 균등분산 · {EVS.date()}~{EVE.date()}\n")
    bh=buyhold(data,idx)
    curves={"Buy&Hold":bh}
    for name,(nodes,ex) in COMBOS.items():
        curves[name]=portfolio(data,idx,nodes,ex)

    # 월별 수익 표
    mtab=pd.DataFrame({k:monthly(v) for k,v in curves.items()})
    mtab.index=[d.strftime("%Y-%m") for d in mtab.index]
    print("── 월별 수익률(%) ──")
    print(mtab.round(1).to_string())

    print("\n── 요약 ──")
    for k,v in curves.items():
        tot=(v.iloc[-1]/TOTAL-1)*100
        vol=monthly(v).std()
        print(f"  {k:12s}  총수익 {tot:+6.1f}%   MDD {mdd(v):6.1f}%   월변동성 {vol:4.1f}%   최종 ₩{v.iloc[-1]:,.0f}")

    # 하락장 방어력: Buy&Hold 가 마이너스인 달에서 각 전략의 수익
    print("\n── 하락장 방어력 (Buy&Hold 가 마이너스였던 달) ──")
    down = mtab[mtab["Buy&Hold"]<0]
    if len(down):
        print(down.round(1).to_string())
        print("\n  하락달 평균수익:")
        for k in curves: print(f"    {k:12s} {down[k].mean():+.2f}%")
        print("  → 값이 덜 마이너스(또는 플러스)일수록 하락 방어가 좋음.")
    else:
        print("  (하락한 달 없음)")

    # 최악 낙폭 구간 비교
    print("\n── 최대낙폭(MDD) ──")
    for k,v in curves.items():
        roll=v.cummax(); dd=(v-roll)/roll
        tr=dd.idxmin()
        pk=v.loc[:tr].idxmax()
        print(f"  {k:12s} MDD {dd.min()*100:6.1f}%  (고점 {pk.date()} → 저점 {tr.date()})")

    mtab.to_csv("two_combo_monthly.csv")
    print("\n(월별표 → two_combo_monthly.csv)")

if __name__=="__main__":
    main()
