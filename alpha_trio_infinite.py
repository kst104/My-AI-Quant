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

# [1. 설정 고도화]
HTTP_TIMEOUT = 180 # 전수 조사를 위해 3분까지 허용
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def post_discord(content: str):
    """디스코드 글자수 제한(2000)을 고려한 지능형 분할 전송"""
    if not content: return
    
    # 1. 마크다운 태그를 포함하여 안전하게 자르기 (1900자 기준)
    limit = 1900
    for i in range(0, len(content), limit):
        chunk = content[i:i+limit]
        # 코드 블록이 깨지지 않도록 앞뒤로 ```json 을 붙여줍니다.
        payload = {
            "content": f"🏛️ **Alpha-Trio 판결문 ({i//limit + 1})**\n```json\n{chunk}\n```"
        }
        try:
            requests.post(DISCORD_URL, json=payload, timeout=30)
            time.sleep(1) # 전송 순서 보장을 위한 미세 지연
        except Exception as e:
            print(f"⚠️ 전송 실패: {e}")

# -------------------------
# 🧠 Gemini API (REST)
# -------------------------
def pick_gemini_model() -> str:
    url = f"[https://generativelanguage.googleapis.com/v1beta/models?key=](https://generativelanguage.googleapis.com/v1beta/models?key=){GEMINI_KEY}"
    try:
        r = requests.get(url, timeout=30).json()
        models = [m["name"] for m in r.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        # pro 모델 우선, 없으면 flash
        pro = [m for m in models if "pro" in m]
        return pro[0] if pro else models[0]
    except: return "models/gemini-1.5-pro"

def call_gemini(prompt: str) -> str:
    model = pick_gemini_model()
    url = f"[https://generativelanguage.googleapis.com/v1beta/](https://generativelanguage.googleapis.com/v1beta/){model}:generateContent?key={GEMINI_KEY}"
    # maxOutputTokens를 4096으로 늘려 답변이 중간에 잘리는 것을 방지합니다.
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 4096,
            "response_mime_type": "application/json" # JSON 응답 강제
        }
    }
    r = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return f"에러 발생: {r.text}"

def get_embedding(text: str):
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=](https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=){GEMINI_KEY}"
    payload = {"model": "models/text-embedding-004", "content": {"parts": [{"text": text[:5000]}]}}
    r = requests.post(url, json=payload, timeout=30).json()
    return r["embedding"]["values"]

# -------------------------
# 📊 Market Scan (S&P 500 Full)
# -------------------------
def explore_sp500_infinity():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 가동...")
    try:
        r = requests.get("[https://en.wikipedia.org/wiki/List_of_S%26P_500_companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies)", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        
        # 5년($5y$) 데이터 배치 다운로드
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        stats = {"Overbought": 0, "Oversold": 0, "U-Break": 0, "L-Break": 0}
        top_movers = []

        for t in tickers:
            try:
                sub = data[t].dropna()
                if len(sub) < 40: continue
                
                close = sub["Close"]
                # 지표 연산 ($BB$, $RSI$, $TDI$)
                mid = close.rolling(20).mean()
                std = close.rolling(20).std()
                rsi = 100 - (100 / (1 + (close.diff().where(lambda x: x>0, 0).rolling(13).mean() / 
                                        -close.diff().where(lambda x: x<x, 0).rolling(13).mean().replace(0, 1))))
                
                curr_p = close.iloc[-1]
                curr_rsi = rsi.iloc[-1]
                
                if curr_rsi > 70: stats["Overbought"] += 1
                if curr_p > (mid.iloc[-1] + std.iloc[-1]*2): stats["U-Break"] += 1
                
                if t in ["AAPL", "NVDA", "TSLA", "MSFT"]:
                    top_movers.append(f"[{t}] P:{round(curr_p,2)} | RSI:{round(curr_rsi,1)}")
            except: continue
            
        return f"📊 S&P500 전수결과: 과매수({stats['Overbought']}), BB상단돌파({stats['U-Break']})\n" + "\n".join(top_movers)
    except Exception as e:
        return f"지표 수집 실패: {e}"

# -------------------------
# 🏛️ 가동 및 자가학습
# -------------------------
if __name__ == "__main__":
    try:
        m_data = explore_sp500_infinity()
        n_res = requests.get(f"[https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey=](https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey=){NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]])
        
        input_text = f"{m_data}\n{n_data}"
        vector = get_embedding(input_text)
        
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past["matches"][0]["metadata"]["conclusion"] if past.get("matches") else "기록 없음."

        prompt = f"""당신은 Alpha-Trio 위원회입니다. 아래 데이터를 바탕으로 시장을 난도질하십시오.
        지표: {m_data}
        뉴스: {n_data}
        과거기억: {memory}

        1. A(Quant): 500개 종목의 기술적 지표 분포를 통해 시장 광기를 비판하라.
        2. B(Dewey): 현재 상황에서 도출할 수 있는 실천적 지식을 증류하라.
        3. C(Beckett): 과거의 실패를 근거로 현재의 희망을 비웃어라.

        반드시 유효한 JSON 형식으로만 답하십시오."""

        verdict = call_gemini(prompt)

        # Vector DB 저장
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": verdict}}])

        # 분할 전송 실행
        post_discord(verdict)
        print("✅ 루프 완료.")

    except Exception as e:
        print(f"🔥 에러: {e}")
        traceback.print_exc()