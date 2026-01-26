import os
import re
import json
import time
import requests
import traceback
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from openai import OpenAI
from pinecone import Pinecone
from google import genai

# [STAGE 1: 하이퍼-인프라 통합]
client_gemini = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
client_gpt = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
client_kimi = OpenAI(api_key=os.environ.get("KIMI_API_KEY"), base_url="https://api.moonshot.cn/v1")
index = Pinecone(api_key=os.environ.get("PINECONE_API_KEY")).Index("alpha-trio-memory")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# ---------------------------------------------------------
# [STAGE 2: 하이퍼-퀀트 - 5년 시계열 및 복합 지표 연산]
# ---------------------------------------------------------
def run_full_diagnosis():
    """500개 종목의 5년 데이터를 훑으며 VWAP, Beta, TDI, ATR, Z-score 산출"""
    print("🌌 [Stage 2] S&P 500 전 종목 5개년 역사 및 지표 전수 조사 시작...")
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
    tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
    
    # 감독님 명령: 식상한 대형주(AAPL, MSFT, NVDA) 강제 거세
    targets = [t for t in tickers if t not in ["AAPL", "MSFT", "NVDA"]]
    
    # 5년치($5y$) 데이터 다운로드 (1,250영업일)
    raw = yf.download(targets, period="5y", group_by="ticker", progress=False, threads=True)
    mkt = yf.download("^GSPC", period="5y", progress=False)['Close']

    pool = []
    for t in targets:
        try:
            df = raw[t].dropna()
            if len(df) < 500: continue
            c, v, h, l = df['Close'], df['Volume'], df['High'], df['Low']
            
            # 1. Z-score (RSI 기반 5년 희소성)
            diff = c.diff()
            g = diff.where(lambda x: x>0, 0).rolling(14).mean()
            ls = -diff.where(lambda x: x<0, 0).rolling(14).mean().replace(0, 1)
            rsi = 100 - (100 / (1 + (g / ls)))
            z = (rsi.iloc[-1] - rsi.mean()) / rsi.std()
            
            # 2. TDI (Price Line & Market Base Line)
            tdi_pl = rsi.rolling(2).mean().iloc[-1]
            tdi_mbl = rsi.rolling(34).mean().iloc[-1]
            
            # 3. VWAP & ATR & Beta
            vwap = (v * (h + l + c) / 3).cumsum() / v.cumsum()
            atr = (pd.concat([h-l, abs(h-c.shift()), abs(l-c.shift())], axis=1).max(axis=1)).rolling(14).mean()
            atr_r = atr.iloc[-1] / atr.mean()
            
            ret = c.pct_change().dropna()
            m_ret = mkt.pct_change().dropna()
            common = ret.index.intersection(m_ret.index)
            beta = ret.loc[common].cov(m_ret.loc[common]) / m_ret.loc[common].var()

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
# [STAGE 5: 아토믹 딜리버리 - 내용 보존 필터]
# ---------------------------------------------------------
def deliver_stage_5(agent_id, model, raw, m_summary=""):
    """
    [REPORT_START] 태그를 기준으로 통찰을 추출하되, 
    태그가 없으면 원본 전체에서 기계 기호를 삭제하고 전송합니다.
    """
    pattern = r"\[REPORT_START\](.*?)\[REPORT_END\]"
    match = re.search(pattern, raw, re.DOTALL)
    
    if match:
        clean = match.group(1).strip()
    else:
        # 태그 누락 시 비상 공정: JSON 파편 및 특수기호 강제 삭제
        clean = re.sub(r'[\{\}\[\]""]', '', raw)
        clean = re.sub(r'[a-zA-Z0-9_]+:', '', clean).strip()

    if not clean or len(clean) < 20:
        clean = "⚠️ 분석 결과가 생성되지 않았습니다. 모델의 출력 길이를 확인하십시오."
    
    emoji = {"A": "📉", "B": "💡", "C": "💀"}.get(agent_id, "🏛️")
    title = {"A": "수량적 수급 인과 해부", "B": "역사적 지능 기반 전략", "C": "실존적 리스크 오답노트"}.get(agent_id)
    
    header = f"### 📊 [Market Summary]\n{m_summary}\n\n" if agent_id == "A" else ""
    msg = f"{header}## {emoji} {title}\n**Agent {agent_id} ({model})**\n---\n{clean}\n"
    
    # 2000자 초과 방지 분할 전송
    for i in range(0, len(msg), 1900):
        requests.post(DISCORD_URL, json={"content": msg[i:i+1900]})
        time.sleep(1)

if __name__ == "__main__":
    try:
        m_sum = "S&P500 Top50 내 과매수 종목은 3개... 강력한 상승 모멘텀 부재 및 관망세 짙음."
        analysis_stats = run_full_diagnosis()
        
        # 에이전트들에게 지독하게 상세한 분석을 명령하는 '하이퍼-프롬프트'
        rule = (
            "반드시 [REPORT_START]와 [REPORT_END] 태그를 사용하라. "
            "VWAP, Beta, TDI, ATR, Z-score를 5년 역사와 대조하여 '왜' 이 종목이 아웃라이어인지 최소 500자 이상 상세히 해부하라. "
            "요약은 죽음이다. 소설처럼 깊게 써라."
        )
        
        # Agent A: Gemini 가동
        res_a = client_gemini.models.generate_content(
            model="gemini-1.5-pro", 
            contents=f"{rule}\n분석 데이터: {json.dumps(analysis_stats)}"
        ).text
        deliver_stage_5("A", "Gemini 1.5 Pro", res_a, m_sum)
        
        # Agent B: GPT-4o 가동
        res_b = client_gpt.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": f"{rule}\nA의 분석을 기반으로 전략을 써라: {res_a}"}]
        ).choices[0].message.content
        deliver_stage_5("B", "GPT-4o", res_b)
        
        # Agent C: Kimi 가동
        res_c = client_kimi.chat.completions.create(
            model="moonshot-v1-8k", 
            messages=[{"role": "user", "content": f"{rule}\n위 모든 분석을 비웃으며 오답노트를 써라: {res_b}"}]
        ).choices[0].message.content
        deliver_stage_5("C", "Kimi", res_c)

    except Exception as e:
        print(f"🔥 Critical Failure: {e}")
        traceback.print_exc()