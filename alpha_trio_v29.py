import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import google.generativeai as genai
from pinecone import Pinecone
from datetime import datetime
import sys

# [1. 하이엔드 인프라 로드]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

genai.configure(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. 기술적 지능 엔진: TDI, Bollinger Bands, RSI, ATR]
def calculate_expert_indicators(df):
    df = df.copy()
    close = df['Close']
    
    # 볼린저 밴드 ($BB$)
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BBL'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    
    # RSI & TDI (Traders Dynamic Index)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    df['TDI_PL'] = df['RSI'].rolling(window=2).mean()   # Price Line
    df['TDI_MBL'] = df['RSI'].rolling(window=34).mean() # Market Base Line
    
    # 변동성 지표 ($ATR$)
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-close.shift()), abs(df['Low']-close.shift())], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    return df

# [3. 뉴스 지능: NewsAPI 기반 매크로 스캔]
def get_realtime_news():
    try:
        url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}"
        res = requests.get(url).json()
        articles = res.get('articles', [])[:5]
        return "\n".join([f"🔥 {a['title']}" for a in articles])
    except:
        return "뉴스 데이터 수집 지연."

# [4. 통합 데이터 스캔]
def get_integrated_data():
    targets = ["^GSPC", "^IXIC", "NVDA", "SOXX", "BTC-USD"]
    market_report = ""
    for t in targets:
        try:
            df = calculate_expert_indicators(yf.download(t, period="100d", progress=False))
            l = df.iloc[-1]
            price = round(float(l['Close']), 2)
            market_report += f"[{t}] P:{price} | RSI:{round(float(l['RSI']),1)} | TDI_PL:{round(float(l['TDI_PL']),1)} | BB:{'Upper' if price > l['BBU'] else 'Lower' if price < l['BBL'] else 'Neutral'}\n"
        except: continue
    return market_report

if __name__ == "__main__":
    print("🚀 Alpha-Trio 3.5 고지능 루프 가동...")
    try:
        # 데이터 수집 (지표 + 뉴스)
        m_data = get_integrated_data()
        n_data = get_realtime_news()
        
        # Vector DB 자아 성찰 (과거 기억 소환)
        embed = genai.embed_content(model="models/text-embedding-004", content=m_data)['embedding']
        past = index.query(vector=embed, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "첫 번째 기록입니다."

        # [계획표에 따른 에이전트 역할 분배]
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"""당신은 Alpha-Trio 전략 위원회입니다. 감독님의 계획표에 따라 시장을 해부하십시오.

        [데이터 피드]
        - 지표: {m_data}
        - 뉴스: {n_data}
        - 과거의 가설: {memory}

        1. 에이전트 A (Quant): $RSI$, $TDI$, $BB$의 상관관계를 통해 기술적 함정과 수급의 에너지를 보고하라.
        2. 에이전트 B (John Dewey): 뉴스와 지표를 결합하여 현재를 '경험적 변곡점'으로 해석하고, 실용적인 지식을 증류하라.
        3. 에이전트 C (Samuel Beckett): 과거의 실패(기억)를 근거로 너희의 낙관을 조롱하라. '실패하라, 더 낫게 실패하라'는 관점에서 리스크를 비판하라.

        JSON 형식으로 'Action', 'Strategy', 'Analysis(A,B,C)'를 작성하십시오."""
        
        verdict = model.generate_content(prompt).text

        # 결과 저장 및 전송
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": embed, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio 3.5 전략 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 모든 데이터 통합 및 보고 완료")

    except Exception as e:
        print(f"🔥 에러: {e}")
        sys.exit(1)