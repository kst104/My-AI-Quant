import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import google.generativeai as genai
from pinecone import Pinecone

# [인프라 설정]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

def calculate_expert_indicators(df):
    """5대 지표: RSI, BB, MACD, TDI, ATR"""
    df['RSI'] = ta.rsi(df['Close'], length=13)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    df = pd.concat([df, ta.bbands(df['Close'], length=20), ta.macd(df['Close'])], axis=1)
    # TDI 직접 구현
    df['TDI_P'] = ta.sma(df['RSI'], length=2) # Green
    df['TDI_S'] = ta.sma(df['RSI'], length=7) # Red
    df['TDI_M'] = ta.sma(df['RSI'], length=34) # Yellow
    return df

def get_intelligence():
    targets = ["^GSPC", "^IXIC", "NVDA", "LLY", "SOXX"]
    market_summary = ""
    for t in targets:
        try:
            data = calculate_expert_indicators(yf.download(t, period="60d", progress=False))
            l = data.iloc[-1]
            market_summary += f"[{t}] P:{round(l['Close'],2)} RSI:{round(l['RSI'],1)} ATR:{round(l['ATR'],2)} TDI_P:{round(l['TDI_P'],1)}\n"
        except: continue
    
    news_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&apiKey={NEWS_KEY}").json()
    news = "\n".join([a['title'] for a in news_res.get('articles', [])[:5]])
    return market_summary, news

def alpha_trio_council(market, news):
    # Step 3: 과거 기억 소환
    model = genai.GenerativeModel('gemini-1.5-pro')
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=market)['embedding']
        past_search = index.query(vector=embed, top_k=1, include_metadata=True)
        memories = past_search['matches'][0]['metadata']['conclusion'] if past_search['matches'] else "신규 시장 상황."
    except: memories = "기억 저장소 연결 전."

    # Step 2 & 4: 3인 에이전트 끝장 토론 (역할 고정)
    prompt = f"""
    당신은 Alpha-Trio 2.1 위원회입니다.
    [시장 데이터]: {market}
    [뉴스]: {news}
    [과거 오답노트]: {memories}

    에이전트 A (현대 퀀트): RSI, MACD, TDI 기반 수급 분석.
    에이전트 B (존 듀이): 매크로 및 뉴스 심리 기반 가치 분석. (경험론적 실용주의)
    에이전트 C (사무엘 베켓): ATR, 볼린저 기반 리스크 관리. (회의적 신중함)

    반드시 아래 JSON 형식으로만 최종 결론을 내세요:
    {{ "Verdict": "매수/매도/관망", "Confidence": "0-100%", "Reason": "에이전트별 논쟁 요약", "Targets": {{"Entry": "0", "TP": "0", "SL": "0"}} }}
    """
    return model.generate_content(prompt).text

def distillate_knowledge(verdict, market):
    try:
        embed = genai.embed_content(model="models/text-embedding-004", content=market)['embedding']
        index.upsert(vectors=[{"id": str(pd.Timestamp.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict}}])
    except: pass

if __name__ == "__main__":
    m, n = get_intelligence()
    v = alpha_trio_council(m, n)
    distillate_knowledge(v, m)
    requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 2.1 가동 보고**\n{v}"})