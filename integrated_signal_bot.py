import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta  # 설치는 pandas-ta, 호출은 pandas_ta!
import requests
import google.generativeai as genai
from pinecone import Pinecone
import json

# [환경 설정]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def calculate_expert_indicators(df):
    """5대 핵심 지표: RSI, BB, MACD, TDI, ATR"""
    df['RSI'] = ta.rsi(df['Close'], length=13)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    # 볼린저밴드 및 MACD
    bb = ta.bbands(df['Close'], length=20, std=2)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, bb, macd], axis=1)
    # TDI 직접 구현
    df['TDI_P'] = ta.sma(df['RSI'], length=2) # Green
    df['TDI_S'] = ta.sma(df['RSI'], length=7) # Red
    df['TDI_M'] = ta.sma(df['RSI'], length=34) # Yellow
    return df

def get_deep_intelligence():
    targets = ["^GSPC", "^IXIC", "^TNX", "NVDA", "LLY", "SOXX"]
    market_summary = ""
    for t in targets:
        try:
            data = calculate_expert_indicators(yf.download(t, period="100d", progress=False))
            l = data.iloc[-1]
            p = data.iloc[-2]
            change = ((l['Close'] - p['Close']) / p['Close']) * 100
            market_summary += f"[{t}] P:{round(float(l['Close']),2)}({round(float(change),2)}%) | RSI:{round(float(l['RSI']),1)} | ATR:{round(float(l['ATR']),2)} | TDI_P:{round(float(l['TDI_P']),1)}\n"
        except: continue
    
    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    news = "\n".join([f"- {a['title']}" for a in news_res.get('articles', [])[:5]])
    return market_summary, news

def recall_memory(current_market):
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=current_market)['embedding']
        past = index.query(vector=embed, top_k=2, include_metadata=True)
        memories = ""
        for match in past['matches']:
            memories += f"📌 과거 기록({match['metadata'].get('date','알수없음')}): {match['metadata']['conclusion']}\n"
        return memories if memories else "과거 데이터 부족."
    except: return "기억 소환 실패."

def alpha_trio_logic():
    market, news = get_deep_intelligence()
    memories = recall_memory(market)
    
    model = genai.GenerativeModel('gemini-1.5-pro')
    prompt = f"""
    당신은 Alpha-Trio 2.1 위원회입니다. 24시간의 분석을 '지식 증류'하여 보고하십시오.
    [데이터]: {market} | [뉴스]: {news} | [과거 오답노트]: {memories}

    1. 에이전트 A (Quant): 지표 수급 분석.
    2. 에이전트 B (Dewey): 경험론적 가치 분석 및 지식 증류.
    3. 에이전트 C (Beckett): 과거 오답을 근거로 한 리스크 비판.

    반드시 아래 JSON 규격으로만 답하십시오:
    {{
      "Verdict": "매수/매도/관망",
      "Confidence": "0-100%",
      "Analysis": {{ "A": "의견", "B": "의견", "C": "의견" }},
      "Self_Reflection": "과거 오답노트 복기 및 교차검증 결과",
      "Knowledge_Distilled": "오늘 얻은 단 한 줄의 투자 로직",
      "Targets": {{ "Entry": "0", "TP": "0", "SL": "0" }}
    }}
    """
    return model.generate_content(prompt).text, market

def distill_and_save(verdict, market):
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=market)['embedding']
        index.upsert(vectors=[{"id": str(pd.Timestamp.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(pd.Timestamp.now())}}])
    except: pass

if __name__ == "__main__":
    v, m = alpha_trio_logic()
    distill_and_save(v, m)
    requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.1: 지식 증류 보고**\n```json\n{v}\n```"})