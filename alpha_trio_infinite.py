import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from google import genai # 최신 SDK 적용
from pinecone import Pinecone
from datetime import datetime
import sys

# [1. 하이엔드 인프라 정렬]
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PINECONE_KEY = os.environ.get("PINECONE_API_KEY")
NEWS_KEY = os.environ.get("NEWS_API_KEY")

if not all([DISCORD_URL, GEMINI_KEY, PINECONE_KEY]):
    print("❌ 필수 API 설정이 부족합니다.")
    sys.exit(1)

# 최신 Gemini 클라이언트 초기화
client = genai.Client(api_key=GEMINI_KEY)
pc = Pinecone(api_key=PINECONE_KEY)
index = pc.Index("alpha-trio-memory")

# [2. 기술적 지능 엔진 ($LaTeX$ 적용)]
def calculate_expert_indicators(df):
    if df.empty or len(df) < 35: return None
    df = df.copy()
    close = df['Close']
    
    # Bollinger Bands ($BB$)
    df['BB_Mid'] = close.rolling(window=20).mean()
    df['BB_Std'] = close.rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BBL'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    
    # RSI & TDI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    df['TDI_PL'] = df['RSI'].rolling(window=2).mean()
    df['TDI_MBL'] = df['RSI'].rolling(window=34).mean()
    
    return df.dropna()

# [3. S&P 500 전수 조사 (5개년 타임리스)]
def explore_sp500_full_scan():
    print("🌌 S&P 500 전 종목 5개년 전수 조사 가동...")
    try:
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = table[0]['Symbol'].replace('.', '-', regex=True).tolist()
        
        # 5년치 배치 다운로드
        data = yf.download(tickers, period="5y", group_by='ticker', progress=False)
        
        stats = {"Overbought": 0, "Oversold": 0, "U-Break": 0, "L-Break": 0}
        samples = []

        for t in tickers:
            try:
                processed = calculate_expert_indicators(data[t])
                if processed is None: continue
                l = processed.iloc[-1]
                price = l['Close']
                if l['RSI'] > 70: stats["Overbought"] += 1
                if price > l['BBU']: stats["U-Break"] += 1
                
                if t in ["AAPL", "NVDA", "MSFT", "TSLA", "GOOGL"]:
                    samples.append(f"[{t}] RSI:{round(float(l['RSI']),1)} | TDI_PL:{round(float(l['TDI_PL']),1)}")
            except: continue
            
        summary = f"📊 S&P500 5y 통계: 과매수({stats['Overbought']}), BB상단돌파({stats['U-Break']})\n"
        return summary + "\n".join(samples)
    except Exception as e:
        return f"데이터 스캔 지연 (원인: {e})"

if __name__ == "__main__":
    print("🚀 Alpha-Trio Infinite V2 엔진 점화...")
    try:
        m_data = explore_sp500_full_scan()
        n_res = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={NEWS_KEY}").json()
        n_data = "\n".join([f"🔥 {a['title']}" for a in n_res.get('articles', [])[:5]]) if 'articles' in n_res else "뉴스 지연"

        brain_input = f"지표:\n{m_data}\n\n뉴스:\n{n_data}"
        
        # [방어] Empty Content 원천 봉쇄
        if len(brain_input.strip()) < 50:
            brain_input = "현재 실시간 데이터 수집 불가. 과거 5년의 패턴과 매크로 지식을 바탕으로 지능을 성장시켜라."

        # 최신 임베딩 호출
        embed_res = client.models.embed_content(model="text-embedding-004", contents=brain_input)
        vector = embed_res.embeddings[0].values
        
        past = index.query(vector=vector, top_k=1, include_metadata=True)
        memory = past['matches'][0]['metadata']['conclusion'] if past['matches'] else "신규 분석 시작."

        # [감독님 지시: 정예 3인 위원회]
        prompt = f"""당신은 Alpha-Trio 위원회입니다. 
        데이터: {brain_input} / 기억: {memory}

        1. A(Quant): 500개 종목의 $BB$, $TDI$ 분포를 통해 수급의 함정을 보고하라.
        2. B(John Dewey): 뉴스 흐름과 지표를 결합하여 '경험적 지식'을 증류하라.
        3. C(Samuel Beckett): 과거의 실수를 근거로 낙관론을 조롱하고 최악의 시나리오를 설계하라.
        
        JSON 형식으로만 답하십시오."""

        response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
        verdict = response.text

        # 저장 및 전송
        index.upsert(vectors=[{"id": str(datetime.now().timestamp()), "values": vector, "metadata": {"conclusion": verdict, "date": str(datetime.now())}}])
        
        chunks = [verdict[i:i+1800] for i in range(0, len(verdict), 1800)]
        for chunk in chunks:
            requests.post(DISCORD_URL, json={"content": f"🏛️ **Alpha-Trio Infinite 보고**\n```json\n{chunk}\n```"})
        
        print("✅ 자가학습 완료 및 초록색 체크 대기 중.")

    except Exception as e:
        print(f"🔥 에러 자백: {e}")
        sys.exit(1)