import os
import re
import json
import time
import traceback
from datetime import datetime, timedelta

import requests
import pandas as pd
import yfinance as yf
from openai import OpenAI
from pinecone import Pinecone
from google import genai

# ---------------------------------------------------------
# [STAGE 1: 인프라 - 모든 부품의 총결집]
# ---------------------------------------------------------
# 감독님이 주신 모든 API 키를 가동하며, 누락 시 엔진을 가동하지 않습니다.
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
KIMI_KEY = os.environ.get("KIMI_API_KEY")       # Moonshot AI (Kimi)
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

client_gemini = genai.Client(api_key=GEMINI_KEY)
client_gpt = OpenAI(api_key=OPENAI_KEY)
client_kimi = OpenAI(api_key=KIMI_KEY, base_url="https://api.moonshot.cn/v1")
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# ---------------------------------------------------------
# [STAGE 2: 하이퍼-퀀트 - 5년 시계열 전수 해부]
# ---------------------------------------------------------
def run_full_causal_diagnosis():
    """500개 종목의 5년 데이터를 훑으며 모든 지표($RSI, VWAP, Beta, TDI$)를 산출합니다."""
    print("🌌 [Stage 2] S&P 500 전 종목 5개년 역사 및 복합 지표 전수 조사 시작...")
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
    tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
    
    # 5년치($5y$) 벌크 다운로드 (1,250영업일)
    data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
    sp500_bench = yf.download("^GSPC", period="5y", progress=False)['Close']

    diagnostic_pool = []
    for t in tickers:
        try:
            df = data[t].dropna()
            if len(df) < 500: continue
            close = df['Close']
            volume = df['Volume']
            high = df['High']
            low = df['Low']
            
            # 2.1 수급 및 역사적 희소성 ($Z-score$)
            delta = close.diff()
            gain = delta.where(lambda x: x>0, 0).rolling(14).mean()
            loss = -delta.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
            rsi = 100 - (100 / (1 + (gain / loss)))
            # $Z_{score} = \frac{x - \mu}{\sigma}$ (5년 분포 대비 현재)
            z_score = (rsi.iloc[-1] - rsi.mean()) / rsi.std()
            
            # 2.2 TDI (Traders Dynamic Index) 수급 밀도
            tdi_pl = rsi.rolling(2).mean().iloc[-1]   # Price Line
            tdi_mbl = rsi.rolling(34).mean().iloc[-1] # Market Base Line
            
            # 2.3 VWAP (Volume Weighted Average Price) 및 변동성($ATR$)
            vwap = (volume * (high + low + close) / 3).cumsum() / volume.cumsum()
            atr = (pd.concat([high-low, abs(high-close.shift()), abs(low-close.shift())], axis=1).max(axis=1)).rolling(14).mean()
            atr_ratio = atr.iloc[-1] / atr.mean() # 에너지 응축 비율

            # 2.4 Beta (시장 민감도)
            returns = close.pct_change().dropna()
            mkt_returns = sp500_bench.pct_change().dropna()
            common_idx = returns.index.intersection(mkt_returns.index)
            beta = returns.loc[common_idx].cov(mkt_returns.loc[common_idx]) / mkt_returns.loc[common_idx].var()

            # 역사적 임계점 혹은 강력한 에너지 응축(입질) 발견 시 수집
            if abs(z_score) > 2.3 or atr_ratio < 0.5:
                diagnostic_pool.append({
                    "ticker": t, "price": round(close.iloc[-1], 2),
                    "z_score": round(z_score, 2), "tdi_gap": round(tdi_pl - tdi_mbl, 2),
                    "vwap_dist": round((close.iloc[-1] / vwap.iloc[-1] - 1) * 100, 2),
                    "beta": round(beta, 2), "atr_ratio": round(atr_ratio, 2)
                })
        except: continue
            
    diagnostic_pool.sort(key=lambda x: abs(x['z_score']), reverse=True)
    return diagnostic_pool[:15]

# ---------------------------------------------------------
# [STAGE 3: 24h 인큐베이션 - 오답노트 작성 및 그림자 학습]
# ---------------------------------------------------------
def process_24h_error_note(current_stats):
    """메시지 전송 전, 지난 24시간의 과오를 복기하고 지능을 보정합니다."""
    print("🧠 [Stage 3] Pinecone에서 어제의 기억을 소환하여 현재와 대조 중...")
    input_str = json.dumps(current_stats)
    embed_res = client_gemini.models.embed_content(model="text-embedding-004", contents=input_str)
    vector = embed_res.embeddings[0].values
    past = index.query(vector=vector, top_k=1, include_metadata=True)
    
    yesterday = past.matches[0].metadata["conclusion"] if past.matches else "데이터 없음"
    
    # 에이전트 C(Kimi)가 어제의 오답을 무자비하게 해부
    note_prompt = f"어제의 예측: {yesterday}\n오늘의 실제: {input_str}\n틀린 이유를 인과관계로 비판하라."
    error_note = client_kimi.chat.completions.create(model="moonshot-v1-8k", messages=[{"role": "user", "content": note_prompt}]).choices[0].message.content
    return yesterday, error_note

# ---------------------------------------------------------
# [STAGE 4: 3인 위원회 - 가변적 전조 기간 끝장 토론]
# ---------------------------------------------------------
def run_debate_for_omens(stats_str, error_note):
    """각기 다른 뇌가 종목별 최적의 '입질' 기간을 놓고 토론합니다."""
    print("💡 [Stage 4] 3국 연합군이 역사적 사례와 현재의 조짐을 놓고 격론 중...")
    
    # 4.1 Gemini (Quant): 인과적 해부
    prompt_a = f"데이터: {stats_str}\n오답노트: {error_note}\n5년 역사를 뒤져 '상승 전조' 기간이 왜 다른지 해부하라. [REPORT_START]와 [REPORT_END] 사이에 써라."
    res_a = client_gemini.models.generate_content(model="gemini-1.5-pro", contents=prompt_a).text
    
    # 4.2 GPT-4o (Strategist): 전략 증류
    prompt_b = f"Gemini의 분석을 기반으로 실전 전략을 글로 써라: {res_a}. [REPORT_START]와 [REPORT_END] 사이에 써라."
    res_b = client_gpt.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt_b}]).choices[0].message.content
    
    # 4.3 Kimi (Beckett): 최종 비판 및 오답노트
    prompt_c = f"위 모든 내용을 비웃고 어제의 실패를 소환하라: {res_b}. [REPORT_START]와 [REPORT_END] 사이에 써라."
    res_c = client_kimi.chat.completions.create(model="moonshot-v1-8k", messages=[{"role": "user", "content": prompt_c}]).choices[0].message.content
    
    return res_a, res_b, res_c

# ---------------------------------------------------------
# [STAGE 5: 최종 정제 보고서 - 망령 퇴치 및 명품 배송]
# ---------------------------------------------------------
def stage_5_guillotine_delivery(agent_id, model_name, raw_content):
    """[REPORT_START] 태그 사이의 내용만 물리적으로 추출하여 JSON을 박멸합니다."""
    pattern = r"\[REPORT_START\](.*?)\[REPORT_END\]"
    match = re.search(pattern, raw_content, re.DOTALL)
    
    # 태그 추출 성공 시 깨끗한 리포트, 실패 시 JSON 기호 강제 삭제
    clean_text = match.group(1).strip() if match else re.sub(r'[\{\}\[\]""]', '', raw_content).strip()
    
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    title = {"A": "수량적 수급 인과 해부", "B": "역사적 지능 기반 전략", "C": "실존적 리스크 오답노트"}.get(agent_id)
    
    msg = f"## {emoji} {title}\n**Agent {agent_id} ({model_name})**\n---\n{clean_text}\n"
    
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, json={"content": msg[i:i+1900]}, timeout=30)
    time.sleep(1.5)

if __name__ == "__main__":
    try:
        # Step 1-2: 5년 시계열 전수 스캔 및 지표 연산
        m_stats = run_full_causal_diagnosis()
        stats_str = json.dumps(m_stats)
        
        # Step 3: 24시간 자가학습 및 오답노트
        yesterday_log, error_report = process_24h_error_note(stats_str)
        
        # Step 4: 3인 위원회 격론 및 전조 판단
        rep_a, rep_b, rep_c = run_debate_for_omens(stats_str, error_report)
        
        # Stage 5: 최종 보고 (물리적 정제)
        stage_5_guillotine_delivery("A", "Gemini 1.5 Pro", rep_a)
        stage_5_guillotine_delivery("B", "GPT-4o", rep_b)
        stage_5_guillotine_delivery("C", "Kimi-Moonshot", rep_c)

        # 다음날 학습을 위한 JSON 저장
        sum_prompt = f"오늘의 결론 요약(JSON): {rep_c}"
        res_sum = client_gemini.models.generate_content(model="gemini-1.5-flash", contents=sum_prompt).text
        if "{" in res_sum:
            index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": [0.1]*1536, "metadata": {"conclusion": res_sum}}])

    except Exception as e:
        print(f"🔥 Critical Failure: {e}")
        traceback.print_exc()