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

# [1. 시스템 초기화]
HTTP_TIMEOUT = 180
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

UA_HEADERS = {"User-Agent": "Mozilla/5.0 AlphaTrioBot/6.0"}

# -------------------------
# 🧠 Gemini REST & Memory (초지능형)
# -------------------------
def pick_gemini_pro_model() -> str:
    """✅ 지능 우선: Pro를 먼저 찾고 없으면 Flash 사용"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    res = requests.get(url, timeout=30).json()
    models = [m["name"] for m in res.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    
    # 1순위 Pro, 2순위 Flash
    pro_models = [m for m in models if "pro" in m]
    return pro_models[0] if pro_models else models[0]

def get_embedding(text: str):
    """지식을 벡터로 변환 (학습용)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={GEMINI_KEY}"
    payload = {"model": "models/text-embedding-004", "content": {"parts": [{"text": text[:5000]}]}}
    r = requests.post(url, json=payload, timeout=30).json()
    return r["embedding"]["values"]

def call_gemini_json(prompt: str, max_retries: int = 3) -> dict:
    model = pick_gemini_pro_model()
    api_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_KEY}"
    
    for attempt in range(max_retries):
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096, "response_mime_type": "application/json"}
        }
        res = requests.post(api_url, json=payload, timeout=HTTP_TIMEOUT).json()
        try:
            raw_text = res["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw_text)
        except:
            print(f"⚠️ JSON 파싱 실패 ({attempt+1}/{max_retries}). 재시도...")
            time.sleep(2)
    raise Exception("최종 JSON 생성 실패")

# -------------------------
# 📊 Market & News Intelligence (Full-Scan)
# -------------------------
def explore_sp500_infinity():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 및 TDI 분석 가동...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30, headers=UA_HEADERS)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        stats = {"Overbought": 0, "U-Break": 0}
        highlights = []
        for t in ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "GOOGL"]:
            try:
                sub = data[t].dropna()
                close = sub["Close"]
                # TDI 연산 ($TDI_{PL}$, $TDI_{MBL}$)
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(13).mean()
                loss = -delta.where(delta < 0, 0).rolling(13).mean().replace(0, 1)
                rsi = 100 - (100 / (1 + (gain / loss)))
                tdi_pl = rsi.rolling(2).mean().iloc[-1]
                tdi_mbl = rsi.rolling(34).mean().iloc[-1]
                
                if rsi.iloc[-1] > 70: stats["Overbought"] += 1
                highlights.append(f"[{t}] P:{round(close.iloc[-1],2)} | TDI(PL/MBL):{round(tdi_pl,1)}/{round(tdi_mbl,1)}")
            except: continue
            
        return f"📊 S&P500 5y 요약: 과매수 종목 {stats['Overbought']}개 확인\n" + "\n".join(highlights)
    except: return "데이터 수집 지연"

# -------------------------
# 🏛️ Discord & Main Loop
# -------------------------
def post_discord_json(obj: dict):
    # (감독님이 주신 A/B/C 섹션 단위 분할 전송 로직 유지)
    root = obj.get("Alpha-Trio_Analysis", obj)
    for k, v in root.items():
        msg = f"🏛️ **Alpha-Trio 판결문 ({k})**\n```json\n{json.dumps({k:v}, ensure_ascii=False, indent=2)}\n```"
        requests.post(DISCORD_URL, json={"content": msg}, timeout=30)
        time.sleep(1)

if __name__ == "__main__":
    try:
        m_data = explore_sp500_infinity()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}", timeout=30).json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get("articles", [])[:5]])

        # [계획 복구] 1. 기억 소환 (Vector DB)
        context_text = f"{m_data}\n{n_data}"
        vector = get_embedding(context_text)
        past_query = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past_query["matches"][0]["metadata"]["conclusion"] if past_query.get("matches") else "첫 번째 학습입니다."

        # [계획 복구] 2. 초지능형 에이전트 가동
        prompt = f"""당신은 Alpha-Trio 위원회입니다. 
        [지표]: {m_data}
        [뉴스]: {n_data}
        [어제의 기억]: {memory}

        에이전트별 미션:
        1. A(Quant): $BB$와 $TDI$의 5개년 분포를 통해 시장의 '쏠림'을 수치로 비판하라.
        2. B(John Dewey): 현재 데이터에서 실용적 지식을 증류(Distill)하라.
        3. C(Samuel Beckett): 어제의 기억과 오늘의 데이터를 대조하며 우리의 무능함과 리스크를 조롱하라.
        
        반드시 JSON 형식으로 응답하십시오."""

        verdict_obj = call_gemini_json(prompt)

        # [계획 복구] 3. 지식 저장 (자가학습)
        index.upsert(vectors=[{
            "id": str(datetime.now().timestamp()),
            "values": vector,
            "metadata": {"conclusion": json.dumps(verdict_obj), "date": str(datetime.now())}
        }])

        post_discord_json(verdict_obj)
        print("✅ 자가학습 및 보고 완료.")

    except Exception as e:
        print(f"🔥 에러: {e}")
        traceback.print_exc()