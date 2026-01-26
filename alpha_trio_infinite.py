import os
import sys
import json
import time
import traceback
from datetime import datetime

import requests
import pandas as pd
import yfinance as yf
from pinecone import Pinecone

# [1. 인프라 및 상수 설정]
HTTP_TIMEOUT = 120 # 전수 조사를 위해 타임아웃 확장
UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AlphaTrioBot/5.0",
}

DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def post_discord(content: str):
    try:
        requests.post(DISCORD_URL, json={"content": content}, timeout=30)
    except: pass

# -------------------------
# 🧠 Gemini & Intelligence (REST)
# -------------------------
def pick_gemini_model() -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    r = requests.get(url, timeout=30)
    if r.status_code != 200: raise Exception("ListModels 실패")
    models = [m["name"] for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    # pro 모델 우선, 없으면 flash
    pro_models = [m for m in models if "pro" in m]
    return pro_models[0] if pro_models else models[0]

def call_gemini(prompt: str) -> str:
    model = pick_gemini_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.8, "maxOutputTokens": 2048}}
    r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def get_embedding(text: str):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={GEMINI_KEY}"
    payload = {"model": "models/text-embedding-004", "content": {"parts": [{"text": text[:5000]}]}}
    r = requests.post(url, json=payload, timeout=30)
    return r.json()["embedding"]["values"]

# -------------------------
# 📊 Market Scan (500+ Stocks, 5y)
# -------------------------
def calculate_expert_indicators(df: pd.DataFrame):
    if df.empty or len(df) < 40: return None
    df = df.copy()
    close = df["Close"]
    
    # 볼린저 밴드 ($BB$)
    mid = close.rolling(window=20).mean()
    std = close.rolling(window=20).std()
    df["BBU"] = mid + (std * 2)
    df["BBL"] = mid - (std * 2)
    
    # RSI & 정교한 TDI ($TDI$)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df["RSI"] = 100 - (100 / (1 + (gain / loss.replace(0, pd.NA))))
    
    # TDI 핵심: $TDI_{PL} = SMA(RSI, 2)$, $TDI_{MBL} = SMA(RSI, 34)$
    df["TDI_PL"] = df["RSI"].rolling(window=2).mean()
    df["TDI_MBL"] = df["RSI"].rolling(window=34).mean()
    
    return df.dropna()

def explore_sp500_infinity():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 가동...")
    try:
        # Wikipedia에서 500개 티커 로드
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=UA_HEADERS, timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        
        # 5년($5y$) 데이터 배치 다운로드
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        stats = {"Overbought": 0, "Oversold": 0, "U-Break": 0, "L-Break": 0}
        sector_sentiment = {}
        highlights = []

        for t in tickers:
            try:
                sub = data[t].dropna() if t in data.columns.get_level_values(0) else None
                df = calculate_expert_indicators(sub)
                if df is None: continue
                
                l = df.iloc[-1]
                price, rsi, tdi_pl, tdi_mbl, bbu, bbl = l["Close"], l["RSI"], l["TDI_PL"], l["TDI_MBL"], l["BBU"], l["BBL"]
                
                # 통계 수집
                if rsi > 70: stats["Overbought"] += 1
                if rsi < 30: stats["Oversold"] += 1
                if price > bbu: stats["U-Break"] += 1
                if price < bbl: stats["L-Break"] += 1
                
                # 주요 지표주 상세 샘플
                if t in ["AAPL", "NVDA", "MSFT", "TSLA", "GOOGL", "AMZN"]:
                    highlights.append(f"[{t}] P:{round(price,2)} | RSI:{round(rsi,1)} | TDI(PL/MBL):{round(tdi_pl,1)}/{round(tdi_mbl,1)}")
            except: continue
            
        summary = f"📊 S&P500 전수조사(5y): 과매수({stats['Overbought']}), BB상단돌파({stats['U-Break']}), 하단이탈({stats['L-Break']})\n"
        return summary + "\n".join(highlights)
    except Exception as e:
        return f"전수 조사 지연: {repr(e)}"

# -------------------------
# 🏛️ Main Execution
# -------------------------
if __name__ == "__main__":
    print(f"🧾 build: {datetime.utcnow().isoformat()}")
    try:
        # 1. 데이터 수집 (전수조사 + 뉴스)
        m_data = explore_sp500_infinity()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}", timeout=30).json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]]) if 'articles' in n_res else "뉴스 지연"

        # 2. 기억과 지능의 융합
        brain_input = f"지표:\n{m_data}\n\n뉴스:\n{n_data}"
        vector = get_embedding(brain_input)
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past["matches"][0]["metadata"]["conclusion"] if past.get("matches") else "첫 번째 자가학습 단계."

        # 3. 정예 에이전트 삼각 편대 (Role-Play 강화)
        prompt = f"""당신은 S&P 500 전수 조사를 마친 초지능 Alpha-Trio 위원회입니다. 
        [지표 데이터]: {m_data}
        [뉴스]: {n_data}
        [과거 기억]: {memory}

        에이전트별 미션:
        1. A(Quant): 500개 종목의 $RSI$, $TDI$, $BB$ 분포도를 통해 시장 전체의 '쏠림 현상'을 수치로 비판하라. 특히 $TDI_{PL}$과 $MBL$의 이격을 분석하라.
        2. B(John Dewey): 실시간 뉴스와 5개년 지표를 결합하여 현재가 어떤 '경험적 질서'를 형성하는지 지식을 증류하라.
        3. C(Samuel Beckett): 과거의 기억(실패)을 소환하여 너희의 낙관을 조롱하라. '더 낫게 실패하라'는 관점에서 리스크를 설계하라.

        반드시 JSON 형식으로만 답하고, Action(매수/매도/관망)과 Confidence_Score를 포함하십시오."""

        verdict = call_gemini(prompt)

        # 4. 저장 및 보고
        index.upsert(vectors=[{
            "id": str(datetime.now().timestamp()),
            "values": vector,
            "metadata": {"conclusion": verdict, "date": str(datetime.now())}
        }])

        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            post_discord(f"🏛️ **Alpha-Trio Infinite V2 최종 판결**\n```json\n{chunk}\n```")

        print("✅ 자가학습 및 전수 조사 완료.")

    except Exception as e:
        print("🔥 치명적 에러 자백:", repr(e))
        traceback.print_exc()
        sys.exit(1)