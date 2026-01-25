import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
import json
from datetime import datetime
import sys

# [1. 환경 변수 로드]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not all([GEMINI_KEY, DISCORD_URL, PINECONE_KEY]):
    print("❌ 환경 변수 설정 누락")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. 고수준 지표 계산 엔진]
def calculate_expert_indicators(df):
    df = df.copy()
    close = df['Close']
    # RSI (13)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    # ATR (14)
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-close.shift()), abs(df['Low']-close.shift())], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    # BB (20, 2)
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    # MACD (12, 26)
    df['MACD'] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    # TDI (Price Line)
    df['TDI_P'] = df['RSI'].rolling(window=2).mean()
    return df

def get_intelligence_data():
    targets = ["^GSPC", "^IXIC", "NVDA", "SOXX", "^TNX"]
    summary = ""
    for t in targets:
        try:
            df = calculate_expert_indicators(yf.download(t, period="100d", progress=False))
            l = df.iloc[-1]
            summary += f"[{t}] P:{round(float(l['Close']),2)} | RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)} | TDI_P:{round(float(l['TDI_P']),1)}\n"
        except: continue
    return summary

# [3. 3인 에이전트 끝장 토론]
def run_supreme_council():
    m = get_intelligence_data()
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=m)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 패턴."
    except: memory = "기억 저장소 연결 중."

    prompt = f"""당신은 Alpha-Trio 2.7 전략 위원회입니다. 아래 데이터를 해부하십시오.
    [데이터]: {m} | [과거 기록]: {memory}

    1. 에이전트 A(Quant): 수급과 지표의 모순을 찾아라.
    2. 에이전트 B(Dewey): 현재를 역사적 변곡점과 대조하여 지식을 증류하라.
    3. 에이전트 C(Beckett): 낙관론을 부정하고 리스크와 손절가를 비판하라.

    반드시 JSON 형식으로만 답하십시오."""
    
    v = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt).text
    return v, m

# [4. 무조건 꽂히는 분할 전송 로직]
def send_safe_discord(content):
    chunks = [content[i:i+1800] for i in range(0, len(content), 1800)]
    for i, chunk in enumerate(chunks):
        msg = f"🏛️ **Alpha-Trio 2.7 판결 ({i+1}/{len(chunks)})**\n```json\n{chunk}\n```"
        res = requests.post(DISCORD_URL, json={"content": msg})
        if res.status_code != 204:
            print(f"❌ 전송 실패: {res.status_code}")
            sys.exit(1)

if __name__ == "__main__":
    print("🚀 Alpha-Trio 2.7 가동...")
    try:
        verdict, raw_data = run_supreme_council()
        # Pinecone 저장
        embed = genai.embed_content(model="models/text-embedding-004", content=raw_data)['embedding']
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        # 전송
        send_safe_discord(verdict)
        print("✅ 가동 완료")
    except Exception as e:
        print(f"🔥 에러: {e}")
        sys.exit(1)