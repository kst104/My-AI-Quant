import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
import json
from datetime import datetime

# [환경 설정]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def calculate_pure_logic(df):
    df = df.copy()
    close = df['Close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-close.shift()), abs(df['Low']-close.shift())], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    return df

def get_market_intelligence():
    targets = ["^GSPC", "^IXIC", "NVDA", "LLY", "SOXX"]
    summary = ""
    for t in targets:
        try:
            df = calculate_pure_logic(yf.download(t, period="100d", progress=False))
            l = df.iloc[-1]
            summary += f"[{t}] P:{round(float(l['Close']),2)} | RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)}\n"
        except: continue
    
    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    news = "\n".join([f"- {a['title']}" for a in news_res.get('articles', [])[:5]])
    return summary, news

def alpha_trio_supreme():
    m, n = get_market_intelligence()
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=m)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 패턴 분석."
    except: memory = "기억 저장소 확인 불가."

    prompt = f"""당신은 Alpha-Trio 2.5 전략 위원회입니다.
    데이터: {m} | 뉴스: {n} | 오답노트: {memory}
    에이전트 A, B, C의 치열한 토론과 지식 증류 결과를 반드시 JSON으로만 답하세요."""
    
    v = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt).text
    return v, m

def send_to_discord(content):
    """디스코드 2,000자 제한을 뚫는 분할 전송 로직"""
    header = "🏛️ **Alpha-Trio 2.5 최종 판결 보고**\n"
    full_message = f"{header}```json\n{content}\n```"
    
    # 1900자 단위로 쪼개서 보냄
    if len(full_message) <= 2000:
        requests.post(DISCORD_URL, json={"content": full_message})
    else:
        chunks = [full_message[i:i+1900] for i in range(0, len(full_message), 1900)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": chunk})

if __name__ == "__main__":
    print("🚀 Alpha-Trio 2.5 가동...")
    try:
        verdict, raw_data = alpha_trio_supreme()
        
        # 1. 지식 증류 저장
        embed = genai.embed_content(model="models/text-embedding-004", content=raw_data)['embedding']
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        # 2. 안전한 전송
        send_to_discord(verdict)
        print("✅ 가동 및 분할 보고 완료")
    except Exception as e:
        print(f"❌ 오류: {e}")