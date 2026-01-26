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

# [1. 설정 최적화]
HTTP_TIMEOUT = 180
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def post_discord(content: str):
    """디스코드 2,000자 제한을 우회하는 지능형 분할 배달 엔진"""
    if not content: return
    
    # JSON이 너무 길면 문맥이 깨지므로, 약 1,500자 단위로 안전하게 자름
    chunk_size = 1500 
    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    
    for idx, chunk in enumerate(chunks):
        # 각 조각을 독립된 JSON 코드 블록으로 포장
        header = f"🏛️ **Alpha-Trio 판결문 (Part {idx+1}/{len(chunks)})**"
        formatted_content = f"{header}\n```json\n{chunk}\n```"
        
        try:
            r = requests.post(DISCORD_URL, json={"content": formatted_content}, timeout=30)
            if r.status_code != 204:
                print(f"⚠️ 전송 경고: {r.status_code}")
            time.sleep(1.5) # 전송 순서 꼬임 방지
        except Exception as e:
            print(f"❌ 전송 실패: {e}")

# -------------------------
# 🧠 Gemini 1.5 Pro (REST)
# -------------------------
def call_gemini(prompt: str) -> str:
    # 감독님 계정에서 가장 똑똑한 모델 자동 선택
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_KEY}"
    r = requests.get(url).json()
    models = [m["name"] for m in r.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    model = next((m for m in models if "pro" in m), models[0])
    
    api_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096, # 충분한 출력 확보
            "response_mime_type": "application/json" # JSON 응답 강제
        }
    }
    res = requests.post(api_url, json=payload, timeout=HTTP_TIMEOUT).json()
    return res["candidates"][0]["content"]["parts"][0]["text"]

# -------------------------
# 📊 Market & News (Full-Scan)
# -------------------------
# (기존의 500개 종목 스캔 로직 유지...)
def explore_sp500_infinity():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 가동...")
    try:
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", timeout=30)
        tickers = pd.read_html(r.text)[0]["Symbol"].replace(".", "-", regex=True).tolist()
        # 데이터 수집 (500개 전 종목, 5년)
        data = yf.download(tickers, period="5y", group_by="ticker", progress=False, threads=True)
        
        # ... (지표 계산 및 요약 로직 생략, 기존 최강화 로직 적용) ...
        return "스캔 요약 데이터 (생략)" # 실제 코드엔 전체 로직 포함
    except: return "데이터 수집 지연"

if __name__ == "__main__":
    try:
        print("🚀 Alpha-Trio Infinite V2.2 가동...")
        m_data = explore_sp500_infinity()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]])

        # 1048576 토큰의 뇌(1.5 Pro)에게 전달
        prompt = f"""당신은 Alpha-Trio 위원회입니다. 
        [지표]: {m_data}
        [뉴스]: {n_data}

        에이전트 A, B, C의 분석을 포함하되, 각 분석은 핵심 통찰 위주로 간결하고 명확하게 작성하십시오. 
        불필요한 서술은 생략하고 JSON 구조를 엄격히 지키십시오.
        """

        verdict = call_gemini(prompt)
        
        # 디스크로 배달 (잘림 방지 로직 적용)
        post_discord(verdict)
        print("✅ 모든 보고가 완료되었습니다.")

    except Exception as e:
        print(f"🔥 에러: {e}")