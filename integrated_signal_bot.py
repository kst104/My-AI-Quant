import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import google.generativeai as genai
from pinecone import Pinecone
import json
from datetime import datetime

# [인프라 설정]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def calculate_expert_indicators(df):
    """5대 지표 산출: RSI, BB, MACD, TDI, ATR"""
    df = df.copy()
    # RSI & ATR
    df['RSI'] = ta.rsi(df['Close'], length=13)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    # BB & MACD
    df = pd.concat([df, ta.bbands(df['Close'], length=20, std=2), ta.macd(df['Close'])], axis=1)
    # TDI (Price, Signal, Market)
    df['TDI_P'] = ta.sma(df['RSI'], length=2)
    df['TDI_S'] = ta.sma(df['RSI'], length=7)
    df['TDI_M'] = ta.sma(df['RSI'], length=34)
    return df

def get_intelligence():
    targets = ["^GSPC", "^IXIC", "^TNX", "NVDA", "LLY", "SOXX"]
    summary = ""
    for t in targets:
        try:
            df = calculate_expert_indicators(yf.download(t, period="100d", progress=False))
            l, p = df.iloc[-1], df.iloc[-2]
            change = ((l['Close'] - p['Close']) / p['Close']) * 100
            summary += f"[{t}] P:{round(float(l['Close']),2)}({round(float(change),2)}%) | RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)} | TDI_P:{round(float(l['TDI_P']),1)}\n"
        except: continue
    
    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    news = "\n".join([f"- {a['title']}" for a in news_res.get('articles', [])[:5]])
    return summary, news

def recall_memory(market_context):
    """지식 증류를 위한 과거 오답 노트 검색"""
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=market_context)['embedding']
        past = index.query(vector=embed, top_k=2, include_metadata=True)
        memories = ""
        for m in past['matches']:
            memories += f"📍 과거 기록({m['metadata'].get('date','Unknown')}): {m['metadata']['conclusion']}\n"
        return memories if memories else "과거 데이터 부족. 신규 학습 필요."
    except: return "기억 저장소 연결 지연 중."

def alpha_trio_council():
    m, n = get_intelligence()
    past = recall_memory(m)
    
    prompt = f"""당신은 Alpha-Trio 2.1 위원회입니다. 24시간의 분석과 과거 복기를 '지식 증류'하여 보고하십시오.
    [오늘의 데이터]: {m} | [뉴스]: {n} | [과거 오답노트]: {past}

    [에이전트 역할 및 지시]
    1. 에이전트 A (Quant): 5대 지표 기반 수급 분석.
    2. 에이전트 B (Dewey): 경험론적 가치 분석 및 지식 증류. (과거와 현재의 인과관계 규명)
    3. 에이전트 C (Beckett): 과거 오답을 근거로 본 위원회의 낙관론을 공격하고 리스크를 제안하라.

    반드시 아래 JSON 형식으로만 답하십시오:
    {{
      "Verdict": "매수/매도/관망",
      "Confidence": "0-100%",
      "Analysis": {{ "A": "의견", "B": "의견", "C": "의견" }},
      "Knowledge_Distillation": "과거 오답 대비 오늘의 성찰 및 추출된 투자 원칙",
      "Targets": {{ "Entry": "0", "TP": "0", "SL": "0" }}
    }}"""
    
    response = genai.GenerativeModel('gemini-1.5-pro').generate_content(prompt)
    return response.text, m

def save_to_pinecone(verdict, market):
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=market)['embedding']
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
    except: pass

if __name__ == "__main__":
    print("🏛️ Alpha-Trio 2.1 위원회 가동...")
    try:
        v, m = alpha_trio_council()
        save_to_pinecone(v, m)
        requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.1: 지식 증류 보고**\n```json\n{v}\n```"})
        print("✅ 가동 완료")
    except Exception as e: print(f"❌ 오류 발생: {e}")