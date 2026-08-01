import sys, pandas as pd, numpy as np
import kquant_node_backtest as kq

start, end = pd.Timestamp("2024-08-01"), pd.Timestamp("2025-08-01")
cap, target = 1_000_000, 4_000_000
frames=[pd.read_parquet(f"/tmp/marcap/data/marcap-{y}.parquet",
        columns=["Code","Name","Date","Open","High","Low","Close","Volume","Amount"]) for y in (2024,2025)]
big=pd.concat(frames,ignore_index=True)
big=big[(big.Date>=start)&(big.Date<=end)]
names=big.groupby("Code")["Name"].last()

cand=[]
for code,g in big.groupby("Code"):
    g=g.sort_values("Date")
    if len(g)<200: continue
    if g["Amount"].median() < 1e9: continue
    first=g["Close"].iloc[0]; peak=g["High"].max()
    if first>0 and peak/first>=3.0:
        cand.append((code, peak/first))
cand.sort(key=lambda x:-x[1]); cand=cand[:80]
print(f"후보 종목(기간 중 저점대비 3배+ & 거래대금 중앙값 10억+): {len(cand)}개")

reached=[]
for code,ratio in cand:
    g=big[big.Code==code].set_index("Date").sort_index()[["Open","High","Low","Close","Volume"]].dropna()
    for row in kq.search_ticker(code, g, cap, target):
        if row["reached"]:
            row=dict(row); row.pop("_eq",None); row["name"]=names.get(code,"")
            reached.append(row)

if not reached:
    print("전체 스캔에서도 노드조합으로 ₩400만 도달 케이스 없음.")
else:
    r=pd.DataFrame(reached).sort_values(["reach_days","final"],ascending=[True,False])
    print(f"\n✅ ₩400만(수익300만) 도달 조합: {len(r)}개 — 도달 빠른 순 Top12\n")
    show=r[["ticker","name","entry","exit","final","ret_pct","reach_days","reach_date","mdd_pct","trades"]].head(12).copy()
    show["final"]=show["final"].map(lambda x:f"{x:,.0f}"); show["ret_pct"]=show["ret_pct"].map(lambda x:f"{x:+.0f}%"); show["mdd_pct"]=show["mdd_pct"].map(lambda x:f"{x:.0f}%")
    print(show.to_string(index=False))
    t=r.iloc[0]
    print("\n🏆 가장 빨리 ₩400만 도달")
    print(f"  종목 {t['ticker']} {t['name']} | 진입 {t['entry']} | 청산 {t['exit']}")
    print(f"  최종 ₩{t['final']:,.0f} ({t['ret_pct']:+.0f}%) | 도달 {t['reach_days']}일 (첫도달 {t['reach_date']}) | MDD {t['mdd_pct']:.0f}% | 체결 {t['trades']}회")

# 결과 CSV 저장 + 승자 자산 마일스톤
if reached:
    r.drop(columns=[c for c in ["_eq"] if c in r.columns]).to_csv("/tmp/reached_combos.csv", index=False)
    # 승자 자산곡선 마일스톤
    t=r.iloc[0]
    g=big[big.Code==t["ticker"]].set_index("Date").sort_index()[["Open","High","Low","Close","Volume"]].dropna()
    # 승자 조합 재구성
    import kquant_node_backtest as kq
    # entry 라벨 '1|MA_cross' → 노드 재생성
    nodes=[("MA_cross", kq.ENTRY_NODES["MA_cross"][0], {"fast":5,"slow":20})]
    entry=kq.build_entry(g,nodes)
    ex=kq.ExitCfg(sl=0.10, trail=0.08)
    eq,tr=kq.backtest_single(g,entry,ex,1_000_000)
    print("\n[승자 자산 마일스톤]  (019490, 골든크로스 + 손절10%+트레일링8%)")
    for m in [1_500_000,2_000_000,3_000_000,4_000_000]:
        d=kq.first_cross_date(eq,m)
        print(f"  ₩{m:>9,.0f} 최초도달: {d.date() if d is not None else '미도달'}")
    print(f"  최종(2025-08-01): ₩{eq.iloc[-1]:,.0f}")
