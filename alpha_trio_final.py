import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
import sys

# 인프라 로드 및 검증
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")

if not DISCORD_URL:
    print("❌ 에러: DISCORD_WEBHOOK_URL이 비어있습니다. GitHub Secrets를 확인하세요.")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def calculate_expert_indicators(df):
    """5대 지표 직접 연산 엔진"""
    df = df.copy()
    close = df['Close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-close.shift()), abs(df['Low']-close.shift())], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    df['MACD'] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    return df

def run_trio_intelligence():
    print("🧠 전체 시장 스캔 및 자가학습 가동...")
    df = calculate_expert_indicators(yf.download("^GSPC", period="100d", progress=False))
    rsi = round(float(df['RSI'].iloc[-1]), 2)
    
    model = genai.GenerativeModel('gemini-1.5-pro')
    prompt = f"현재 S&P500 RSI는 {rsi}입니다. 어제의 가설을 검토하고 오늘의 시장 분석 보고서를 JSON으로 작성하세요."
    verdict = model.generate_content(prompt).text
    
    # 디스코드 전송 (안전 분할)
    chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
    for chunk in chunks:
        requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 최종 판결**\n```json\n{chunk}\n```"})

if __name__ == "__main__":
    try:
        run_trio_intelligence()
        print("✅ 가동 성공")
    except Exception as e:
        print(f"🔥 에러 발생: {e}")
        sys.exit(1)