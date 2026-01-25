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
    """수학적으로 정교하게 계산된 5대 지표"""
    df = df.copy()
    close = df['Close']
    
    # 1. RSI (13)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))

    # 2. ATR (14)
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-close.shift()), abs(df['Low']-close.shift())], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()

    # 3. Bollinger Bands (20, 2)
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)

    # 4. MACD (12, 26)
    df['MACD'] = close.ewm(span=12).mean() - close.ewm(span=26).mean()

    # 5. TDI (Traders Dynamic Index)
    df['TDI_P'] = df['RSI'].rolling(window=2).mean() # Price
    df['TDI_S'] = df['RSI'].rolling(window=7).mean() # Signal
    df['TDI_M'] = df['RSI'].rolling(window=34).mean() # Market
    return df

def get_market_data():
    targets = ["^GSPC", "^IXIC", "NVDA", "LLY", "SOXX"]
    summary = ""
    for t in targets:
        try:
            df = calculate_pure_logic(yf.download(t, period="100d", progress=False))
            l = df.iloc[-1]
            summary += f"[{t}] P:{round(float(l['Close']),2)} | RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)} | TDI_P:{round(float(l['TDI_P']),1)}\n"
        except: continue
    return summary

def alpha_trio_supreme():
    m = get_market_data()
    # 뉴스 수집
    news = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    n_str = "\n".join([f"- {a['title']}" for a in news.get('articles', [])[:5]])
    
    # 과거 기억 소환
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=m)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 패턴 분석 중."
    except: memory = "기억 저장소 연결 중."

    prompt = f"""당신은 Alpha-Trio 2.5 전략 위원회입니다.
    데이터: {m} | 뉴스: {n_str} | 과거 오답노트: {memory}
    
    1. 에이전트 A(Quant): 지표 수급의 탄력성을 수학적으로 해부하라.
    2. 에이전트 B(Dewey): 과거와 현재의 인과관계를 찾아 지식을 증류하라.
    3. 에이전트 C(Beckett): 낙관론을 파괴하고 최악의 시나리오를 제시하라.
    
    반드시 아래 JSON 형식으로만 답하세요:
    {{
      "Action": "매수/매도/관망",
      "Strategy_Name": "전략 별칭",
      "Debate": {{ "A": "의견", "B": "의견", "C": "의견" }},
      "Self_Reflection": "과거 오답 대비 오늘의 성찰",
      "Knowledge_Distilled": "오늘의 핵심 투자 원칙",
      "Targets": {{ "Entry": "0", "TP": "0", "SL": "0" }}
    }}"""
    
    v = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt).text
    return v, m

if __name__ == "__main__":
    try:
        verdict, raw_data = alpha_trio_supreme()
        # Pinecone 저장
        embed = genai.embed_content(model="models/text-embedding-004", content=raw_data)['embedding']
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        # 디스코드 보고
        requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.5 최종 보고**\n```json\n{verdict}\n```"})
        print("✅ 가동 완료")
    except Exception as e:
        print(f"❌ 오류: {e}")