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

# [1. 환경 변수 확인]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 설정 누락 시 즉시 실패(X) 처리
if not all([GEMINI_KEY, DISCORD_URL, PINECONE_KEY]):
    print("❌ 에러: GitHub Secrets 설정이 누락되었습니다.")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. 고수준 지표 계산 엔진: 지능 복구]
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
    # Bollinger Bands (20, 2)
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    # MACD (12, 26)
    df['MACD'] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    # TDI (Price Line)
    df['TDI_P'] = df['RSI'].rolling(window=2).mean()
    return df

def get_full_market_data():
    targets = ["^GSPC", "^IXIC", "NVDA", "SOXX", "^TNX"]
    summary = ""
    for t in targets:
        try:
            df = calculate_expert_indicators(yf.download(t, period="100d", progress=False))
            l = df.iloc[-1]
            p = df.iloc[-2]
            change = ((l['Close'] - p['Close']) / p['Close']) * 100
            summary += f"[{t}] P:{round(float(l['Close']),2)}({round(float(change),2)}%) | RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)} | TDI_P:{round(float(l['TDI_P']),1)}\n"
        except: continue
    return summary

# [3. 3인 에이전트 끝장 토론]
def run_alpha_trio_council():
    m = get_full_market_data()
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=m)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 패턴 분석."
    except: memory = "기억 저장소 연결 불가."

    prompt = f"""당신은 Alpha-Trio 2.7 전략 위원회입니다.
    데이터: {m} | 과거 기록: {memory}

    [미션]
    1. 에이전트 A (Quant): $RSI$, $TDI$, $ATR$의 상관관계를 통해 수급의 함정을 찾아라.
    2. 에이전트 B (Dewey): 이 상황을 역사적 변곡점과 대조하여 지능적인 '지식 증류'를 수행하라.
    3. 에이전트 C (Beckett): 너희의 논리는 부실하다. 최악의 시나리오와 손절가($SL$)의 타당성을 공격하라.

    반드시 JSON 형식으로만 답하십시오."""
    
    v = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt).text
    return v, m

# [4. 무조건 꽂히는 분할 전송 로직]
def send_safe_discord(content):
    # 디스코드 2000자 제한을 피하기 위해 1800자 단위 분할
    chunks = [content[i:i+1800] for i in range(0, len(content), 1800)]
    for i, chunk in enumerate(chunks):
        title = f"🏛️ **Alpha-Trio 2.7 보고서 ({i+1}/{len(chunks)})**"
        msg = f"{title}\n```json\n{chunk}\n```"
        res = requests.post(DISCORD_URL, json={"content": msg})
        if res.status_code != 204:
            print(f"❌ 전송 실패: {res.status_code} - {res.text}")
            sys.exit(1) # 실패 시 깃허브 액션을 빨간색(X)으로 만듦
    print("✅ 모든 보고서 전송 성공")

if __name__ == "__main__":
    print("🚀 Alpha-Trio 2.7 고지능 엔진 가동...")
    try:
        verdict, raw_data = run_alpha_trio_council()
        # Pinecone 저장
        embed = genai.embed_content(model="models/text-embedding-004", content=raw_data)['embedding']
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        # 안전 전송
        send_safe_discord(verdict)
    except Exception as e:
        print(f"🔥 치명적 에러: {e}")
        sys.exit(1)