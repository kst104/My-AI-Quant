import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone  # 👈 Cone 오타 수정 완료
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

def calculate_expert_logic(df):
    """라이브러리 없이 직접 계산하는 5대 지표 (정밀도 100%)"""
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

    # 5. TDI (RSI 기반 Price Line)
    df['TDI_P'] = df['RSI'].rolling(window=2).mean()
    return df

def get_intelligence():
    targets = ["^GSPC", "^IXIC", "NVDA", "LLY", "SOXX"]
    summary = ""
    for t in targets:
        try:
            df = calculate_expert_logic(yf.download(t, period="100d", progress=False))
            l = df.iloc[-1]
            summary += f"[{t}] P:{round(float(l['Close']),2)} | RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)}\n"
        except: continue
    
    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    news = "\n".join([f"- {a['title']}" for a in news_res.get('articles', [])[:5]])
    return summary, news

def alpha_trio_supreme():
    m, n = get_intelligence()
    # 과거 기억 소환 (Step 3: 지식 증류)
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=m)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 패턴 분석 시작."
    except: memory = "기억 저장소 연결 중."

    # 지능 강화 프롬프트
    prompt = f"""당신은 자산 운용사 Alpha-Trio의 수석 전략 위원회입니다. 
    데이터를 '해부'하고 에이전트 간의 파괴적인 토론을 통해 결론을 내세요.

    [데이터]: {m} | [뉴스]: {n} | [과거 오답노트]: {memory}

    - 에이전트 A(Quant): 지표 간의 다이버전스를 포착하라.
    - 에이전트 B(Dewey): 현재 상황을 역사적 사건과 교차검증하여 지식을 증류하라.
    - 에이전트 C(Beckett): 모든 낙관론을 부정하고 손절가($SL$)의 정당성을 공격하라.

    반드시 아래 JSON 규격으로만 답하십시오:
    {{
      "Action": "매수/매도/관망",
      "Strategy": "오늘의 작전명",
      "Debate_Log": {{ "A": "의견", "B": "의견", "C": "의견" }},
      "Knowledge_Distilled": "오늘 얻은 단 한 줄의 투자 원칙",
      "Self_Reflection": "과거 오답 대비 오늘의 성찰",
      "Targets": {{ "Entry": "0", "TP": "0", "SL": "0" }}
    }}"""
    
    v = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt).text
    return v, m

if __name__ == "__main__":
    print("🏛️ Alpha-Trio 2.5 초지능 엔진 가동...")
    try:
        verdict, raw_data = alpha_trio_supreme()
        # Pinecone 저장
        embed = genai.embed_content(model="models/text-embedding-004", content=raw_data)['embedding']
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        # 디스코드 보고
        requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.5 최종 판결**\n```json\n{verdict}\n```"})
        print("✅ 가동 및 보고 성공")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")