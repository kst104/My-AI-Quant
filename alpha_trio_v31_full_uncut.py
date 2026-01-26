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

# [STAGE 1: 하이퍼-인프라 통합]
# 모든 키가 완벽하게 세팅되어야 엔진이 점화됩니다.
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
KIMI_KEY = os.environ.get("KIMI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

client_gemini = genai.Client(api_key=GEMINI_KEY)
client_gpt = OpenAI(api_key=OPENAI_KEY)
client_kimi = OpenAI(api_key=KIMI_KEY, base_url="https://api.moonshot.cn/v1")
index = Pinecone(api_key=PINECONE_KEY).Index("alpha-trio-memory")

# ---------------------------------------------------------
# [STAGE 2: 하이퍼-퀀트 - 5년 시계열 전수 해부]
# ---------------------------------------------------------
def run_full_diagnosis():
    """500개 종목의 5년 데이터를 훑으며 VWAP, Beta, TDI, ATR, Z-score 산출"""
    print("🌌 [Stage 2] S&P 500 전 종목 5개년 역사 전수 조사 시작...")
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
    tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
    
    # 식상한 대형주 3인방 제외 (AAPL, MSFT, NVDA)
    targets = [t for t in tickers if t not in ["AAPL", "MSFT", "NVDA"]]
    
    # 데이터 벌크 다운로드 (5y)
    raw = yf.download(targets, period="5y", group_by="ticker", progress=False, threads=True)
    mkt = yf.download("^GSPC", period="5y", progress=False)['Close']

    pool = []
    for t in targets:
        try:
            df = raw[t].dropna()
            if len(df) < 500: continue
            c, v, h, l = df['Close'], df['Volume'], df['High'], df['Low']
            
            # Z-score (RSI 기반 5년 희소성)
            diff = c.diff()
            g = diff.where(lambda x: x>0, 0).rolling(14).mean()
            ls = -diff.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
            rsi = 100 - (100 / (1 + (g / ls)))
            z = (rsi.iloc[-1] - rsi.mean()) / rsi.std()
            
            # TDI (Price Line - Market Base Line)
            tdi_pl = rsi.rolling(2).mean().iloc[-1]
            tdi_mbl = rsi.rolling(34).mean().iloc[-1]
            
            # VWAP & ATR & Beta
            vwap = (v * (h + l + c) / 3).cumsum() / v.cumsum()
            atr = (pd.concat([h-l, abs(h-c.shift()), abs(l-c.shift())], axis=1).max(axis=1)).rolling(14).mean()
            atr_r = atr.iloc[-1] / atr.mean()
            
            ret = c.pct_change().dropna()
            m_ret = mkt.pct_change().dropna()
            common = ret.index.intersection(m_ret.index)
            beta = ret.loc[common].cov(m_ret.loc[common]) / m_ret.loc[common].var()

            # Z-score 2.3 이상의 '진짜 아웃라이어' 3종목만 선정
            if abs(z) > 2.3:
                pool.append({
                    "ticker": t, "price": round(c.iloc[-1], 2), "z": round(z, 2),
                    "tdi_gap": round(tdi_pl - tdi_mbl, 2), "beta": round(beta, 2),
                    "vwap_dist": round((c.iloc[-1]/vwap.iloc[-1]-1)*100, 2), "atr_r": round(atr_r, 2)
                })
        except: continue
    
    pool.sort(key=lambda x: abs(x['z']), reverse=True)
    return pool[:3]

# ---------------------------------------------------------
# [STAGE 3: 24h 학습 - 오답노트 복기]
# ---------------------------------------------------------
def get_24h_study(current_stats):
    print("🧠 [Stage 3] Pinecone에서 어제의 오답을 꺼내 공부하는 중...")
    stat_str = json.dumps(current_stats)
    vec = client_gemini.models.embed_content(model="text-embedding-004", contents=stat_str).embeddings[0].values
    past = index.query(vector=vec, top_k=1, include_metadata=True)
    
    yesterday = past.matches[0].metadata["conclusion"] if past.matches else "데이터 없음"
    # Kimi에게 비판적 오답노트 작성을 시킴
    res = client_kimi.chat.completions.create(
        model="moonshot-v1-8k",
        messages=[{"role": "user", "content": f"어제의 나: {yesterday}\n오늘의 팩트: {stat_str}\n왜 틀렸는지 해부하라."}]
    )
    return yesterday, res.choices[0].message.content

# ---------------------------------------------------------
# [STAGE 5: 최종 보고서 - 망령 퇴치 (Guillotine)]
# ---------------------------------------------------------
def stage_5_guillotine(agent_id, model, raw, market_sum=""):
    """[REPORT_START] 사이의 글만 물리적으로 도려내서 배달합니다."""
    pattern = r"\[REPORT_START\](.*?)\[REPORT_END\]"
    match = re.search(pattern, raw, re.DOTALL)
    clean = match.group(1).strip() if match else re.sub(r'[\{\}\[\]""]', '', raw).strip()
    
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    header = f"### 📊 [Market Summary]\n{market_sum}\n\n" if agent_id == "A" else ""
    msg = f"{header}## {emoji} Agent {agent_id} ({model})\n---\n{clean}\n"
    
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, json={"content": msg[i:i+1900]})
    time.sleep(1.5)

if __name__ == "__main__":
    try:
        # 감독님이 주신 시장 요약 고정
        m_sum = "S&P500 Top50 내 과매수 종목은 3개... 강력한 상승 모멘텀 부재 및 관망세 짙음."
        
        # 1. 5년 시계열 전수 해부
        stats = run_full_diagnosis()
        
        # 2. 24시간 오답노트 복기
        past_log, error_note = get_24h_study(stats)
        
        # 3. 3인 위원회 토론 (프롬프트에 Stage 5 형식 강제)
        debate_instr = "반드시 [REPORT_START]와 [REPORT_END] 태그를 써라. 기계 언어는 죽여라."
        
        res_a = client_gemini.models.generate_content(model="gemini-1.5-pro", contents=f"{debate_instr}\n데이터: {json.dumps(stats)}\n오답: {error_note}").text
        stage_5_guillotine("A", "Gemini 1.5 Pro", res_a, m_sum)
        
        res_b = client_gpt.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": f"{debate_instr}\n전략 짜라: {res_a}"}]).choices[0].message.content
        stage_5_guillotine("B", "GPT-4o", res_b)
        
        res_c = client_kimi.chat.completions.create(model="moonshot-v1-8k", messages=[{"role": "user", "content": f"{debate_instr}\n비웃어라: {res_b}"}]).choices[0].message.content
        stage_5_guillotine("C", "Kimi", res_c)

    except Exception as e:
        print(f"🔥 공정 중단: {e}")
        traceback.print_exc()