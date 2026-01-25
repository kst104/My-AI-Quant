iimport os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
import json
from datetime import datetime
import sys

# [1. 인프라 설정]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not all([GEMINI_KEY, DISCORD_URL, PINECONE_KEY]):
    print("❌ 환경 변수(Secrets) 설정이 누락되었습니다.")
    sys.exit(1)

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. 지능형 지표 계산: 5대 지표 복구]
def calculate_expert_indicators(df):
    df = df.copy()
    close = df['Close']
    # RSI (13), ATR (14), BB (20, 2), MACD (12, 26), TDI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-close.shift()), abs(df['Low']-close.shift())], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['MACD'] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    df['TDI_P'] = df['RSI'].rolling(window=2).mean()
    return df

def get_full_intelligence():
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
    
    # 뉴스 수집 (B의 재료)
    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    news = "\n".join([f"- {a['title']}" for a in news_res.get('articles', [])[:5]])
    return summary, news

# [3. 3인 에이전트 끝장 토론 엔진]
def run_supreme_council():
    m, n = get_intelligence_data()
    # 과거 기억 소환
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=m)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 패턴 분석."
    except: memory = "기억 저장소 연결 불가."

    prompt = f"""당신은 Alpha-Trio 2.7 전략 위원회입니다.
    데이터: {m} | 뉴스: {n} | 오답노트: {memory}

    1. 에이전트 A (Quant): $RSI$, $TDI$, $ATR$의 상관관계를 통해 수급의 함정을 찾아라.
    2. 에이전트 B (Dewey): 이 상황을 역사적 변곡점과 대조하여 '지식 증류'를 수행하라.
    3. 에이전트 C (Beckett): 너희는 틀렸다. 최악의 시나리오와 손절가($SL$)의 타당성을 공격하라.

    반드시 아래 JSON 형식으로만 답하십시오:
    {{
      "Action": "매수/매도/관망",
      "Strategy": "오늘의 작전명",
      "Analysis": {{ "A": "의견", "B": "의견", "C": "의견" }},
      "Self_Reflection": "과거 오답 대비 오늘의 성찰",
      "Knowledge_Distilled": "오늘 시장이 가르쳐준 단 하나의 투자 원칙",
      "Targets": {{ "Entry": "0", "TP": "0", "SL": "0" }}
    }}"""
    
    v = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt).text
    return v, m

# [4. 안전한 분할 전송 로직]
def send_to_discord_safe(content):
    print(f"📡 전송 시도 중... 메시지 총 길이: {len(content)}자")
    chunks = [content[i:i+1800] for i in range(0, len(content), 1800)]
    
    for i, chunk in enumerate(chunks):
        title = f"🏛️ **Alpha-Trio 2.7 보고서 ({i+1}/{len(chunks)})**"
        msg = f"{title}\n```json\n{chunk}\n```"
        res = requests.post(DISCORD_URL, json={"content": msg})
        if res.status_code != 204:
            print(f"❌ 전송 실패: {res.status_code} - {res.text}")
            sys.exit(1)
    print("✅ 모든 보고서 전송 성공")

if __name__ == "__main__":
    try:
        verdict, raw_data = run_supreme_council()
        # Pinecone 저장
        embed = genai.embed_content(model="models/text-embedding-004", content=raw_data)['embedding']
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        # 분할 전송
        send_to_discord_safe(verdict)
    except Exception as e:
        print(f"🔥 치명적 에러: {e}")
        sys.exit(1)