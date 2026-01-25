import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Cone
import json
from datetime import datetime

# [환경 설정]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

genai.configure(api_key=GEMINI_KEY)
# Pinecone 연결 (버전에 따라 처리)
try:
    from pinecone import Pinecone
    pc = Pinecone(api_key=PINECONE_KEY)
    index = pc.Index("alpha-trio-memory")
except:
    pass

def calculate_indicators_pure(df):
    """라이브러리 없이 직접 계산하는 5대 지표"""
    close = df['Close']
    high = df['High']
    low = df['Low']

    # 1. RSI (Relative Strength Index)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # 2. ATR (Average True Range)
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()

    # 3. Bollinger Bands (20, 2)
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU_20_2.0'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BBL_20_2.0'] = df['BB_Mid'] - (df['BB_Std'] * 2)

    # 4. MACD (12, 26, 9)
    exp1 = close.ewm(span=12, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # 5. TDI (Traders Dynamic Index) - RSI 기반 계산
    # Price Line (Green), Signal Line (Red), Market Base (Yellow)
    df['TDI_P'] = df['RSI'].rolling(window=2).mean()
    df['TDI_S'] = df['RSI'].rolling(window=7).mean()
    df['TDI_M'] = df['RSI'].rolling(window=34).mean()
    # Volatility Band (RSI 기반의 볼린저밴드)
    rsi_std = df['RSI'].rolling(window=34).std()
    df['TDI_VB_Upper'] = df['TDI_M'] + (rsi_std * 1.618)
    df['TDI_VB_Lower'] = df['TDI_M'] - (rsi_std * 1.618)
    
    return df

def get_intelligence():
    targets = ["^GSPC", "^IXIC", "^TNX", "NVDA", "LLY", "SOXX"]
    summary = ""
    for t in targets:
        try:
            df = yf.download(t, period="100d", progress=False)
            df = calculate_indicators_pure(df)
            l, p = df.iloc[-1], df.iloc[-2]
            change = ((l['Close'] - p['Close']) / p['Close']) * 100
            summary += f"[{t}] P:{round(float(l['Close']),2)}({round(float(change),2)}%) | RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)} | TDI_P:{round(float(l['TDI_P']),1)}\n"
        except: continue
    
    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    news = "\n".join([f"- {a['title']}" for a in news_res.get('articles', [])[:5]])
    return summary, news

def alpha_trio_final():
    m, n = get_intelligence()
    # 과거 기억 소환 (생략 가능하면 에러 방지 위해 예외처리)
    memories = "과거 오답 노트 분석 중..."
    
    prompt = f"""당신은 Alpha-Trio 2.1 위원회입니다. 24시간 분석 결과를 보고하십시오.
    [데이터]: {m} | [뉴스]: {n} | [기억]: {memories}
    에이전트 A(Quant), B(Dewey), C(Beckett)의 토론을 포함해 JSON으로 답하세요."""
    
    response = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt)
    return response.text

if __name__ == "__main__":
    print("🏛️ Alpha-Trio 2.1 엔진 가동 (의존성 제거 버전)...")
    try:
        v = alpha_trio_final()
        requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.1 최종 보고**\n```json\n{v}\n```"})
        print("✅ 가동 완료")
    except Exception as e:
        print(f"❌ 오류: {e}")